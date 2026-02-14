#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import time
import json
import glob
import sys
import subprocess
import atexit
import logging
import tempfile
import urllib.request
import socket
from datetime import datetime, timedelta
from typing import Dict, Optional, Any

from parser import parse_line
from filters import quiet_time, should_push
from notify_fmt import format_message, format_boot_notice, format_test_push
from identity import Identity
from hardware import Hardware
from alerts import AlertManager
from notifier import PushService
from config import ConfigManager

# =========================
# Global Constants | 全局常量
# =========================
VERSION = "v3.4.1"
CONFIG_FILE = "/etc/mmdvm_push.json"
MMDVM_LOG_DIR = "/var/log/pi-star/"
LOCAL_ID_FILE = "/usr/local/etc/nextionUsers.csv"
MEMORY_CHECK_INTERVAL = 3600  # Memory check interval in seconds
MEMORY_THRESHOLD_KB = 100000  # Memory threshold in KB (100MB)
MAX_LOG_ITERATIONS = 100000  # Max log loop iterations to prevent stale handles

# Version check for web interface
if len(sys.argv) > 1 and sys.argv[1] == "--version":
    print(VERSION)
    sys.exit(0)

# Logging Setup
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
        logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s')
    console.setFormatter(formatter)
    logging.getLogger('').addHandler(console)
    logger = logging.getLogger(__name__)

atexit.register(PushService.shutdown)

# =========================
# Monitor Logic | 监控逻辑
# =========================
class MMDVMMonitor:
    def __init__(self):
        self.last_msg: Dict[str, Any] = {"call": "", "target": "", "ts": 0}
        self.hw = Hardware()
        self.alerts = AlertManager(self.hw)
        self.identity = Identity(LOCAL_ID_FILE)
        self.last_activity_ts: float = 0.0
        self._last_temp_check: float = 0.0 

    def _send_boot_notice(self, conf: Dict, network_ok: bool):
        ip, cpu, mem = self.hw.get_sys_info()
        temp_str, _ = self.hw.get_current_temp(conf)
        title, body = format_boot_notice(conf, VERSION, ip, temp_str, cpu, mem, network_ok)
        PushService.send(conf, title, body, is_voice=False, async_mode=False)

    def _proc_mem_rss_kb(self) -> str:
        try:
            with open(f"/proc/{os.getpid()}/status", "r") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        parts = line.split()
                        return parts[1] if len(parts) >= 2 else "0"
            return "0"
        except Exception:
            return "0"

    def get_latest_log(self) -> Optional[str]:
        """Get latest log file with UTC support for Pi-Star"""
        try:
            current_date = datetime.utcnow().date()
            utc_log = os.path.join(MMDVM_LOG_DIR, f"MMDVM-{current_date}.log")
            if os.path.exists(utc_log) and os.path.getsize(utc_log) > 0:
                return utc_log

            # Fallback to yesterday
            yesterday = current_date - timedelta(days=1)
            yesterday_log = os.path.join(MMDVM_LOG_DIR, f"MMDVM-{yesterday}.log")
            if os.path.exists(yesterday_log) and os.path.getsize(yesterday_log) > 0:
                return yesterday_log
                
            # Fallback to glob
            log_files = glob.glob(os.path.join(MMDVM_LOG_DIR, "MMDVM-*.log"))
            valid_files = [f for f in log_files if os.path.isfile(f) and os.path.getsize(f) > 0]
            return max(valid_files, key=os.path.getmtime) if valid_files else None
        except Exception as e:
            logger.error(f"Error finding log file: {e}")
            return None

    def check_network(self, max_attempts: int = 30, interval: float = 2) -> bool:
        logger.info("Starting network check...")
        for i in range(max_attempts):
            try:
                # Optimized check using socket first (lighter than subprocess)
                urllib.request.urlopen("http://www.apple.com/library/test/success.html", timeout=3)
                logger.info(f"Network ready (attempt {i+1})")
                return True
            except Exception:
                time.sleep(interval)
        
        logger.warning("Network check timed out")
        return False

    def run(self):
        conf = ConfigManager.get_config()
        network_ok = self.check_network()

        if conf.get('boot_push_enabled', True):
            self._send_boot_notice(conf, network_ok)

        logger.info(f"{VERSION} Monitor ready, tailing logs...")
        
        last_mem_check = time.time()
        
        # Initialize temp check timer
        self._last_temp_check = time.time()

        while True:
            try:
                # 1. Resource Self-Audit (Hourly)
                if time.time() - last_mem_check > MEMORY_CHECK_INTERVAL:
                    rss_kb = int(self._proc_mem_rss_kb())
                    if rss_kb > MEMORY_THRESHOLD_KB:
                        logger.warning(f"High memory usage: {rss_kb}KB")
                    last_mem_check = time.time()

                # 2. Log Tailing Loop
                current_log = self.get_latest_log()
                if not current_log:
                    time.sleep(5)
                    continue

                self._tail_log(current_log)

            except KeyboardInterrupt:
                logger.info("Shutdown signal received.")
                break
            except Exception as e:
                logger.error(f"Main loop error: {e}")
                time.sleep(5)

    def _tail_log(self, log_file: str):
        max_iterations = MAX_LOG_ITERATIONS
        iteration_count = 0
        start_time = time.time()

        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(0, 2)
                last_check_file = time.time()

                while True:
                    iteration_count += 1
                    
                    # Periodic Reset
                    if time.time() - start_time > 3600:
                        iteration_count = 0
                        start_time = time.time()

                    if iteration_count > max_iterations:
                        logger.info("Max iterations reached, reloading log file...")
                        return

                    # 3. Temperature Alert Check (The "Three-Body Problem" Fix)
                    # Logic centralized here. Config provides 'temp_interval' in seconds.
                    # 逻辑集中于此。配置中的 temp_interval 已转换为秒。
                    conf = ConfigManager.get_config()
                    temp_interval = conf.get('temp_interval', 1800) # Default 30 mins
                    
                    now_ts = time.time()
                    if now_ts - self._last_temp_check > temp_interval:
                        # Call AlertManager to check threshold and format message
                        alert_res = self.alerts.check_temp_alert(conf)
                        if alert_res:
                            title, body = alert_res
                            PushService.send(conf, title, body, is_voice=False)
                        self._last_temp_check = now_ts

                    # 4. Check for log rotation
                    if time.time() - last_check_file > 5:
                        if not os.path.exists(log_file):
                            return
                        new_log = self.get_latest_log()
                        if new_log and new_log != log_file:
                            # Read remaining lines efficiently
                            remaining = f.readlines()
                            for line in remaining:
                                self.process_line(line)
                            return
                        last_check_file = time.time()

                    # 5. Read line
                    line = f.readline()
                    if not line:
                        # Dynamic polling interval
                        idle_time = time.time() - self.last_activity_ts
                        sleep_time = 0.3 if idle_time < 60 else (0.5 if idle_time < 300 else 1.0)
                        time.sleep(sleep_time)
                        continue

                    self.process_line(line)

        except Exception as e:
            logger.error(f"Tail log error: {e}")

    def process_line(self, line: str):
        event = parse_line(line)
        if not event:
            return
            
        conf = ConfigManager.get_config()
        
        if quiet_time(conf):
            return
            
        if not should_push(conf, event, self.last_msg):
            return
            
        # Update last message state for deduplication
        curr_ts = time.time()
        self.last_msg.update({
            "call": event['call'], 
            "target": event['target'],
            "ts": curr_ts
        })
        self.last_activity_ts = curr_ts
        
        # Identity lookup and formatting
        info = self.identity.get_info(event['call'])
        temp_str, _ = self.hw.get_current_temp(conf)
        type_label, body = format_message(conf, event, temp_str, info)
        
        PushService.send(conf, type_label, body, is_voice=event['is_voice'])
        logger.info(f"Push sent: {event['call']} -> {event['target']}")

