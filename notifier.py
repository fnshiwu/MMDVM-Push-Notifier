import json
import ssl
import time
import base64
import hmac
import hashlib
import urllib.request
import urllib.error
import urllib.parse
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Dict, Tuple

# Import constants from config module | 从 config 模块导入常量
try:
    from config import PUSH_MAX_WORKERS, PUSH_RETRY
except ImportError:
    # Fallback if config module not available | 如果 config 模块不可用则使用默认值
    PUSH_MAX_WORKERS = 3
    PUSH_RETRY = 2

REQUEST_TIMEOUT = 12  # Seconds per HTTP request | 单次请求超时
USER_AGENT = "MMDVM-Push-Notifier"


def _ssl_contexts():
    """Verified first, unverified as last resort (minimal images lack CA bundle)"""
    contexts = []
    try:
        contexts.append(ssl.create_default_context())
    except Exception:
        pass
    # Fallback: Pi-Star Bookworm ships ca-certificates, but a broken bundle
    # must never silently stop all notifications | 证书链异常时降级但不静默失败
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    contexts.append(ctx)
    return contexts


class PushService:
    """Multi-platform push notification service | 多平台推送通知服务"""
    _max_workers = PUSH_MAX_WORKERS
    _executor: Optional[ThreadPoolExecutor] = None
    _executor_lock = threading.Lock()  # Thread-safe executor management | 线程安全的执行器管理
    _ctx_verified = None
    _ctx_insecure = None

    # ---------- executor ----------
    @classmethod
    def _ensure_executor(cls) -> bool:
        """Ensure executor exists, returns False if shutdown | 确保执行器存在，关闭时返回 False"""
        with cls._executor_lock:
            if cls._executor is None:
                cls._executor = ThreadPoolExecutor(max_workers=cls._max_workers)
                logging.getLogger(__name__).info(
                    "ThreadPoolExecutor initialized with %s workers", cls._max_workers)
            return cls._executor is not None

    # ---------- helpers ----------
    @staticmethod
    def get_fs_sign(secret: str, timestamp: str) -> str:
        """Generate Feishu webhook signature | 生成飞书 Webhook 签名"""
        string_to_sign = f"{timestamp}\n{secret}"
        hmac_code = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
        return base64.b64encode(hmac_code).decode("utf-8")

    @classmethod
    def _http_post(cls, url: str, data: bytes = None, is_json: bool = False,
                   retries: int = PUSH_RETRY) -> Tuple[bool, str]:
        """POST with retry + TLS fallback. Returns (transport_ok, body) | 带回退的 POST"""
        last_error = None
        for attempt in range(retries + 1):
            for ctx in _ssl_contexts():
                try:
                    req = urllib.request.Request(url, data=data, method="POST")
                    req.add_header("User-Agent", USER_AGENT)
                    if is_json:
                        req.add_header("Content-Type", "application/json; charset=utf-8")
                    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT, context=ctx) as resp:
                        return True, resp.read().decode("utf-8", errors="replace")
                except urllib.error.HTTPError as e:
                    last_error = e
                    # 4xx will not improve by retrying | 4xx 重试无意义
                    if 400 <= e.code < 500:
                        body = ""
                        try:
                            body = e.read().decode("utf-8", errors="replace")[:200]
                        except Exception:
                            pass
                        logging.getLogger(__name__).error(
                            "HTTP %s for %s %s", e.code, url.split('?')[0], body)
                        return False, body
                    logging.getLogger(__name__).warning(
                        "HTTP error %s on attempt %s/%s", e.code, attempt + 1, retries + 1)
                except ssl.SSLError as e:
                    last_error = e
                    logging.getLogger(__name__).warning(
                        "TLS error on attempt %s/%s, retrying with relaxed context: %s",
                        attempt + 1, retries + 1, e)
                    continue  # try the next (insecure) context immediately
                except urllib.error.URLError as e:
                    last_error = e
                    logging.getLogger(__name__).warning(
                        "URL error on attempt %s/%s: %s", attempt + 1, retries + 1, e.reason)
                    break
                except Exception as e:
                    last_error = e
                    logging.getLogger(__name__).warning(
                        "Request error on attempt %s/%s: %s", attempt + 1, retries + 1, e)
                    break
            if attempt < retries:
                time.sleep(2 ** attempt)
        logging.getLogger(__name__).error("All retries failed for %s: %s",
                                          url.split('?')[0], last_error)
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
                    "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": body_text}}]
                }
            }
            if config.get("fs_secret"):
                fs_payload["timestamp"] = ts
                fs_payload["sign"] = cls.get_fs_sign(config["fs_secret"], ts)
            ok, body = cls._http_post(config["fs_webhook"],
                                      data=json.dumps(fs_payload, ensure_ascii=False).encode("utf-8"),
                                      is_json=True)
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
            html_content = f"<b>{type_label}</b>{br}{br}{br.join(body_text.splitlines())}"
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
            text = f"<b>{type_label}</b>\n\n{body_text}"
            url = f"https://api.telegram.org/bot{config['tg_token']}/sendMessage"
            data = urllib.parse.urlencode({
                "chat_id": config["tg_chat_id"],
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": "true",
            }).encode("utf-8")
            ok, body = cls._http_post(url, data=data)
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
        if not cls.has_channel(config):
            logging.getLogger(__name__).warning(
                "No push channel enabled/configured, notification dropped")
            return False
        success = False
        if config.get("push_fs_enabled") and config.get("fs_webhook"):
            success = cls._push_feishu(config, type_label, body_text, is_voice) or success
        if config.get("push_wx_enabled") and config.get("wx_token"):
            success = cls._push_wechat(config, type_label, body_text) or success
        if config.get("push_tg_enabled") and config.get("tg_token") and config.get("tg_chat_id"):
            success = cls._push_telegram(config, type_label, body_text) or success
        if not success:
            logging.getLogger(__name__).warning(
                "No channel accepted the message (check enable flags and tokens)")
        return success

    @classmethod
    def post_with_retry(cls, url: str, data: bytes = None, is_json: bool = False,
                        retries: int = PUSH_RETRY) -> Optional[str]:
        """Backwards compatible wrapper, returns body or None | 兼容旧接口"""
        ok, body = cls._http_post(url, data=data, is_json=is_json, retries=retries)
        return body if ok else None

    @classmethod
    def send(cls, config: Dict, type_label: str, body_text: str,
             is_voice: bool = True, async_mode: bool = True):
        if not cls._ensure_executor():
            logging.getLogger(__name__).warning("Cannot send: executor is shutdown")
            return None

        if async_mode:
            executor_available = False
            with cls._executor_lock:
                if cls._executor is not None:
                    cls._executor.submit(cls._do_push_logic, config, type_label, body_text, is_voice)
                    executor_available = True
            if not executor_available:
                logging.getLogger(__name__).warning(
                    "Executor shutdown during send, dropping notification")
                return None
            return None
        return cls._do_push_logic(config, type_label, body_text, is_voice)

    @classmethod
    def shutdown(cls):
        """Gracefully shutdown executor and wait for pending tasks | 优雅关闭执行器并等待待处理任务"""
        executor_to_shutdown = None
        with cls._executor_lock:
            if cls._executor is not None:
                executor_to_shutdown = cls._executor
                cls._executor = None

        if executor_to_shutdown is not None:
            executor_to_shutdown.shutdown(wait=True)
            logging.getLogger(__name__).info("ThreadPoolExecutor shutdown complete")
