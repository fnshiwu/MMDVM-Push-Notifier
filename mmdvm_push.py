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
import socket
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from parser import parse_line
from filters import quiet_time, should_push
from notify_fmt import format_message, format_boot_notice, format_test_push
from identity import Identity
from hardware import Hardware
from alerts import AlertManager
from notifier import PushService
from config import ConfigManager

# =========================
# Global Constants
# =========================
VERSION = "v3.3.0"
CONFIG_FILE = "/etc/mmdvm_push.json"
MMDVM_LOG_DIR = "/var/log/pi-star/"
LOCAL_ID_FILE = "/usr/local/etc/nextionUsers.csv"
LOG_POLL_INTERVAL = 0.2
PUSH_MAX_WORKERS = 3
PUSH_RETRY = 2
MEMORY_CHECK_INTERVAL = 3600  # 内存检查间隔（秒）
MEMORY_THRESHOLD_KB = 100000  # 内存阈值（KB）
MAX_LOG_ITERATIONS = 100000  # 日志循环最大迭代次数

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

atexit.register(PushService.shutdown)

# =========================
# Monitor Logic
# =========================
class MMDVMMonitor:
    def __init__(self):
        self.last_msg: Dict[str, Any] = {"call": "", "ts": 0}
        self.hw = Hardware()
        self.alerts = AlertManager(self.hw)
        self.identity = Identity(LOCAL_ID_FILE)
        self.last_activity_ts: float = 0.0
        self._last_temp_check: float = 0.0  # 温度检查时间戳

    def _send_boot_notice(self, conf: Dict, network_ok: bool):
        ip, cpu, mem = self.hw.get_sys_info()
        temp_str, _ = self.hw.get_current_temp(conf)
        title, body = format_boot_notice(conf, VERSION, ip, temp_str, cpu, mem, network_ok)
        PushService.send(conf, title, body, is_voice=False, async_mode=False)

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

    def check_temp_alert(self, conf: Dict):
        """Check and send temperature alert if needed | 检查并在需要时发送温度告警"""
        res = self.alerts.check_temp_alert(conf)
        if res:
            title, body = res
            PushService.send(conf, title, body, is_voice=False)

    def get_latest_log(self) -> Optional[str]:
        """Get latest log file (MEDIUM #8 fix: consistent UTC timezone)"""
        try:
            # Pi-Star uses UTC for log files, so always use UTC
            current_date = datetime.utcnow().date()
            utc_log = os.path.join(MMDVM_LOG_DIR, f"MMDVM-{current_date}.log")
            if os.path.exists(utc_log) and os.path.getsize(utc_log) > 0:
                return utc_log

            # Fallback: Check yesterday's log (for timezone edge cases)
            yesterday = current_date - timedelta(days=1)
            yesterday_log = os.path.join(MMDVM_LOG_DIR, f"MMDVM-{yesterday}.log")
            if os.path.exists(yesterday_log) and os.path.getsize(yesterday_log) > 0:
                return yesterday_log

            # Final fallback: glob for most recent
            log_files = [
                f for f in glob.glob(os.path.join(MMDVM_LOG_DIR, "MMDVM-*.log"))
                if os.path.isfile(f) and os.path.getsize(f) > 0
            ]
            return max(log_files, key=os.path.getmtime) if log_files else None
        except (OSError, ValueError) as e:
            logger.error(f"Error finding log file: {e}")
            return None

    def check_network(self, max_attempts: int = 30, interval: float = 2) -> bool:
        """检查网络连通性 (HIGH #4 & MEDIUM #11 fix)"""
        logger.info("正在进入冷启动网络探测循环...")

        for i in range(max_attempts):
            try:
                # MEDIUM #11 fix: Validate subprocess output before using
                result = subprocess.run(
                    ["hostname", "-I"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False
                )
                ip_check = result.stdout.strip() if result.returncode == 0 else ""
                if not ip_check or ip_check.startswith("127."):
                    time.sleep(interval)
                    continue

                # 网络连通性测试
                urllib.request.urlopen(
                    "http://www.apple.com/library/test/success.html",
                    timeout=3
                )
                logger.info(f"网络就绪 (尝试 {i+1})")
                return True
            except (urllib.error.URLError, urllib.error.HTTPError, socket.timeout) as e:
                # Expected network errors
                logger.debug(f"Network check attempt {i+1} failed: {e}")
            except subprocess.SubprocessError as e:
                # hostname command failed
                logger.warning(f"Failed to get IP address: {e}")
            except Exception as e:
                # Unexpected errors - log with full traceback
                logger.error(f"Unexpected error in network check: {e}", exc_info=True)

            time.sleep(interval)

        logger.warning("网络探测超时")
        return False

    def run(self):
        conf = ConfigManager.get_config()
        network_ok = self.check_network()

        if conf.get('boot_push_enabled', True):
            if network_ok:
                self._send_boot_notice(conf, True)
            else:
                # 网络不可用，重试一次
                network_ok_retry = self.check_network(max_attempts=30, interval=2)
                self._send_boot_notice(conf, network_ok_retry)

        logger.info(f"{VERSION} 监控就绪，正在监听日志行...")

        # 内存监控
        last_mem_check = time.time()

        while True:
            try:
                # 每小时检查一次内存
                if time.time() - last_mem_check > MEMORY_CHECK_INTERVAL:
                    rss_kb = int(self._proc_mem_rss_kb())
                    if rss_kb > MEMORY_THRESHOLD_KB:
                        logger.warning(f"内存占用过高: {rss_kb}KB，建议重启服务")
                    else:
                        logger.info(f"内存占用正常: {rss_kb}KB")
                    last_mem_check = time.time()

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
        """持续读取日志文件 (CRITICAL #3 & MEDIUM #8 & #9 fix)"""
        max_iterations = MAX_LOG_ITERATIONS
        iteration_count = 0
        start_time = time.time()

        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(0, 2)  # 移到文件末尾
                last_check = time.time()

                while True:
                    # MEDIUM #8 fix: Reset counter every hour BEFORE incrementing
                    if time.time() - start_time >= 3600:
                        iteration_count = 0
                        start_time = time.time()
                        logger.info(f"Iteration counter reset for active log: {log_file}")

                    iteration_count += 1

                    if iteration_count > max_iterations:
                        logger.warning(f"达到最大迭代次数 {max_iterations}，重启日志监控")
                        return

                    # Check if file still exists and is readable
                    if not os.path.exists(log_file):
                        logger.warning(f"Log file deleted: {log_file}")
                        return

                    # 定期检查是否有新日志文件
                    if time.time() - last_check > 5:
                        new_log = self.get_latest_log()
                        # MEDIUM #20 fix: Only switch if new log is different AND newer
                        if new_log and new_log != log_file:
                            try:
                                # Verify new log is actually newer before switching
                                if os.path.getmtime(new_log) > os.path.getmtime(log_file):
                                    rest = f.read()
                                    if rest:
                                        for line in rest.splitlines():
                                            self.process_line(line)
                                    logger.info(f"切换到新日志: {new_log}")
                                    return  # 退出当前循环，让外层重新打开新文件
                            except OSError as e:
                                logger.warning(f"Failed to compare log file times: {e}")
                        last_check = time.time()

                    line = f.readline()
                    if not line:
                        # 根据活跃度动态调整轮询间隔
                        idle_time = time.time() - self.last_activity_ts
                        if idle_time < 60:
                            interval = 0.3  # 1分钟内活跃
                        elif idle_time < 300:
                            interval = 0.5  # 5分钟内
                        else:
                            interval = 1.0  # 长时间无活动
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

        # MEDIUM #19 fix: Use configurable temp_interval instead of hardcoded constant
        now = time.time()
        temp_interval = conf.get('temp_interval', 30)
        if now - self._last_temp_check > temp_interval:
            self.check_temp_alert(conf)
            self._last_temp_check = now

        if quiet_time(conf):
            return
        if not should_push(conf, event, self.last_msg):
            return
        curr_ts = time.time()
        self.last_msg.update({"call": event['call'], "ts": curr_ts})
        info = self.identity.get_info(event['call'])
        temp_str, _ = self.hw.get_current_temp(conf)
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
        ip, cpu, mem = monitor.hw.get_sys_info()
        temp_str, _ = monitor.hw.get_current_temp(conf)
        title, test_body = format_test_push(conf, VERSION, ip, temp_str, cpu, mem)
        PushService.send(conf, title, test_body, is_voice=False, async_mode=False)
        print("Success")
    elif len(sys.argv) > 1 and sys.argv[1] == "--health":
        conf = ConfigManager.get_config()
        mon = MMDVMMonitor()
        ip, cpu_sys, mem_sys = mon.hw.get_sys_info()
        cpu_proc = mon.hw._cpu_percent_process_top()
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
                ip_output = subprocess.getoutput("hostname -I").strip()
                _ip = ip_output.split()[0] if ip_output else ""
            except Exception:
                _ip = ""
            if os.path.exists(MMDVM_LOG_DIR) and _ip:
                break
            time.sleep(2)
        monitor.run()
