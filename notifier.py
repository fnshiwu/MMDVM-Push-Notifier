import json
import time
import base64
import hmac
import hashlib
import urllib.request
import urllib.parse
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Dict

PUSH_MAX_WORKERS = 3
PUSH_RETRY = 2

class PushService:
    """Multi-platform push notification service | 多平台推送通知服务"""
    _max_workers = PUSH_MAX_WORKERS
    _executor: Optional[ThreadPoolExecutor] = None
    _executor_lock = threading.Lock()  # Thread-safe executor management | 线程安全的执行器管理

    @classmethod
    def _ensure_executor(cls) -> bool:
        """Ensure executor exists, returns False if shutdown | 确保执行器存在，关闭时返回 False"""
        with cls._executor_lock:
            if cls._executor is None:
                cls._executor = ThreadPoolExecutor(max_workers=cls._max_workers)
                logging.getLogger(__name__).info(f"ThreadPoolExecutor initialized with {cls._max_workers} workers")
            return cls._executor is not None
    @staticmethod
    def get_fs_sign(secret: str, timestamp: str) -> str:
        """Generate Feishu webhook signature | 生成飞书 Webhook 签名"""
        string_to_sign = f"{timestamp}\n{secret}"
        hmac_code = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
        return base64.b64encode(hmac_code).decode("utf-8")
    @classmethod
    def _do_push_logic(cls, config: Dict, type_label: str, body_text: str, is_voice: bool):
        """Execute push logic for all enabled platforms | 执行所有启用平台的推送逻辑"""
        if config.get("push_fs_enabled") and config.get("fs_webhook"):
            cls._push_feishu(config, type_label, body_text, is_voice)
        if config.get("push_wx_enabled") and config.get("wx_token"):
            cls._push_wechat(config, type_label, body_text)
        if config.get("push_tg_enabled") and config.get("tg_token") and config.get("tg_chat_id"):
            cls._push_telegram(config, type_label, body_text)
    @classmethod
    def _push_feishu(cls, config: Dict, type_label: str, body_text: str, is_voice: bool):
        """Push notification to Feishu/Lark | 推送通知到飞书"""
        try:
            ts = str(int(time.time()))
            template = "blue" if is_voice else ("orange" if "上线" in type_label else "green")
            fs_payload = {
                "msg_type": "interactive",
                "card": {
                    "header": {"title": {"tag": "plain_text", "content": type_label}, "template": template},
                    "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": body_text}}]
                }
            }
            if config.get("fs_secret"):
                fs_payload["timestamp"] = ts
                fs_payload["sign"] = cls.get_fs_sign(config["fs_secret"], ts)
            cls.post_with_retry(config["fs_webhook"], data=json.dumps(fs_payload).encode("utf-8"), is_json=True)
        except Exception as e:
            logging.getLogger(__name__).error(f"Feishu push failed: {e}")
    @classmethod
    def _push_wechat(cls, config: Dict, type_label: str, body_text: str):
        """Push notification to WeChat via PushPlus | 通过 PushPlus 推送到微信"""
        try:
            br = "<br>"
            html_content = f"<b>{type_label}</b>{br}{br}{br.join(body_text.splitlines())}"
            payload = {"token": config["wx_token"], "title": type_label, "content": html_content, "template": "html"}
            cls.post_with_retry("http://www.pushplus.plus/send", data=json.dumps(payload).encode("utf-8"), is_json=True)
        except Exception as e:
            logging.getLogger(__name__).error(f"WeChat push failed: {e}")
    @classmethod
    def _push_telegram(cls, config: Dict, type_label: str, body_text: str):
        """Push notification to Telegram | 推送通知到 Telegram"""
        try:
            text = f"<b>{type_label}</b>\n\n{body_text}"
            url = f"https://api.telegram.org/bot{config['tg_token']}/sendMessage"
            data = urllib.parse.urlencode({"chat_id": config["tg_chat_id"], "text": text, "parse_mode": "HTML"}).encode("utf-8")
            cls.post_with_retry(url, data=data)
        except Exception as e:
            logging.getLogger(__name__).error(f"Telegram push failed: {e}")
    @classmethod
    def post_with_retry(cls, url: str, data: bytes = None, is_json: bool = False, retries: int = PUSH_RETRY) -> Optional[str]:
        """HTTP POST with exponential backoff retry | 带指数退避重试的 HTTP POST"""
        last_error = None
        for i in range(retries + 1):
            try:
                req = urllib.request.Request(url, data=data, method="POST")
                if is_json:
                    req.add_header("Content-Type", "application/json; charset=utf-8")
                with urllib.request.urlopen(req, timeout=10) as response:
                    return response.read().decode("utf-8")
            except urllib.error.HTTPError as e:
                last_error = e
                logging.getLogger(__name__).warning(f"HTTP error {e.code} on attempt {i+1}/{retries+1}: {url}")
            except urllib.error.URLError as e:
                last_error = e
                logging.getLogger(__name__).warning(f"URL error on attempt {i+1}/{retries+1}: {e.reason}")
            except Exception as e:
                last_error = e
                logging.getLogger(__name__).warning(f"Request error on attempt {i+1}/{retries+1}: {e}")
            if i < retries:
                time.sleep(2 ** i)
        logging.getLogger(__name__).error(f"All retries failed for {url}: {last_error}")
        return None
    @classmethod
    def send(cls, config: Dict, type_label: str, body_text: str, is_voice: bool = True, async_mode: bool = True):
        """Send push notification (async by default) | 发送推送通知（默认异步）"""
        # Check executor under lock to prevent race with shutdown | 在锁内检查执行器防止关闭竞态
        if not cls._ensure_executor():
            logging.getLogger(__name__).warning("Cannot send: executor is shutdown")
            return

        if async_mode:
            with cls._executor_lock:
                if cls._executor is not None:
                    cls._executor.submit(cls._do_push_logic, config, type_label, body_text, is_voice)
                else:
                    logging.getLogger(__name__).warning("Executor shutdown during send, executing synchronously")
                    cls._do_push_logic(config, type_label, body_text, is_voice)
        else:
            cls._do_push_logic(config, type_label, body_text, is_voice)
    @classmethod
    def shutdown(cls):
        """Gracefully shutdown executor and wait for pending tasks | 优雅关闭执行器并等待待处理任务"""
        # Release lock before shutdown to prevent deadlock | 在关闭前释放锁防止死锁
        executor_to_shutdown = None
        with cls._executor_lock:
            if cls._executor is not None:
                executor_to_shutdown = cls._executor
                cls._executor = None

        # Shutdown outside lock to prevent deadlock | 在锁外关闭防止死锁
        if executor_to_shutdown is not None:
            executor_to_shutdown.shutdown(wait=True)
            logging.getLogger(__name__).info("ThreadPoolExecutor shutdown complete")
