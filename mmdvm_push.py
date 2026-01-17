#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import json
import glob
import re
import urllib.request
import urllib.parse
import sys
import base64
import hmac
import hashlib
import mmap
import subprocess
import atexit
import logging
import tempfile
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from threading import Semaphore, Lock
from typing import Dict, List, Optional, Tuple, Any
from parser import parse_line
from filters import quiet_time, should_push
from notify_fmt import format_message

# =========================
# Global Constants
# =========================
VERSION = "v3.1.7"
CONFIG_FILE = "/etc/mmdvm_push.json"
MMDVM_LOG_DIR = "/var/log/pi-star/"
LOCAL_ID_FILE = "/usr/local/etc/nextionUsers.csv"
LOG_POLL_INTERVAL = 0.2
PUSH_MAX_WORKERS = 3
PUSH_RETRY = 2

# 版本查询快速返回，避免初始化日志等产生额外输出
if len(sys.argv) > 1 and sys.argv[1] == "--version":
    print(VERSION)
    sys.exit(0)

# 动态调整日志目录权限（不向 stdout 打印，后续使用 logger 提示）
APP_LOG_DIR = "/var/log/pi-star/"
if not os.path.exists(APP_LOG_DIR) or not os.access(APP_LOG_DIR, os.W_OK):
    APP_LOG_DIR = tempfile.gettempdir()