# =========================
# Entry
# =========================
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        setup_logging()
        monitor = MMDVMMonitor()
        conf = ConfigManager.get_config()
        ip, cpu, mem = monitor.hw.get_sys_info()
        temp_str, _ = monitor.hw.get_current_temp(conf)
        title, test_body = format_test_push(conf, VERSION, ip, temp_str, cpu, mem)
        PushService.send(conf, title, test_body, is_voice=False, async_mode=False)
        print("Success")
    elif len(sys.argv) > 1 and sys.argv[1] == "--health":
        # Health check JSON output
        try:
            conf = ConfigManager.get_config()
            mon = MMDVMMonitor()
            ip, cpu_sys, mem_sys = mon.hw.get_sys_info()
            cpu_proc = mon.hw._cpu_percent_process(interval=0.1) # Non-blocking approx
            rss_kb = mon._proc_mem_rss_kb()
            status = {
                "version": VERSION,
                "app_log_dir": APP_LOG_DIR,
                "app_log_writable": os.access(APP_LOG_DIR, os.W_OK),
                "mmdvm_log_dir": MMDVM_LOG_DIR,
                "mmdvm_log_exists": os.path.exists(MMDVM_LOG_DIR),
                "config_valid": True,
                "ip": ip,
                "cpu_system": f"{cpu_sys}%",
                "cpu_process": f"{cpu_proc}%",
                "mem_rss_kb": rss_kb,
                "time": datetime.now().isoformat(timespec="seconds")
            }
            print(json.dumps(status, ensure_ascii=False))
        except Exception as e:
            print(json.dumps({"error": str(e), "config_valid": False}, ensure_ascii=False))
    else:
        setup_logging()
        monitor = MMDVMMonitor()
        monitor.run()
