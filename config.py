import os
import time
import json
import math
import logging
import urllib.parse
from threading import Lock
from typing import Dict
from copy import deepcopy

# Global constants | 全局常量
PUSH_MAX_WORKERS = 3  # Maximum push worker threads | 最大推送工作线程数
PUSH_RETRY = 2  # Number of push retries | 推送重试次数
PUSH_MAX_QUEUE = 64  # Max queued notifications before dropping | 队列上限，超出即丢弃
PUSH_TIME_BUDGET = 25.0  # Hard wall-clock budget per channel (seconds) | 单渠道总耗时上限

CONFIG_PATH = os.environ.get("MMDVM_PUSH_CONFIG", "/etc/mmdvm_push.json")

# 默认日志目录候选（Pi-Star 4.2.x / 4.3.x 均为 /var/log/pi-star）
DEFAULT_LOG_DIR = "/var/log/pi-star"


def _num(value, default, lo=None, hi=None):
    """Convert to float with a default and optional clamp | 转 float，失败回落默认值"""
    try:
        val = float(value)
    except (TypeError, ValueError):
        return float(default)
    # NaN/Inf are valid floats but break int() and arithmetic comparisons.
    # NaN/Inf 虽是合法 float，却会让 int() 抛错或让比较永远为假，必须在这里拦下。
    if not math.isfinite(val):
        return float(default)
    if lo is not None:
        val = max(lo, val)
    if hi is not None:
        val = min(hi, val)
    return val