logger = None
def setup_logging():
    global logger
    try:
        logging.basicConfig(
            filename=os.path.join(APP_LOG_DIR, 'mmdvm_push.log'),
            level=logging.INFO,
            format='[%(asctime)s] [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    except PermissionError:
        logging.basicConfig(
            level=logging.INFO,
            format='[%(asctime)s] [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s')
    console.setFormatter(formatter)
    logging.getLogger('').addHandler(console)
    logger = logging.getLogger(__name__)
    if APP_LOG_DIR != "/var/log/pi-star/":
        logger.warning(f"No write permission for /var/log/pi-star/. Falling back to {APP_LOG_DIR}")


# =========================
# Config Manager
# =========================
class ConfigManager:
    _config: Dict = {}
    _last_mtime: float = 0
    _check_interval: int = 5
    _last_check_time: float = 0
    _lock = Lock()

    @classmethod
    def get_config(cls) -> Dict:
        now = time.time()
        if now - cls._last_check_time < cls._check_interval:
            return cls._config
        
        with cls._lock:
            # Double-check after acquiring lock
            if now - cls._last_check_time < cls._check_interval:
                return cls._config
            cls._last_check_time = now
            
            if not os.path.exists(CONFIG_FILE):
                return {}
            
            try:
                mtime = os.path.getmtime(CONFIG_FILE)
                if mtime > cls._last_mtime:
                    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                        raw = json.load(f)
                    cls._config = cls._validate_config(raw)
                    cls._last_mtime = mtime
                    logger.debug("Config reloaded")
            except json.JSONDecodeError as e:
                logger.error(f"Config JSON parse error: {e}")
            except OSError as e:
                logger.error(f"Config file read error: {e}")
        
        return cls._config

    @staticmethod
    def parse_list(data) -> List[str]:
        if isinstance(data, list):
            data = ";".join(map(str, data))
        if not data or not isinstance(data, str):
            return []
        return [item.strip().upper() for item in re.split(r'[;；,，\s\n]+', data) if item.strip()]

    @staticmethod
    def _validate_config(raw: Dict) -> Dict:
        defaults = {
            "my_callsign": "",
            "min_duration": 1.0,
            "quiet_mode": {"enabled": False, "start": "23:00", "end": "07:00"},
            "boot_push_enabled": True,
            "temp_alert_enabled": False,
            "temp_threshold": 65.0,
            "temp_interval": 30,
            "temp_unit": "C",
            "push_tg_enabled": False, "tg_token": "", "tg_chat_id": "",
            "push_wx_enabled": False, "wx_token": "",
            "push_fs_enabled": False, "fs_webhook": "", "fs_secret": "",
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
            logger.warning(f"Config sanitize error: {e}")
        return conf


# =========================
# Ham Info Manager (修复后的映射表)
# =========================
class HamInfoManager:
    # 使用类级别的缓存，避免实例方法 lru_cache 问题
    _cache: Dict[str, Dict[str, str]] = {}
    _cache_lock = Lock()
    _max_cache_size = 4096

    def __init__(self, id_file: str):
        self.id_file = id_file
        self._io_lock = Semaphore(4)
        self.geo_map = {
            # 亚洲
            "China": "🇨🇳 中国", "Hong Kong": "🇭🇰 中国香港", "Macao": "🇲🇴 中国澳门", 
            "Taiwan": "🇹🇼 中国台湾", "Japan": "🇯🇵 日本", "Korea": "🇰🇷 韩国", 
            "South Korea": "🇰🇷 韩国", "North Korea": "🇰🇵 朝鲜", "Thailand": "🇹🇭 泰国", 
            "Singapore": "🇸🇬 新加坡", "Malaysia": "🇲🇾 马来西亚", "Indonesia": "🇮🇩 印度尼西亚",
            "Philippines": "🇵🇭 菲律宾", "Vietnam": "🇻🇳 越南", "India": "🇮🇳 印度", 
            "Pakistan": "🇵🇰 巴基斯坦", "Sri Lanka": "🇱🇰 斯里兰卡", "Bangladesh": "🇧🇩 孟加拉国", 
            "Nepal": "🇳🇵 尼泊尔", "Mongolia": "🇲🇳 蒙古",
            # 中东
            "United Arab Emirates": "🇦🇪 阿联酋", "UAE": "🇦🇪 阿联酋", "Saudi Arabia": "🇸🇦 沙特", 
            "Israel": "🇮🇱 以色列", "Turkey": "🇹🇷 土耳其", "Iran": "🇮🇷 伊朗", 
            "Iraq": "🇮🇶 伊拉克", "Kuwait": "🇰🇼 科威特", "Oman": "🇴🇲 阿曼", 
            "Qatar": "🇶🇦 卡塔尔", "Jordan": "🇯🇴 约旦", "Lebanon": "🇱🇧 黎巴嫩",
            "Kazakhstan": "🇰🇿 哈萨克斯坦", "Uzbekistan": "🇺🇿 乌兹别克斯坦",
            # 欧洲 (修复了错误)
            "United Kingdom": "🇬🇧 英国", "UK": "🇬🇧 英国", "Germany": "🇩🇪 德国",
            "France": "🇫🇷 法国", "Italy": "🇮🇹 意大利", "Spain": "🇪🇸 西班牙", 
            "Portugal": "🇵🇹 葡萄牙", "Russia": "🇷🇺 俄罗斯", "Russian Federation": "🇷🇺 俄罗斯", 
            "Netherlands": "🇳🇱 荷兰", "Belgium": "🇧🇪 比利时", "Switzerland": "🇨🇭 瑞士", 
            "Austria": "🇦🇹 奥地利",  # 修复：原来是 🇦ᵗ
            "Sweden": "🇸🇪 瑞典", "Norway": "🇳🇴 挪威", 
            "Denmark": "🇩🇰 丹麦",  # 修复：原来是 🇩麦
            "Finland": "🇫🇮 芬兰", "Poland": "🇵🇱 波兰",
            "Czech Republic": "🇨🇿 捷克", "Czechia": "🇨🇿 捷克", "Hungary": "🇭🇺 匈牙利", 
            "Greece": "🇬🇷 希腊", "Ireland": "🇮🇪 爱尔兰", "Romania": "🇷🇴 罗马尼亚", 
            "Bulgaria": "🇧🇬 保加利亚", "Ukraine": "🇺🇦 乌克兰", "Belarus": "🇧🇾 白俄罗斯",
            "Slovakia": "🇸🇰 斯洛伐克", "Croatia": "🇭🇷 克罗地亚", "Serbia": "🇷🇸 塞尔维亚", 
            "Slovenia": "🇸🇮 斯洛文尼亚", "Estonia": "🇪🇪 爱沙尼亚", "Latvia": "🇱🇻 拉脱维亚", 
            "Lithuania": "🇱🇹 立陶宛", "Iceland": "🇮🇸 冰岛", "Luxembourg": "🇱🇺 卢森堡", 
            "Monaco": "🇲🇨 摩纳哥", "Cyprus": "🇨🇾 塞浦路斯", "Malta": "🇲🇹 马耳他",
            # 美洲
            "United States": "🇺🇸 美国", "USA": "🇺🇸 美国", "Canada": "🇨🇦 加拿大", 
            "Mexico": "🇲🇽 墨西哥", "Cuba": "🇨🇺 古巴", "Jamaica": "🇯🇲 牙买加", 
            "Puerto Rico": "🇵🇷 波多黎各", "Dominican Republic": "🇩🇴 多米尼加",
            "Costa Rica": "🇨🇷 哥斯达黎加", "Panama": "🇵🇦 巴拿马", "Guatemala": "🇬🇹 危地马拉", 
            "Honduras": "🇭🇳 洪都拉斯", "Brazil": "🇧🇷 巴西", "Argentina": "🇦🇷 阿根廷", 
            "Chile": "🇨🇱 智利", "Colombia": "🇨🇴 哥伦比亚", "Peru": "🇵🇪 秘鲁", 
            "Venezuela": "🇻🇪 委内瑞拉", "Uruguay": "🇺🇾 乌拉圭", "Paraguay": "🇵🇾 巴拉圭",
            "Ecuador": "🇪🇨 厄瓜多尔", "Bolivia": "🇧🇴 玻利维亚",
            # 大洋洲
            "Australia": "🇦🇺 澳大利亚", "New Zealand": "🇳🇿 新西兰", "Fiji": "🇫🇯 斐济", 
            "Papua New Guinea": "🇵🇬 巴布亚新几内亚",
            # 非洲 (修复摩洛哥)
            "South Africa": "🇿🇦 南非", "Egypt": "🇪🇬 埃及", "Nigeria": "🇳🇬 尼日利亚", 
            "Kenya": "🇰🇪 肯尼亚", 
            "Morocco": "🇲🇦 摩洛哥",  # 修复：原来写成了摩纳哥
            "Algeria": "🇩🇿 阿尔及利亚", "Ethiopia": "🇪🇹 埃塞俄比亚", "Ghana": "🇬🇭 加纳",
            "Tanzania": "🇹🇿 坦桑尼亚", "Uganda": "🇺🇬 乌干达", "Mauritius": "🇲🇺 毛里求斯", 
            "Seychelles": "🇸🇨 塞舌尔"
        }

    def get_info(self, callsign: str) -> Dict[str, str]:
        """获取呼号信息，带手动缓存管理"""
        # 检查缓存
        with self._cache_lock:
            if callsign in self._cache:
                return self._cache[callsign]
        
        result = self._fetch_info(callsign)
        
        # 更新缓存
        with self._cache_lock:
            # 简单的 LRU：如果超过最大大小，清除一半
            if len(self._cache) >= self._max_cache_size:
                keys_to_remove = list(self._cache.keys())[:self._max_cache_size // 2]
                for k in keys_to_remove:
                    del self._cache[k]
            self._cache[callsign] = result
        
        return result

    def _fetch_info(self, callsign: str) -> Dict[str, str]:
        """实际从文件获取信息"""
        default_result = {"name": "", "loc": "Unknown"}
        
        if not os.path.exists(self.id_file):
            return default_result
        
        if not self._io_lock.acquire(timeout=2):
            logger.warning(f"IO lock timeout for callsign: {callsign}")
            return default_result
        
        try:
            file_size = os.path.getsize(self.id_file)
            if file_size == 0:
                return default_result
                
            with open(self.id_file, 'rb') as f:
                with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                    query = f",{callsign},".encode('utf-8')
                    idx = mm.find(query)
                    if idx == -1:
                        return default_result
                    
                    start = mm.rfind(b'\n', 0, idx) + 1
                    end = mm.find(b'\n', idx)
                    if end == -1:
                        end = len(mm)
                    line_bytes = mm[start:end]
                    
                    try:
                        line = line_bytes.decode('utf-8')
                    except UnicodeDecodeError:
                        line = line_bytes.decode('gb18030', errors='ignore')
                    
                    parts = line.split(',')
                    first_name = parts[2].strip() if len(parts) > 2 else ""
                    last_name = parts[3].strip() if len(parts) > 3 else ""
                    city = parts[4].strip().title() if len(parts) > 4 else ""
                    state = parts[5].strip().upper() if len(parts) > 5 else ""
                    country = parts[6].strip() if len(parts) > 6 else ""
                    
                    # 国家名称映射
                    if any('\u4e00' <= char <= '\u9fff' for char in country):
                        for k, v in self.geo_map.items():
                            if k in country or (len(v.split()) > 1 and v.split()[1] in country):
                                country = v
                                break
                    else:
                        country = self.geo_map.get(country, country)
                    
                    full_name = f"{first_name} {last_name}".strip().upper()
                    name_part = f" ({full_name})" if full_name else ""
                    loc = f"{city}, {state} ({country})" if city or state else country
                    
                    return {"name": name_part, "loc": loc}
                    
        except (OSError, ValueError) as e:
            logger.debug(f"Error fetching info for {callsign}: {e}")
            return default_result
        finally:
            self._io_lock.release()


# =========================
# Push Service
# =========================
class PushService:
    _max_workers = PUSH_MAX_WORKERS
    _executor: Optional[ThreadPoolExecutor] = None
    _push_semaphore = Semaphore(_max_workers)
    _initialized = False

    @classmethod
    def _ensure_executor(cls):
        if cls._executor is None:
            cls._executor = ThreadPoolExecutor(max_workers=cls._max_workers)
            cls._initialized = True

    @staticmethod
    def get_fs_sign(secret: str, timestamp: str) -> str:
        string_to_sign = f'{timestamp}\n{secret}'
        hmac_code = hmac.new(
            string_to_sign.encode("utf-8"), 
            digestmod=hashlib.sha256
        ).digest()
        return base64.b64encode(hmac_code).decode('utf-8')

    @classmethod
    def _do_push_logic(cls, config: Dict, type_label: str, body_text: str, is_voice: bool):
        # Remove redundant semaphore if executor already limits concurrency, 
        # but keep it if we want to limit active push executions specifically.
        # Given max_workers=3 in executor, this semaphore is redundant but harmless.
        # Refactored for clarity.
        
        # 1. Feishu
        if config.get('push_fs_enabled') and config.get('fs_webhook'):
            cls._push_feishu(config, type_label, body_text, is_voice)

        # 2. WeChat (PushPlus)
        if config.get('push_wx_enabled') and config.get('wx_token'):
            cls._push_wechat(config, type_label, body_text)

        # 3. Telegram
        if config.get('push_tg_enabled') and config.get('tg_token') and config.get('tg_chat_id'):
            cls._push_telegram(config, type_label, body_text)

    @classmethod
    def _push_feishu(cls, config: Dict, type_label: str, body_text: str, is_voice: bool):
        try:
            ts = str(int(time.time()))
            template = "blue" if is_voice else ("orange" if "上线" in type_label else "green")
            fs_payload = {
                "msg_type": "interactive",
                "card": {
                    "header": {
                        "title": {"tag": "plain_text", "content": type_label},
                        "template": template
                    },
                    "elements": [{
                        "tag": "div",
                        "text": {"tag": "lark_md", "content": body_text}
                    }]
                }
            }
            if config.get('fs_secret'):
                fs_payload["timestamp"] = ts
                fs_payload["sign"] = cls.get_fs_sign(config['fs_secret'], ts)
            
            cls.post_with_retry(
                config['fs_webhook'],
                data=json.dumps(fs_payload).encode('utf-8'),
                is_json=True
            )
        except Exception as e:
            logger.error(f"Feishu push failed: {e}")

    @classmethod
    def _push_wechat(cls, config: Dict, type_label: str, body_text: str):
        try:
            br = "<br>"
            html_content = f"<b>{type_label}</b>{br}{br}{br.join(body_text.splitlines())}"
            payload = {
                "token": config['wx_token'],
                "title": type_label,
                "content": html_content,
                "template": "html"
            }
            cls.post_with_retry(
                "http://www.pushplus.plus/send",
                data=json.dumps(payload).encode('utf-8'),
                is_json=True
            )
        except Exception as e:
            logger.error(f"WeChat push failed: {e}")

    @classmethod
    def _push_telegram(cls, config: Dict, type_label: str, body_text: str):
        try:
            text = f"<b>{type_label}</b>\n\n{body_text}"
            url = f"https://api.telegram.org/bot{config['tg_token']}/sendMessage"
            data = urllib.parse.urlencode({
                "chat_id": config['tg_chat_id'],
                "text": text,
                "parse_mode": "HTML"
            }).encode('utf-8')
            cls.post_with_retry(url, data=data)
        except Exception as e:
            logger.error(f"Telegram push failed: {e}")

    @classmethod
    def post_with_retry(cls, url: str, data: bytes = None, is_json: bool = False, 
                        retries: int = PUSH_RETRY) -> Optional[str]:
        last_error = None
        for i in range(retries + 1):
            try:
                req = urllib.request.Request(url, data=data, method='POST')
                if is_json:
                    req.add_header('Content-Type', 'application/json; charset=utf-8')
                with urllib.request.urlopen(req, timeout=10) as response:
                    return response.read().decode('utf-8')
            except urllib.error.HTTPError as e:
                last_error = e
                logger.warning(f"HTTP error {e.code} on attempt {i+1}/{retries+1}: {url}")
            except urllib.error.URLError as e:
                last_error = e
                logger.warning(f"URL error on attempt {i+1}/{retries+1}: {e.reason}")
            except Exception as e:
                last_error = e
                logger.warning(f"Request error on attempt {i+1}/{retries+1}: {e}")
            
            if i < retries:
                time.sleep(2 ** i)  # 指数退避
        
        logger.error(f"All retries failed for {url}: {last_error}")
        return None

    @classmethod
    def send(cls, config: Dict, type_label: str, body_text: str, 
             is_voice: bool = True, async_mode: bool = True):
        cls._ensure_executor()
        if async_mode:
            cls._executor.submit(cls._do_push_logic, config, type_label, body_text, is_voice)
        else:
            cls._do_push_logic(config, type_label, body_text, is_voice)

    @classmethod
    def shutdown(cls):
        if cls._executor is not None:
            cls._executor.shutdown(wait=True)
            cls._executor = None


atexit.register(PushService.shutdown)


# =========================
# Monitor Logic
# =========================
class MMDVMMonitor:
    def __init__(self):
        self.last_msg: Dict[str, Any] = {"call": "", "ts": 0}
        self.last_temp_alert_time: float = 0
        self.last_temp_check_time: float = 0
        self.ham_manager = HamInfoManager(LOCAL_ID_FILE)
        self._cpu_prev_total = None
        self._cpu_prev_idle = None
        self.last_activity_ts: float = 0.0
        

    def _cpu_percent_proc(self) -> str:
        try:
            with open("/proc/stat", "r") as f:
                parts = f.readline().split()
            if not parts or parts[0] != "cpu":
                return "0"
            nums = [int(x) for x in parts[1:]]
            user = nums[0] if len(nums) > 0 else 0
            nice = nums[1] if len(nums) > 1 else 0
            system = nums[2] if len(nums) > 2 else 0
            idle = nums[3] if len(nums) > 3 else 0
            iowait = nums[4] if len(nums) > 4 else 0
            irq = nums[5] if len(nums) > 5 else 0
            softirq = nums[6] if len(nums) > 6 else 0
            steal = nums[7] if len(nums) > 7 else 0
            idleall = idle + iowait
            nonidle = user + nice + system + irq + softirq + steal
            total = idleall + nonidle
            prev_total = self._cpu_prev_total
            prev_idle = self._cpu_prev_idle
            if prev_total is None or prev_idle is None:
                import time as _t
                _t.sleep(0.5)
                with open("/proc/stat", "r") as f2:
                    parts2 = f2.readline().split()
                if not parts2 or parts2[0] != "cpu":
                    return "0"
                nums2 = [int(x) for x in parts2[1:]]
                user2 = nums2[0] if len(nums2) > 0 else 0
                nice2 = nums2[1] if len(nums2) > 1 else 0
                system2 = nums2[2] if len(nums2) > 2 else 0
                idle2 = nums2[3] if len(nums2) > 3 else 0
                iowait2 = nums2[4] if len(nums2) > 4 else 0
                irq2 = nums2[5] if len(nums2) > 5 else 0
                softirq2 = nums2[6] if len(nums2) > 6 else 0
                steal2 = nums2[7] if len(nums2) > 7 else 0
                idleall2 = idle2 + iowait2
                nonidle2 = user2 + nice2 + system2 + irq2 + softirq2 + steal2
                total2 = idleall2 + nonidle2
                totald_i = total2 - total
                idled_i = idleall2 - idleall
                self._cpu_prev_total = total2
                self._cpu_prev_idle = idleall2
                pct_i = 0.0 if totald_i <= 0 else (totald_i - idled_i) * 100.0 / totald_i
                if pct_i < 0.0:
                    pct_i = 0.0
                if pct_i > 100.0:
                    pct_i = 100.0
                return f"{pct_i:.1f}"
            self._cpu_prev_total = total
            self._cpu_prev_idle = idleall
            totald = total - prev_total
            idled = idleall - prev_idle
            pct = 0.0 if totald <= 0 else (totald - idled) * 100.0 / totald
            if pct < 0.0:
                pct = 0.0
            if pct > 100.0:
                pct = 100.0
            return f"{pct:.1f}"
        except Exception:
            return "0"

    def _cpu_percent_process(self, interval: float = 0.5) -> str:
        try:
            import time as _t
            pid = os.getpid()
            with open("/proc/stat", "r") as f:
                parts = f.readline().split()
            if not parts or parts[0] != "cpu":
                return "0"
            total1 = sum(int(x) for x in parts[1:])
            with open(f"/proc/{pid}/stat", "r") as f2:
                p1 = f2.read().split()
            if len(p1) < 17:
                return "0"
            utime1 = int(p1[13]); stime1 = int(p1[14])
            _t.sleep(interval)
            with open("/proc/stat", "r") as f:
                parts = f.readline().split()
            if not parts or parts[0] != "cpu":
                return "0"
            total2 = sum(int(x) for x in parts[1:])
            with open(f"/proc/{pid}/stat", "r") as f2:
                p2 = f2.read().split()
            if len(p2) < 17:
                return "0"
            utime2 = int(p2[13]); stime2 = int(p2[14])
            delta_proc = (utime2 + stime2) - (utime1 + stime1)
            delta_total = total2 - total1
            pct = 0.0 if delta_total <= 0 else (delta_proc * 100.0 / delta_total)
            if pct < 0.0:
                pct = 0.0
            if pct > 100.0:
                pct = 100.0
            return f"{pct:.1f}"
        except Exception:
            return "0"

    def _proc_mem_rss_kb(self) -> str:
        try:
            pid = os.getpid()
            with open(f"/proc/{pid}/status", "r") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        parts = line.split()
                        return parts[1] if len(parts) >= 2 else "0"
            return "0"
        except Exception:
            return "0"

    def _mem_percent_proc(self) -> str:
        mt = ma = None
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    mt = float(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    ma = float(line.split()[1])
                if mt is not None and ma is not None:
                    break
        if mt and ma:
            used = (mt - ma) / mt * 100.0
            return f"{used:.1f}%"
        return "0%"

    def get_sys_info(self) -> Tuple[str, str, str]:
        try:
            ip = subprocess.getoutput("hostname -I").split()[0]
        except (IndexError, Exception):
            ip = "Unknown"
        try:
            cpu = self._cpu_percent_proc()
        except Exception:
            try:
                cpu = subprocess.getoutput("top -bn1 | grep 'Cpu(s)' | awk '{print $2+$4}'").strip()
            except Exception:
                cpu = "0"
        try:
            mem = self._mem_percent_proc()
        except Exception:
            try:
                mem = subprocess.getoutput("free -m | awk 'NR==2{printf \"%.1f%%\", $3*100/$2 }'").strip()
            except Exception:
                mem = "0%"
        return ip, cpu, mem

    def get_current_temp(self, conf: Dict) -> Tuple[str, float]:
        try:
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                temp_c = float(f.read().strip()) / 1000.0
            unit = conf.get('temp_unit', 'C').upper()
            val = (temp_c * 9/5) + 32 if unit == 'F' else temp_c
            return f"{val:.1f}°{unit}", val
        except (FileNotFoundError, ValueError, OSError):
            return "N/A", 0.0

    def check_temp_alert(self, conf: Dict):
        if not conf.get('temp_alert_enabled'):
            return
        
        now = time.time()
        if now - self.last_temp_check_time < 60:
            return
        self.last_temp_check_time = now
        
        display_str, current_val = self.get_current_temp(conf)
        threshold = float(conf.get('temp_threshold', 65.0))
        
        if current_val >= threshold:
            interval_sec = int(conf.get('temp_interval', 30)) * 60
            if now - self.last_temp_alert_time > interval_sec:
                self.last_temp_alert_time = now
                lang = (conf.get('ui_lang', 'cn') or 'cn').lower()
                if lang == 'en':
                    alert_body = (
                        f"🚨 <b>High Temperature Alert</b>\n"
                        f"🔥 <b>Current Temp</b>: {display_str}\n"
                        f"⚠️ <b>Threshold</b>: {threshold:.1f}°{conf.get('temp_unit', 'C')}\n"
                        f"⏰ <b>Time</b>: {datetime.now().strftime('%H:%M:%S')}"
                    )
                    PushService.send(conf, "🌡️ Hardware Status Warning", alert_body, is_voice=False)
                else:
                    alert_body = (
                        f"🚨 <b>硬件高温预警</b>\n"
                        f"🔥 <b>当前温度</b>: {display_str}\n"
                        f"⚠️ <b>预警阈值</b>: {threshold:.1f}°{conf.get('temp_unit', 'C')}\n"
                        f"⏰ <b>检测时间</b>: {datetime.now().strftime('%H:%M:%S')}"
                    )
                    PushService.send(conf, "🌡️ 硬件状态警告", alert_body, is_voice=False)

    def get_latest_log(self) -> Optional[str]:
        try:
            # Optimization: Check today's log first to avoid glob overhead
            today = datetime.now().strftime("%Y-%m-%d")
            today_log = os.path.join(MMDVM_LOG_DIR, f"MMDVM-{today}.log")
            if os.path.exists(today_log) and os.path.getsize(today_log) > 0:
                return today_log

            log_files = [
                f for f in glob.glob(os.path.join(MMDVM_LOG_DIR, "MMDVM-*.log"))
                if os.path.isfile(f) and os.path.getsize(f) > 0
            ]
            return max(log_files, key=os.path.getmtime) if log_files else None
        except (OSError, ValueError):
            return None

    def check_network(self, max_attempts: int = 30, interval: float = 2) -> bool:
        """检查网络连通性"""
        logger.info("正在进入冷启动网络探测循环...")
        
        for i in range(max_attempts):
            try:
                ip_check = subprocess.getoutput("hostname -I").strip()
                if ip_check and not ip_check.startswith("127."):
                    urllib.request.urlopen(
                        "http://www.apple.com/library/test/success.html",
                        timeout=3
                    )
                    logger.info(f"网络就绪 (尝试 {i+1})")
                    return True
            except Exception:
                pass
            time.sleep(interval)
        
        logger.warning("网络探测超时")
        return False

    def run(self):
        conf = ConfigManager.get_config()
        network_ok = self.check_network()
        
        if conf.get('boot_push_enabled', True):
            ip, cpu, mem = self.get_sys_info()
            temp_str, _ = self.get_current_temp(conf)
            lang = (conf.get('ui_lang', 'cn') or 'cn').lower()
            if lang == 'en':
                status = "✅ Online" if network_ok else "⚠️ Packet loss/timeout"
                body = (
                    f"🚀 <b>Device Online</b> ({VERSION})\n"
                    f"🌐 <b>Network</b>: {status}\n"
                    f"🛠️ <b>Admin IP</b>: {ip}\n"
                    f"🌡️ <b>System Temp</b>: {temp_str}\n"
                    f"📊 <b>CPU</b>: {cpu}%\n"
                    f"💾 <b>Memory</b>: {mem}\n"
                    f"⏰ <b>Time</b>: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
                PushService.send(conf, "⚙️ Boot Notice", body, is_voice=False, async_mode=False)
            else:
                status = "✅ 连通" if network_ok else "⚠️ 丢包/超时"
                body = (
                    f"🚀 <b>设备已上线</b> ({VERSION})\n"
                    f"🌐 <b>网络状态</b>: {status}\n"
                    f"🛠️ <b>管理IP</b>: {ip}\n"
                    f"🌡️ <b>系统温度</b>: {temp_str}\n"
                    f"📊 <b>CPU占用</b>: {cpu}%\n"
                    f"💾 <b>内存占用</b>: {mem}\n"
                    f"⏰ <b>时间</b>: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                )
                PushService.send(conf, "⚙️ 系统启动通知", body, is_voice=False, async_mode=False)

        logger.info(f"{VERSION} 监控就绪，正在监听日志行...")
        
        while True:
            try:
                current_log = self.get_latest_log()
                if not current_log:
                    time.sleep(5)
                    continue
                
                self._tail_log(current_log)
                
            except KeyboardInterrupt:
                logger.info("收到中断信号，正在退出...")
                break
            except Exception as e:
                logger.error(f"循环异常: {e}")
                time.sleep(5)

    def _tail_log(self, log_file: str):
        """持续读取日志文件"""
        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(0, 2)  # 移到文件末尾
                last_check = time.time()
                
                while True:
                    # 定期检查是否有新日志文件
                    if time.time() - last_check > 5:
                        new_log = self.get_latest_log()
                        if new_log and new_log != log_file:
                            logger.info(f"切换到新日志: {new_log}")
                            return  # 退出当前循环，让外层重新打开新文件
                        last_check = time.time()
                    
                    line = f.readline()
                    if not line:
                        interval = 0.2 if (time.time() - self.last_activity_ts) < 60 else 0.8
                        time.sleep(interval)
                        continue
                    
                    self.process_line(line)
                    
        except FileNotFoundError:
            logger.warning(f"日志文件不存在: {log_file}")
        except PermissionError:
            logger.error(f"无权限读取日志: {log_file}")

    def process_line(self, line: str):
        event = parse_line(line)
        if not event:
            return
        conf = ConfigManager.get_config()
        self.check_temp_alert(conf)
        if quiet_time(conf):
            return
        if not should_push(conf, event, self.last_msg):
            return
        curr_ts = time.time()
        self.last_msg.update({"call": event['call'], "ts": curr_ts})
        info = self.ham_manager.get_info(event['call'])
        temp_str, _ = self.get_current_temp(conf)
        type_label, body = format_message(conf, event, temp_str, info)
        self.last_activity_ts = time.time()
        PushService.send(conf, type_label, body, is_voice=event['is_voice'])
        logger.info(f"推送完成: {event['call']} -> {event['target']}")


# =========================
# Entry
# =========================
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--version":
        print(VERSION)
        sys.exit(0)
    
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        setup_logging()
        monitor = MMDVMMonitor()
        conf = ConfigManager.get_config()
        ip, cpu, mem = monitor.get_sys_info()
        temp_str, _ = monitor.get_current_temp(conf)
        lang = (conf.get('ui_lang', 'cn') or 'cn').lower()
        if lang == 'en':
            test_body = (
                f"Channel test success ({VERSION})\n"
                f"🌐 <b>IP</b>: {ip}\n"
                f"🌡️ <b>Temp</b>: {temp_str}\n"
                f"📊 <b>CPU</b>: {cpu}%\n"
                f"💾 <b>Memory</b>: {mem}\n"
                f"⏰ <b>Time</b>: {datetime.now().strftime('%H:%M:%S')}"
            )
            PushService.send(conf, "🔔 Test Notification", test_body, is_voice=False, async_mode=False)
        else:
            test_body = (
                f"通道测试成功 ({VERSION})\n"
                f"🌐 <b>IP</b>: {ip}\n"
                f"🌡️ <b>温度</b>: {temp_str}\n"
                f"📊 <b>CPU</b>: {cpu}%\n"
                f"💾 <b>内存</b>: {mem}\n"
                f"⏰ <b>时间</b>: {datetime.now().strftime('%H:%M:%S')}"
            )
            PushService.send(conf, "🔔 测试推送", test_body, is_voice=False, async_mode=False)
        print("Success")
    elif len(sys.argv) > 1 and sys.argv[1] == "--health":
        conf = ConfigManager.get_config()
        mon = MMDVMMonitor()
        ip, cpu_sys, mem_sys = mon.get_sys_info()
        cpu_proc = mon._cpu_percent_process()
        rss_kb = mon._proc_mem_rss_kb()
        status = {
            "version": VERSION,
            "app_log_dir": APP_LOG_DIR,
            "app_log_writable": os.access(APP_LOG_DIR, os.W_OK),
            "mmdvm_log_dir": MMDVM_LOG_DIR,
            "mmdvm_log_exists": os.path.exists(MMDVM_LOG_DIR),
            "config_exists": os.path.exists(CONFIG_FILE),
            "config_valid": isinstance(conf, dict) and len(conf) > 0,
            "ip": ip,
            "cpu_system": f"{cpu_sys}%",
            "cpu_process": f"{cpu_proc}%",
            "mem": mem_sys,
            "mem_rss_kb": rss_kb,
            "time": datetime.now().isoformat(timespec="seconds")
        }
        print(json.dumps(status, ensure_ascii=False))
    else:
        setup_logging()
        monitor = MMDVMMonitor()
        # 简单就绪等待：日志目录存在 + 获取 IP 成功
        start_t = time.time()
        for i in range(10):
            try:
                _ip = subprocess.getoutput("hostname -I").split()[0]
            except Exception:
                _ip = ""
            if os.path.exists(MMDVM_LOG_DIR) and _ip:
                break
            time.sleep(2)
        monitor.run()
