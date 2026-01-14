#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MMDVM Push Monitor
Designed as a long-running daemon-grade service.
"""

import os
import time
import json
import glob
import re
import sys
import base64
import hmac
import hashlib
import mmap
import subprocess
import atexit
import urllib.request
import urllib.parse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from threading import Semaphore

# =========================
# Global Constants
# =========================
VERSION = "v3.1.2-S"

CONFIG_FILE = "/etc/mmdvm_push.json"
LOG_DIR = "/var/log/pi-star/"
LOCAL_ID_FILE = "/usr/local/etc/nextionUsers.csv"

LOG_POLL_INTERVAL = 0.1
PUSH_MAX_WORKERS = 3
PUSH_RETRY = 2
CONFIG_RELOAD_INTERVAL = 5

# =========================
# Logging
# =========================
def log(level, msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{level}] {msg}", flush=True)

# =========================
# Config Manager
# =========================
class ConfigManager:
    _config = {}
    _last_mtime = 0
    _last_check = 0

    @classmethod
    def get_config(cls):
        now = time.time()
        if now - cls._last_check < CONFIG_RELOAD_INTERVAL:
            return cls._config
        cls._last_check = now

        if not os.path.exists(CONFIG_FILE):
            return cls._config

        try:
            mtime = os.path.getmtime(CONFIG_FILE)
            if mtime > cls._last_mtime:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cls._config = json.load(f)
                cls._last_mtime = mtime
                log("INFO", "Config reloaded")
        except json.JSONDecodeError as e:
            log("ERROR", f"Invalid config JSON, keep last config: {e}")
        except Exception as e:
            log("WARN", f"Config reload failed: {e}")

        return cls._config

# =========================
# Ham Info Manager
# =========================
class HamInfoManager:
    def __init__(self, id_file):
        self.id_file = id_file
        self._io_lock = Semaphore(2)
        self.geo_map = {
            "China": "🇨🇳 中国", "Hong Kong": "🇭🇰 中国香港", "Macao": "🇲🇴 中国澳门", "Taiwan": "🇹🇼 中国台湾",
            "Japan": "🇯🇵 日本", "Korea": "🇰🇷 韩国", "South Korea": "🇰🇷 韩国", "North Korea": "🇰🇵 朝鲜",
            "Thailand": "🇹🇭 泰国", "Singapore": "🇸🇬 新加坡", "Malaysia": "🇲🇾 马来西亚", "Indonesia": "🇮🇩 印度尼西亚",
            "Philippines": "🇵🇭 菲律宾", "Vietnam": "🇻🇳 越南", "India": "🇮🇳 印度", "Pakistan": "🇵🇰 巴基斯坦",
            "Sri Lanka": "🇱🇰 斯里兰卡", "Bangladesh": "🇧🇩 孟加拉国", "Nepal": "🇳🇵 尼泊尔", "Mongolia": "🇲🇳 蒙古",
            "United Arab Emirates": "🇦🇪 阿联酋", "UAE": "🇦🇪 阿联酋", "Saudi Arabia": "🇸🇦 沙特", "Israel": "🇮🇱 以色列",
            "Turkey": "🇹🇷 土耳其", "Iran": "🇮🇷 伊朗", "Iraq": "🇮🇶 伊拉克", "Kuwait": "🇰🇼 科威特",
            "Oman": "🇴🇲 阿曼", "Qatar": "🇶🇦 卡塔尔", "Jordan": "🇯🇴 约旦", "Lebanon": "🇱🇧 黎巴嫩",
            "Kazakhstan": "🇰🇿 哈萨克斯坦", "Uzbekistan": "🇺🇿 乌兹别克斯坦",
            "United Kingdom": "🇬🇧 英国", "UK": "🇬🇧 英国", "Germany": "🇩🇪 德国",
            "France": "🇫🇷 法国", "Italy": "🇮ᵗ 意大利", "Spain": "🇪🇸 西班牙", "Portugal": "🇵ᵗ 葡萄牙",
            "Russia": "🇷🇺 俄罗斯", "Russian Federation": "🇷🇺 俄罗斯", "Netherlands": "🇳🇱 荷兰",
            "Belgium": "🇧🇪 比利时", "Switzerland": "🇨🇭 瑞士", "Austria": "🇦ᵗ 奥地利", "Sweden": "🇸🇪 瑞典",
            "Norway": "🇳🇴 挪威", "Denmark": "🇩🇲 丹麦", "Finland": "🇫🇮 芬兰", "Poland": "🇵🇱 波兰",
            "Czech Republic": "🇨🇿 捷克", "Hungary": "🇭🇺 匈牙利", "Greece": "🇬🇷 希腊", "Ireland": "🇮🇪 爱尔兰",
            "Romania": "🇷🇴 罗马尼亚", "Bulgaria": "🇧🇬 保加利亚", "Ukraine": "🇺🇦 乌克兰", "Belarus": "🇧🇾 白俄罗斯",
            "Slovakia": "🇸🇰 斯洛伐克", "Croatia": "🇭🇷 克罗地亚", "Serbia": "🇷🇸 塞尔维亚", "Slovenia": "🇸🇮 斯洛文尼亚",
            "Estonia": "🇪🇪 爱沙尼亚", "Latvia": "🇱🇻 拉脱维亚", "Lithuania": "🇱🇹 立陶宛", "Iceland": "🇮🇸 冰岛",
            "Luxembourg": "🇱🇺 卢森堡", "Monaco": "🇲🇨 摩纳哥", "Cyprus": "🇨🇾 塞浦路斯", "Malta": "🇲🇹 马耳他",
            "United States": "🇺🇸 美国", "USA": "🇺🇸 美国", "Canada": "🇨🇦 加拿大", "Mexico": "🇲🇽 墨西哥",
            "Cuba": "🇨🇺 古巴", "Jamaica": "🇯🇲 牙买加", "Puerto Rico": "🇵🇷 波多黎各", "Dominican Republic": "🇩🇴 多米尼加",
            "Costa Rica": "🇨🇷 哥斯达黎加", "Panama": "🇵🇦 巴拿马", "Guatemala": "🇬🇹 危地马拉", "Honduras": "🇭🇳 洪都拉斯",
            "Brazil": "🇧🇷 巴西", "Argentina": "🇦🇷 阿根廷", "Chile": "🇨🇱 智利", "Colombia": "🇨🇴 哥伦比亚",
            "Peru": "🇵🇪 秘鲁", "Venezuela": "🇻🇪 委内瑞拉", "Uruguay": "🇺🇾 乌拉圭", "Paraguay": "🇵🇾 巴拉圭",
            "Ecuador": "🇪🇨 厄瓜多尔", "Bolivia": "🇧🇴 玻利维亚",
            "Australia": "🇦🇺 澳大利亚", "New Zealand": "🇳🇿 新西兰", "Fiji": "🇫🇯 斐济", "Papua New Guinea": "🇵🇬 巴布亚新几内亚",
            "South Africa": "🇿🇦 南非", "Egypt": "🇪🇬 埃及", "Nigeria": "🇳🇬 尼日利亚", "Kenya": "🇰🇪 肯尼亚",
            "Morocco": "🇲🇦 摩纳哥", "Algeria": "🇩🇿 阿尔及利亚", "Ethiopia": "🇪ᵗ 埃塞俄比亚", "Ghana": "🇬🇭 加纳",
            "Tanzania": "🇹🇿 坦桑尼亚", "Uganda": "🇺🇬 乌干达", "Mauritius": "🇲🇺 毛里求斯", "Seychelles": "🇸🇨 塞舌尔"
        }

    @lru_cache(maxsize=1)
    def _file_exists(self):
        return os.path.exists(self.id_file)

    @lru_cache(maxsize=4096)
    def get_info(self, callsign):
        if not self._file_exists():
            return {"name": "", "loc": "Unknown"}

        if not self._io_lock.acquire(timeout=2):
            return {"name": "", "loc": "Unknown"}

        try:
            with open(self.id_file, "rb") as f:
                with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                    key = f",{callsign},".encode()
                    idx = mm.find(key)
                    if idx == -1:
                        return {"name": "", "loc": "Unknown"}

                    start = mm.rfind(b"\n", 0, idx) + 1
                    end = mm.find(b"\n", idx)
                    line = mm[start:end].decode("utf-8", "ignore")
                    parts = line.split(",")

                    first = parts[2].strip() if len(parts) > 2 else ""
                    last = parts[3].strip() if len(parts) > 3 else ""
                    city = parts[4].strip().title() if len(parts) > 4 else ""
                    state = parts[5].strip().upper() if len(parts) > 5 else ""
                    country = parts[6].strip() if len(parts) > 6 else "Unknown"

                    if any('\u4e00' <= char <= '\u9fff' for char in country):
                        for k, v in self.geo_map.items():
                            if k in country or (len(v.split()) > 1 and v.split()[1] in country):
                                country = v
                                break
                    else:
                        country = self.geo_map.get(country, country)

                    name = f"{first} {last}".strip().upper()
                    loc = f"{city}, {state} ({country})" if city or state else country

                    return {
                        "name": f" ({name})" if name else "",
                        "loc": loc
                    }
        except Exception:
            return {"name": "", "loc": "Unknown"}
        finally:
            self._io_lock.release()

# =========================
# Push Service (S-level)
# =========================
class PushService:
    _executor = ThreadPoolExecutor(max_workers=PUSH_MAX_WORKERS)
    _semaphore = Semaphore(PUSH_MAX_WORKERS)

    @classmethod
    def send(cls, conf, title, body, async_mode=True):
        if async_mode:
            if not cls._semaphore.acquire(blocking=False):
                log("WARN", "Push queue full, dropping message")
                return
            cls._executor.submit(cls._wrapped_send, conf, title, body)
        else:
            cls._do_send(conf, title, body)

    @classmethod
    def _wrapped_send(cls, *args):
        try:
            cls._do_send(*args)
        finally:
            cls._semaphore.release()

    @classmethod
    def _do_send(cls, conf, title, body):
        if conf.get("push_tg_enabled") and conf.get("tg_token"):
            text = f"<b>{title}</b>\n\n{body}"
            url = f"https://api.telegram.org/bot{conf['tg_token']}/sendMessage"
            data = urllib.parse.urlencode({
                "chat_id": conf.get("tg_chat_id"),
                "text": text,
                "parse_mode": "HTML"
            }).encode()
            cls._post(url, data)

    @staticmethod
    def _post(url, data):
        for i in range(PUSH_RETRY + 1):
            try:
                req = urllib.request.Request(url, data=data)
                with urllib.request.urlopen(req, timeout=10):
                    return
            except Exception:
                if i == PUSH_RETRY:
                    log("WARN", "Push failed")
                time.sleep(1)

    @classmethod
    def shutdown(cls):
        cls._executor.shutdown(wait=True)

atexit.register(PushService.shutdown)

# =========================
# Monitor
# =========================
class MMDVMMonitor:
    def __init__(self):
        self.ham = HamInfoManager(LOCAL_ID_FILE)
        self.last_msg = {"call": "", "ts": 0}
        self.last_log_inode = None

        self.re_end = re.compile(
            r"end of (?P<v_type>(?:voice\s+|data\s+)?)transmission from "
            r"(?P<call>[A-Z0-9/\-]+) to (?P<target>[A-Z0-9/\-\s]+?), "
            r"(?P<dur>\d+\.?\d*) seconds"
            r"(?:, (?P<loss>\d+)% packet loss)?"
            r"(?:, BER: (?P<ber>\d+\.?\d*)%)?",
            re.IGNORECASE
        )

    # -------- 启动推送：网页端测试属于此范畴，改为实时同步推送 --------
    def push_boot_info(self):
        conf = ConfigManager.get_config()
        if not conf.get("boot_push_enabled", True):
            return

        try:
            ip = subprocess.getoutput("hostname -I").split()[0]
            cpu = subprocess.getoutput("top -bn1 | grep 'Cpu(s)' | awk '{print $2+$4}'")
            mem = subprocess.getoutput("free -m | awk 'NR==2{printf \"%.1f%%\", $3*100/$2 }'")
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                temp = f"{float(f.read())/1000:.1f}°C"
        except Exception:
            ip, cpu, mem, temp = "Unknown", "0", "0", "N/A"

        body = (
            f"🚀 **设备已上线** ({VERSION})\n"
            f"🌐 **内网IP**: {ip}\n"
            f"🌡️ **系统温度**: {temp}\n"
            f"📊 **CPU占用**: {cpu}%\n"
            f"💾 **内存占用**: {mem}\n"
            f"⏰ **时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        # ✅ 修改点1：网页端触发的测试推送改为同步执行 (async_mode=False)
        PushService.send(conf, "⚙️ 系统启动通知", body, async_mode=False)

    def run(self):
        self.push_boot_info()

        while True:
            try:
                self._run_inner()
            except Exception as e:
                log("ERROR", f"Fatal loop error, restarting in 5s: {e}")
                time.sleep(5)

    def _run_inner(self):
        log("INFO", f"MMDVM Push {VERSION} started")
        while True:
            log_file = self._latest_log()
            if not log_file:
                time.sleep(2)
                continue

            inode = os.stat(log_file).st_ino
            if inode != self.last_log_inode:
                self.last_log_inode = inode

            with open(log_file, "r", errors="ignore") as f:
                f.seek(0, 2)
                while True:
                    line = f.readline()
                    if not line:
                        time.sleep(LOG_POLL_INTERVAL)
                        break
                    self.process_line(line)

    def _latest_log(self):
        files = glob.glob(os.path.join(LOG_DIR, "MMDVM-*.log"))
        return max(files, key=os.path.getmtime) if files else None

    def process_line(self, line):
        if "end of" not in line.lower():
            return

        m = self.re_end.search(line)
        if not m:
            return

        conf = ConfigManager.get_config()
        call = m.group("call").upper()
        dur = float(m.group("dur"))

        if dur < conf.get("min_duration", 1):
            return

        now = time.time()
        if call == self.last_msg["call"] and now - self.last_msg["ts"] < 3:
            return
        self.last_msg = {"call": call, "ts": now}

        loss = m.group("loss") or "0"
        ber = m.group("ber") or "0.0"
        info = self.ham.get_info(call)

        try:
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                current_temp = f"{float(f.read())/1000:.1f}°C"
        except Exception:
            current_temp = "N/A"

        body = (
            f"👤 **呼号**: {call}{info['name']}\n"
            f"👥 **群组**: {m.group('target').strip()}\n"
            f"📍 **地区**: {info['loc']}\n"
            f"📅 **日期**: {datetime.now().strftime('%Y-%m-%d')}\n"
            f"⏰ **时间**: {datetime.now().strftime('%H:%M:%S')}\n"
            f"⏳ **时长**: {dur:.1f}秒\n"
            f"📦 **丢失**: {loss}%\n"
            f"📉 **误码**: {ber}%\n"
            f"🌡️ **温度**: {current_temp}"
        )

        # ✅ 修改点2：通联推送显式设定为异步推送 (async_mode=True)
        PushService.send(conf, "🎙️ 语音通联", body, async_mode=True)

# =========================
# Entry
# =========================
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--version":
        print(VERSION)
        sys.exit(0)

    MMDVMMonitor().run()
