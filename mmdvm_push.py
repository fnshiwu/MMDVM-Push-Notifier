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
import subprocess
import atexit
import logging
import tempfile
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from parser import parse_line
from filters import quiet_time, should_push
from notify_fmt import format_message, format_boot_notice, format_temp_alert, format_test_push
from identity import Identity
from hardware import Hardware
from notifier import PushService
from config import ConfigManager

# =========================
# Global Constants
# =========================
VERSION = "v3.2.8"
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
            (logger or logging.getLogger(__name__)).warning(f"Config sanitize error: {e}")
        return conf


# =========================
# Ham Info Manager (修复后的映射表)
# =========================
class HamInfoManager:
    def __init__(self, id_file: str):
        self.identity = Identity(id_file)
    def get_info(self, callsign: str) -> Dict[str, str]:
        return self.identity.get_info(callsign)

atexit.register(PushService.shutdown)

# =========================
# Monitor Logic
# =========================
class MMDVMMonitor:
    def __init__(self):
        self.last_msg: Dict[str, Any] = {"call": "", "ts": 0}
        self.hw = Hardware()
        self.ham_manager = HamInfoManager(LOCAL_ID_FILE)
        self.last_activity_ts: float = 0.0
        
    def _send_boot_notice(self, conf: Dict, network_ok: bool):
        ip, cpu, mem = self.get_sys_info()
        temp_str, _ = self.get_current_temp(conf)
        title, body = format_boot_notice(conf, VERSION, ip, temp_str, cpu, mem, network_ok)
        PushService.send(conf, title, body, is_voice=False, async_mode=False)        

    def _cpu_percent_proc(self) -> str:
        return self.hw._cpu_percent_top()

    def _cpu_percent_top(self) -> str:
        return self.hw._cpu_percent_top()

    def _cpu_percent_process(self, interval: float = 1.0) -> str:
        return self.hw._cpu_percent_process(interval=interval)

    def _cpu_percent_process_top(self) -> str:
        return self.hw._cpu_percent_process_top()

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
        return self.hw._mem_percent_proc()

    def get_sys_info(self) -> Tuple[str, str, str]:
        return self.hw.get_sys_info()

    def get_current_temp(self, conf: Dict) -> Tuple[str, float]:
        return self.hw.get_current_temp(conf)

    def check_temp_alert(self, conf: Dict):
        res = self.hw.check_temp_alert(conf)
        if res:
            title, body = res
            PushService.send(conf, title, body, is_voice=False)

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
            self._send_boot_notice(conf, network_ok)
            if not network_ok:
                if self.check_network(max_attempts=30, interval=2):
                    self._send_boot_notice(conf, True)

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
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        setup_logging()
        monitor = MMDVMMonitor()
        conf = ConfigManager.get_config()
        ip, cpu, mem = monitor.get_sys_info()
        temp_str, _ = monitor.get_current_temp(conf)
        title, test_body = format_test_push(conf, VERSION, ip, temp_str, cpu, mem)
        PushService.send(conf, title, test_body, is_voice=False, async_mode=False)
        print("Success")
    elif len(sys.argv) > 1 and sys.argv[1] == "--health":
        conf = ConfigManager.get_config()
        mon = MMDVMMonitor()
        ip, cpu_sys, mem_sys = mon.get_sys_info()
        cpu_proc = mon._cpu_percent_process_top()
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