class ConfigManager:
    """Configuration manager with hot-reload support | 支持热重载的配置管理器"""
    _config: Dict = {}
    _last_mtime: float = 0.0
    _check_interval: int = 30  # Check interval in seconds | 检查间隔（秒）
    _last_check_time: float = 0.0
    _lock = Lock()  # Thread-safe lock | 线程安全锁

    @staticmethod
    def _validate_url(url: str) -> str:
        """Validate URL format | 验证 URL 格式"""
        if not url:
            return ""
        try:
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme not in ('http', 'https'):
                logging.getLogger(__name__).warning(
                    "Invalid URL scheme: %s, URL: %s", parsed.scheme, url)
                return ""
            if not parsed.netloc:
                logging.getLogger(__name__).warning("Invalid URL (no host): %s", url)
                return ""
            return url
        except Exception as e:
            logging.getLogger(__name__).warning("URL validation failed: %s", e)
            return ""

    @staticmethod
    def _validate_token(token: str, min_length: int = 10) -> str:
        """Validate token format | 验证 token 格式"""
        if not token:
            return ""
        token = str(token).strip().strip("\"'")
        if len(token) < min_length:
            logging.getLogger(__name__).warning("Token too short (< %s chars)", min_length)
            return ""
        return token

    @staticmethod
    def _validate_callsign(value: str) -> str:
        """Normalise callsign (upper case, no spaces, SSID kept) | 规范化呼号"""
        value = str(value or "").strip().upper().replace(" ", "")
        # keep A-Z 0-9 / - only
        cleaned = "".join(ch for ch in value if ch.isalnum() or ch in "/-")
        return cleaned

    @staticmethod
    def _validate_log_dir(value: str) -> str:
        """Accept an absolute path only | 只接受绝对路径"""
        value = str(value or "").strip()
        if not value:
            return ""
        if not value.startswith("/"):
            logging.getLogger(__name__).warning("log_dir must be absolute: %s", value)
            return ""
        return value.rstrip("/") or "/"

    @classmethod
    def _validate_config(cls, raw: Dict) -> Dict:
        """
        Validate and sanitize configuration
        验证并清洗配置
        """
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
            "temp_interval": 30,  # Minutes in JSON, seconds in memory | JSON 中为分钟
            "temp_hysteresis": 3.0,  # Cooling needed to re-arm an alert | 告警复位迟滞
            "temp_unit": "C",
            "ignore_list": "", "focus_list": "", "ui_lang": "cn",
            "log_dir": "",       # Empty = auto detect | 留空为自动探测
            "dedup_window": 3.0  # Duplicate suppression window in seconds
        }

        # Merge with defaults
        conf = dict(defaults)
        if isinstance(raw, dict):
            conf.update(raw)

        try:
            # Each field is converted independently: one bad value must not skip
            # the validation of everything after it.
            # 每个字段独立转换：单个坏值不应让后续字段全部跳过校验。
            conf["min_duration"] = _num(conf.get("min_duration"), defaults["min_duration"], lo=0.1)
            conf["temp_threshold"] = _num(conf.get("temp_threshold"), defaults["temp_threshold"],
                                          lo=0.0, hi=150.0)
            conf["dedup_window"] = _num(conf.get("dedup_window"), defaults["dedup_window"],
                                        lo=0.0, hi=60.0)
            conf["temp_hysteresis"] = _num(conf.get("temp_hysteresis"), defaults["temp_hysteresis"],
                                           lo=0.5, hi=20.0)

            # === Unit Conversion: Web UI inputs Minutes, backend needs Seconds ===
            # Web UI 输入为分钟，后端需要转换为秒。
            raw_interval = int(_num(conf.get("temp_interval"), defaults["temp_interval"]))
            # Enforce minimum 1 minute (60 seconds)
            conf["temp_interval"] = max(1, raw_interval) * 60

            # Unit normalization
            unit = str(conf.get("temp_unit", "C")).upper()
            conf["temp_unit"] = "F" if unit == "F" else "C"

            # Language whitelist
            lang = str(conf.get("ui_lang", "cn")).lower()
            conf["ui_lang"] = "en" if lang == "en" else "cn"

            # Validate URLs and tokens
            conf["fs_webhook"] = cls._validate_url(conf.get("fs_webhook", ""))
            conf["wx_token"] = cls._validate_token(conf.get("wx_token", ""), min_length=10)
            conf["tg_token"] = cls._validate_token(conf.get("tg_token", ""), min_length=20)
            conf["tg_chat_id"] = str(conf.get("tg_chat_id", "") or "").strip()

            # Callsign / log dir
            conf["my_callsign"] = cls._validate_callsign(conf.get("my_callsign", ""))
            conf["log_dir"] = cls._validate_log_dir(conf.get("log_dir", ""))

            # Quiet mode structure check
            qm = conf.get("quiet_mode", defaults["quiet_mode"])
            if not isinstance(qm, dict):
                qm = defaults["quiet_mode"]
            conf["quiet_mode"] = {
                "enabled": bool(qm.get("enabled", False)),
                "start": str(qm.get("start", "23:00")),
                "end": str(qm.get("end", "07:00"))
            }

        except Exception as e:
            logging.getLogger(__name__).warning("Config sanitize error: %s", e)
            if "temp_interval" not in conf:
                conf["temp_interval"] = 1800  # 30 mins * 60

        return conf

    @classmethod
    def get_config(cls, path: str = None) -> Dict:
        """Get configuration with thread-safe reload | 线程安全地获取配置（支持热重载）"""
        path = path or CONFIG_PATH
        now = time.time()

        with cls._lock:
            # Check under lock to avoid redundant reads
            if now - cls._last_check_time < cls._check_interval:
                return deepcopy(cls._config)

            cls._last_check_time = now

            if not os.path.exists(path):
                if not cls._config:
                    cls._config = cls._validate_config({})
                return deepcopy(cls._config)

            try:
                mtime = os.path.getmtime(path)
                if mtime > cls._last_mtime:
                    with open(path, "r", encoding="utf-8") as f:
                        raw = json.load(f)
                    cls._config = cls._validate_config(raw)
                    cls._last_mtime = mtime
                    logging.getLogger(__name__).info("Config reloaded from %s", path)
            except json.JSONDecodeError as e:
                logging.getLogger(__name__).error(
                    "Config JSON parse error in %s: %s. Using previous configuration.", path, e)
                if not cls._config:
                    cls._config = cls._validate_config({})
            except OSError as e:
                logging.getLogger(__name__).error("Config file read error: %s", e)

            return deepcopy(cls._config)
