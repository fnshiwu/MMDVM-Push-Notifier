import os
import time
import json
import logging
from threading import Lock
from typing import Dict

class ConfigManager:
    _config: Dict = {}
    _last_mtime: float = 0.0
    _check_interval: int = 5
    _last_check_time: float = 0.0
    _lock = Lock()
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
            conf["temp_threshold"] = float(conf.get("temp_threshold", defaults["temp_threshold"]))
            conf["temp_interval"] = int(conf.get("temp_interval", defaults["temp_interval"]))
            unit = str(conf.get("temp_unit", "C")).upper()
            conf["temp_unit"] = "F" if unit == "F" else "C"
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
        now = time.time()
        if now - cls._last_check_time < cls._check_interval:
            return cls._config
        with cls._lock:
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
            except json.JSONDecodeError as e:
                logging.getLogger(__name__).error(f"Config JSON parse error: {e}")
            except OSError as e:
                logging.getLogger(__name__).error(f"Config file read error: {e}")
            return cls._config
