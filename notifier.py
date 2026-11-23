"""Push notification service | 推送通知服务

Design notes / 设计要点
-----------------------
* Every channel has a hard time budget, so one broken endpoint can never pin a
  worker thread for minutes. 每个渠道都有总时间预算，避免线程被长期占用。
* The submit queue is bounded; when it is full the notification is dropped and
  counted instead of growing memory without limit. 队列有上限，满了就丢弃并计数。
* TLS downgrade only happens on certificate errors, is logged and counted, and
  is disabled for channels that carry the credential inside the URL.
  TLS 降级仅在证书错误时发生、有日志与计数，且对凭据在 URL 中的渠道禁用。
* Failures are recorded as ``PUSH_FAILED`` log lines so the web panel can show
  them without any IPC. 失败写 PUSH_FAILED 日志行，面板可直接统计。
"""
import html
import json
import re
import ssl
import time
import base64
import hmac
import hashlib
import logging
import threading
import collections
import urllib.request
import urllib.error
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional, Tuple

# Import constants from config module | 从 config 模块导入常量
try:
    from config import PUSH_MAX_WORKERS, PUSH_RETRY, PUSH_MAX_QUEUE, PUSH_TIME_BUDGET
except ImportError:
    # Fallback if config module not available | 如果 config 模块不可用则使用默认值
    PUSH_MAX_WORKERS = 3
    PUSH_RETRY = 2
    PUSH_MAX_QUEUE = 64
    PUSH_TIME_BUDGET = 25.0

REQUEST_TIMEOUT = 10  # Seconds per HTTP request | 单次请求超时
USER_AGENT = "MMDVM-Push-Notifier"


def _safe_url(url: str) -> str:
    """Strip credentials from a URL before logging | 记录日志前抹掉凭据

    Telegram keeps the bot token in the path (``/bot<id>:<secret>/``), Feishu keeps
    the hook id in the last segment. Both are credentials, both end up in logs.
    Telegram 的 token 在路径里，飞书的 hook id 在最后一段，都会进日志。
    """
    try:
        parts = urllib.parse.urlsplit(url)
        path = parts.path
        host = parts.netloc.lower()

        if host.endswith("telegram.org"):
            match = re.match(r"^(/bot)([^/]+)(.*)$", path)
            if match:
                path = f"{match.group(1)}***{match.group(3)}"
        elif "/hook/" in path:
            # Mask the whole segment after /hook/ regardless of a trailing
            # slash or extra path segments; rpartition('/') would leave the
            # credential intact when the URL ends with '/'.
            # 无论后面是否带斜杠或额外路径，都遮掉 /hook/ 后的整段；
            # rpartition('/') 在结尾斜杠时会把凭据原样留下。
            path = re.sub(r"(/hook/)[^/?#]*", r"\1***", path)

        return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, "", ""))
    except Exception:
        return "url"


def _verified_context():
    """Default verifying TLS context | 默认校验证书的上下文"""
    return ssl.create_default_context()


