import os
import time
import json
import logging
import urllib.parse
from threading import Lock
from typing import Dict

class ConfigManager:
    _config: Dict = {}
    _last_mtime: float = 0.0
    _check_interval: int = 30  # 从5秒优化为30秒
    _last_check_time: float = 0.0
    _lock = Lock()

    @staticmethod
    def _validate_url(url: str) -> str:
        """Validate URL format | 验证 URL 格式"""
        if not url:
            return ""
        try:
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme not in ('http', 'https'):
                logging.getLogger(__name__).warning(f"Invalid URL scheme: {parsed.scheme}, URL: {url}")
                return ""
            if not parsed.netloc:
                logging.getLogger(__name__).warning(f"Invalid URL (no host): {url}")
                return ""
            return url
        except Exception as e:
            logging.getLogger(__name__).warning(f"URL validation failed: {e}")
            return ""

    @staticmethod
    def _validate_token(token: str, min_length: int = 10) -> str:
        """Validate token format | 验证 token 格式"""
        if not token:
            return ""
        token = str(token).strip()
        if len(token) < min_length:
            logging.getLogger(__name__).warning(f"Token too short (< {min_length} chars)")
            return ""
        return token

    @classmethod
    def _validate_config(cls, raw: Dict) -> Dict:
        defaults = {
            "my_callsign": "",
            "min_duration": 4.0,
            "quiet_mode": {"enabled": False, "start": "23:00", "end": "07:00"},
            "push_fs_enabled": False, "fs_webhook": "", "fs_secret": "",
            "push_wx_enabled": False, "wx_token": "",
            "push_tg_enabled": False, "tg_token": "", "tg_chat_id": "",
            "boot_push_enabled": True,
            "temp_alert_enabled": True,
            "temp_threshold": 65.0,
            "temp_interval": 30,
            "temp_unit": "C",
            "ignore_list": "", "focus_list": "", "ui_lang": "cn"
        }
        conf = dict(defaults)
        if isinstance(raw, dict):
            conf.update(raw)
        try:
            conf["min_duration"] = max(0.1, float(conf.get("min_duration", defaults["min_duration"])))
            conf["temp_threshold"] = max(0.0, min(150.0, float(conf.get("temp_threshold", defaults["temp_threshold"]))))
            conf["temp_interval"] = max(10, int(conf.get("temp_interval", defaults["temp_interval"])))
            unit = str(conf.get("temp_unit", "C")).upper()
            conf["temp_unit"] = "F" if unit == "F" else "C"

            # Validate URLs and tokens
            conf["fs_webhook"] = cls._validate_url(conf.get("fs_webhook", ""))
            conf["wx_token"] = cls._validate_token(conf.get("wx_token", ""), min_length=10)
            conf["tg_token"] = cls._validate_token(conf.get("tg_token", ""), min_length=20)

            qm = conf.get("quiet_mode", defaults["quiet_mode"])
            conf["quiet_mode"] = {
                "enabled": bool(qm.get("enabled", False)),
                "start": qm.get("start", "23:00"),
                "end": qm.get("end", "07:00")
            }
        except Exception as e:
            logging.getLogger(__name__).warning(f"Config sanitize error: {e}")
        return conf
    @classmethod
    def get_config(cls, path: str = "/etc/mmdvm_push.json") -> Dict:
        """Get configuration with thread-safe reload (HIGH #7 fix)"""
        now = time.time()

        # Fast path: return cached config if still valid (no lock needed)
        if now - cls._last_check_time < cls._check_interval:
            return cls._config

        # Slow path: acquire lock and check again
        with cls._lock:
            # Re-check under lock to avoid redundant reads
            if now - cls._last_check_time < cls._check_interval:
                return cls._config

            cls._last_check_time = now

            if not os.path.exists(path):
                return cls._config

            try:
                mtime = os.path.getmtime(path)
                if mtime > cls._last_mtime:
                    with open(path, "r", encoding="utf-8") as f:
                        raw = json.load(f)
                    cls._config = cls._validate_config(raw)
                    cls._last_mtime = mtime
                    logging.getLogger(__name__).info(f"Config reloaded from {path}")
            except json.JSONDecodeError as e:
                logging.getLogger(__name__).error(f"Config JSON parse error: {e}")
            except OSError as e:
                logging.getLogger(__name__).error(f"Config file read error: {e}")

            return cls._config