def _insecure_context():
    """Fallback context without verification | 不校验证书的降级上下文"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def html_to_lark_md(text: str) -> str:
    """Convert our ``<b>`` markup into Feishu lark_md | 转换飞书 lark_md

    Tag replacement runs on the *escaped* string, then entities are decoded, so a
    user-supplied ``<b>`` (stored as ``&lt;b&gt;``) stays literal text.
    先在转义后的字符串上换标签，再解实体，用户输入的 <b> 仍保持普通文本。
    """
    return html.unescape(text.replace("<b>", "**").replace("</b>", "**"))


class PushService:
    """Multi-platform push notification service | 多平台推送通知服务"""
    _max_workers = PUSH_MAX_WORKERS
    _executor: Optional[ThreadPoolExecutor] = None
    _executor_lock = threading.Lock()  # Thread-safe executor management | 线程安全的执行器管理
    _pending_lock = threading.Lock()
    _pending = 0           # In-flight + queued tasks | 在途与排队任务数
    _tls_lock = threading.Lock()
    _insecure_uses = 0     # How many times we downgraded TLS | TLS 降级次数
    _stats_lock = threading.Lock()
    _stats = {"ok": 0, "failed": 0, "dropped": 0, "skipped": 0, "tls_downgraded": 0}
    _recent_failures = collections.deque(maxlen=10)

    # ---------- executor ----------
    @classmethod
    def _ensure_executor(cls) -> Optional[ThreadPoolExecutor]:
        """Ensure executor exists, returns None if shutdown | 确保执行器存在，关闭时返回 None"""
        with cls._executor_lock:
            if cls._executor is None:
                cls._executor = ThreadPoolExecutor(max_workers=cls._max_workers)
                logging.getLogger(__name__).info(
                    "ThreadPoolExecutor initialized with %s workers", cls._max_workers)
            return cls._executor

    # ---------- stats ----------
    @classmethod
    def _count(cls, key: str, delta: int = 1):
        with cls._stats_lock:
            cls._stats[key] = cls._stats.get(key, 0) + delta

    @classmethod
    def stats(cls) -> Dict[str, Any]:
        """Snapshot of counters since process start | 进程启动以来的计数快照"""
        with cls._stats_lock:
            data = dict(cls._stats)
            data["pending"] = cls._pending
            data["recent_failures"] = list(cls._recent_failures)
            data["tls_downgraded"] = cls._insecure_uses
        return data

    # ---------- helpers ----------
    @staticmethod
    def get_fs_sign(secret: str, timestamp: str) -> str:
        """Generate Feishu webhook signature | 生成飞书 Webhook 签名"""
        string_to_sign = f"{timestamp}\n{secret}"
        hmac_code = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
        return base64.b64encode(hmac_code).decode("utf-8")

    @classmethod
    def _attempt(cls, url: str, data: Optional[bytes], is_json: bool, ctx) -> Tuple[str, str]:
        """Single POST. Returns (state, body) where state is ok/http4xx/tls/error."""
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("User-Agent", USER_AGENT)
        if is_json:
            req.add_header("Content-Type", "application/json; charset=utf-8")
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT, context=ctx) as resp:
                return "ok", resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            detail = ""
            try:
                detail = e.read().decode("utf-8", errors="replace")[:200]
            except Exception:
                pass
            if 400 <= e.code < 500:
                return "http4xx", detail
            logging.getLogger(__name__).warning(
                "HTTP %s for %s %s", e.code, _safe_url(url), detail)
            return "error", detail
        except ssl.SSLCertVerificationError as e:
            return "tls", str(e)
        except ssl.SSLError as e:
            logging.getLogger(__name__).warning("TLS handshake error for %s: %s", _safe_url(url), e)
            return "error", str(e)
        except urllib.error.URLError as e:
            reason = getattr(e, "reason", e)
            # urllib wraps OSError (and therefore SSLError) into URLError, so the
            # certificate failure usually arrives here instead of in the ssl branch.
            # urllib 会把 SSLError 包进 URLError，证书错误多数情况下从这里出来。
            if isinstance(reason, ssl.SSLCertVerificationError):
                return "tls", str(reason)
            if isinstance(reason, ssl.SSLError):
                logging.getLogger(__name__).warning(
                    "TLS handshake error for %s: %s", _safe_url(url), reason)
                return "error", str(reason)
            logging.getLogger(__name__).warning(
                "URL error for %s: %s", _safe_url(url), reason)
            return "error", str(reason)
        except Exception as e:
            logging.getLogger(__name__).warning("Request error for %s: %s", _safe_url(url), e)
            return "error", str(e)

    @classmethod
    def _http_post(cls, url: str, data: Optional[bytes] = None, is_json: bool = False,
                   retries: int = PUSH_RETRY, allow_insecure: bool = True) -> Tuple[bool, str]:
        """POST with bounded retries + policy-controlled TLS fallback.

        Returns (transport_ok, body). Total wall time is capped by PUSH_TIME_BUDGET,
        so a dead endpoint cannot hold a worker for minutes.
        返回 (传输成功, 响应体)；总耗时受 PUSH_TIME_BUDGET 限制。
        """
        log = logging.getLogger(__name__)
        deadline = time.monotonic() + PUSH_TIME_BUDGET

        try:
            verified = _verified_context()
        except Exception as e:  # pragma: no cover - depends on host CA store
            log.error("Cannot build a verified TLS context (%s); every request for %s "
                      "will use UNVERIFIED TLS until the CA bundle is fixed",
                      e, _safe_url(url))
            verified = None

        for attempt in range(retries + 1):
            if time.monotonic() >= deadline:
                log.warning("Time budget %.0fs exhausted for %s", PUSH_TIME_BUDGET, _safe_url(url))
                break

            if verified is not None:
                state, body = cls._attempt(url, data, is_json, verified)
            else:
                # No CA store at all: stay explicit rather than silently insecure.
                # 系统没有可用 CA 库时明确降级，并记录日志。
                state, body = "tls", "no verified context"

            if state == "ok":
                return True, body
            if state == "http4xx":
                log.error("HTTP 4xx for %s: %s", _safe_url(url), body)
                return False, body

            if state == "tls":
                if not allow_insecure:
                    log.error(
                        "TLS verification failed for %s and the insecure fallback is disabled "
                        "for this channel (credential travels inside the URL) — dropped",
                        _safe_url(url))
                    return False, ""
                if time.monotonic() >= deadline:
                    log.warning("Time budget reached before the insecure retry for %s",
                                _safe_url(url))
                    break
                with cls._tls_lock:
                    cls._insecure_uses += 1
                    uses = cls._insecure_uses
                log.warning(
                    "Certificate verification failed for %s, retrying with verification "
                    "DISABLED (downgrades so far: %s)", _safe_url(url), uses)
                state, body = cls._attempt(url, data, is_json, _insecure_context())
                if state == "ok":
                    return True, body
                if state == "http4xx":
                    return False, body

            if attempt < retries:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                time.sleep(min(2 ** attempt, remaining))

        log.error("All attempts failed for %s", _safe_url(url))
        return False, ""

    @staticmethod
    def _json_field(text: str, *keys, default=None):
        try:
            data = json.loads(text)
        except (ValueError, TypeError):
            return default
        if not isinstance(data, dict):
            return default
        for key in keys:
            if key in data:
                return data[key]
        return default

    # ---------- platform push ----------
    @classmethod
    def _push_feishu(cls, config: Dict, type_label: str, body_text: str, is_voice: bool) -> bool:
        try:
            ts = str(int(time.time()))
            template = "blue" if is_voice else ("orange" if "上线" in type_label else "green")
            fs_payload = {
                "msg_type": "interactive",
                "card": {
                    "header": {"title": {"tag": "plain_text", "content": type_label},
                               "template": template},
                    "elements": [{"tag": "div",
                                  "text": {"tag": "lark_md", "content": html_to_lark_md(body_text)}}]
                }
            }
            if config.get("fs_secret"):
                fs_payload["timestamp"] = ts
                fs_payload["sign"] = cls.get_fs_sign(config["fs_secret"], ts)
            # The hook id inside the URL is a credential: no unverified TLS for it.
            # hook id 在 URL 里，属于凭据，禁止降级到不校验的 TLS。
            ok, body = cls._http_post(config["fs_webhook"],
                                      data=json.dumps(fs_payload, ensure_ascii=False).encode("utf-8"),
                                      is_json=True, allow_insecure=False)
            if not ok:
                return False
            code = cls._json_field(body, "code", "StatusCode")
            if code in (0, "0"):
                return True
            logging.getLogger(__name__).error("Feishu rejected push: %s", body[:200])
            return False
        except Exception as e:
            logging.getLogger(__name__).error("Feishu push failed: %s", e)
            return False

    @classmethod
    def _push_wechat(cls, config: Dict, type_label: str, body_text: str) -> bool:
        try:
            br = "<br>"
            html_content = (f"<b>{html.escape(type_label)}</b>{br}{br}"
                            f"{br.join(body_text.splitlines())}")
            payload = {"token": config["wx_token"], "title": type_label,
                       "content": html_content, "template": "html"}
            ok, body = cls._http_post("https://www.pushplus.plus/send",
                                      data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                      is_json=True)
            if not ok:
                return False
            code = cls._json_field(body, "code")
            if code == 200:
                return True
            logging.getLogger(__name__).error("PushPlus rejected push: %s", body[:200])
            return False
        except Exception as e:
            logging.getLogger(__name__).error("WeChat push failed: %s", e)
            return False

    @classmethod
    def _push_telegram(cls, config: Dict, type_label: str, body_text: str) -> bool:
        try:
            text = f"<b>{html.escape(type_label)}</b>\n\n{body_text}"
            url = f"https://api.telegram.org/bot{config['tg_token']}/sendMessage"
            data = urllib.parse.urlencode({
                "chat_id": config["tg_chat_id"],
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": "true",
            }).encode("utf-8")
            # The bot token is part of the URL: never fall back to unverified TLS.
            # bot token 在 URL 里，禁止降级到不校验的 TLS。
            ok, body = cls._http_post(url, data=data, allow_insecure=False)
            if not ok:
                return False
            if cls._json_field(body, "ok") is True:
                return True
            logging.getLogger(__name__).error("Telegram rejected push: %s", body[:200])
            return False
        except Exception as e:
            logging.getLogger(__name__).error("Telegram push failed: %s", e)
            return False

    # ---------- orchestration ----------
    @staticmethod
    def has_channel(config: Dict) -> bool:
        """True when at least one channel is enabled AND configured | 是否至少有一个可用通道"""
        return bool(
            (config.get("push_fs_enabled") and config.get("fs_webhook")) or
            (config.get("push_wx_enabled") and config.get("wx_token")) or
            (config.get("push_tg_enabled") and config.get("tg_token") and config.get("tg_chat_id"))
        )

    @classmethod
    def _do_push_logic(cls, config: Dict, type_label: str, body_text: str, is_voice: bool) -> bool:
        log = logging.getLogger(__name__)
        if not cls.has_channel(config):
            log.warning("No push channel enabled/configured, notification dropped")
            cls._count("skipped")
            return False

        results = {}
        if config.get("push_fs_enabled") and config.get("fs_webhook"):
            results["feishu"] = cls._push_feishu(config, type_label, body_text, is_voice)
        if config.get("push_wx_enabled") and config.get("wx_token"):
            results["pushplus"] = cls._push_wechat(config, type_label, body_text)
        if config.get("push_tg_enabled") and config.get("tg_token") and config.get("tg_chat_id"):
            results["telegram"] = cls._push_telegram(config, type_label, body_text)

        success = any(results.values())
        if success:
            cls._count("ok")
        else:
            cls._count("failed")
            failed = ",".join(k for k, v in results.items() if not v) or "none"
            # Stable marker so the admin panel can count failures from the log.
            # 固定标记，便于面板从日志统计失败次数。
            log.error("PUSH_FAILED channel=%s title=%s", failed, type_label)
            with cls._stats_lock:
                cls._recent_failures.append({
                    "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "channel": failed,
                    "title": type_label,
                })
        return success

    @classmethod
    def _run_task(cls, config: Dict, type_label: str, body_text: str, is_voice: bool) -> bool:
        """Executor wrapper that always releases the pending slot | 释放队列计数的包装器"""
        try:
            return cls._do_push_logic(config, type_label, body_text, is_voice)
        except Exception as e:
            logging.getLogger(__name__).error("Push task crashed: %s", e)
            return False
        finally:
            with cls._pending_lock:
                cls._pending = max(0, cls._pending - 1)

    @classmethod
    def send(cls, config: Dict, type_label: str, body_text: str,
             is_voice: bool = True, async_mode: bool = True):
        """Queue (or run) a notification.

        Returns a ``Future`` in async mode (None when rejected), or a bool in sync
        mode. 异步模式返回 Future（被拒绝时为 None），同步模式返回 bool。
        """
        log = logging.getLogger(__name__)

        if not cls.has_channel(config):
            log.warning("No push channel enabled/configured, notification dropped")
            cls._count("skipped")
            return None if async_mode else False

        if not async_mode:
            return cls._do_push_logic(config, type_label, body_text, is_voice)

        with cls._pending_lock:
            if cls._pending >= PUSH_MAX_QUEUE:
                cls._count("dropped")
                log.warning(
                    "Push queue full (%s pending), dropping notification: %s",
                    cls._pending, type_label)
                return None
            cls._pending += 1

        executor = cls._ensure_executor()
        if executor is None:
            with cls._pending_lock:
                cls._pending = max(0, cls._pending - 1)
            log.warning("Cannot send: executor is shutdown")
            return None
        try:
            return executor.submit(cls._run_task, config, type_label, body_text, is_voice)
        except RuntimeError:
            with cls._pending_lock:
                cls._pending = max(0, cls._pending - 1)
            log.warning("Executor rejected the task (shutting down), notification dropped")
            return None

    @classmethod
    def shutdown(cls):
        """Gracefully shutdown executor and wait for pending tasks | 优雅关闭执行器并等待待处理任务"""
        with cls._executor_lock:
            executor = cls._executor
            cls._executor = None
        if executor is not None:
            executor.shutdown(wait=True)
            logging.getLogger(__name__).info(
                "ThreadPoolExecutor shutdown complete (stats: %s)", cls.stats())
