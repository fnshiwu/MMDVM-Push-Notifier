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
TEMP_CHECK_INTERVAL = 30  # 温度检查间隔（秒）
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
        try:
            # 优先尝试 UTC 时间（Pi-Star 默认使用 UTC 创建日志文件）
            utc_date = datetime.utcnow().date()
            utc_log = os.path.join(MMDVM_LOG_DIR, f"MMDVM-{utc_date}.log")
            if os.path.exists(utc_log) and os.path.getsize(utc_log) > 0:
                return utc_log

            # Fallback 1: 尝试本地时间（兼容非标准配置）
            local_date = datetime.now().date()
            if local_date != utc_date:  # 避免重复检查
                local_log = os.path.join(MMDVM_LOG_DIR, f"MMDVM-{local_date}.log")
                if os.path.exists(local_log) and os.path.getsize(local_log) > 0:
                    return local_log

            # Fallback 2: glob 查找最新文件（最后的保险）
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
                # 先快速检查 IP，避免不必要的网络请求
                ip_check = subprocess.getoutput("hostname -I").strip()
                if not ip_check or ip_check.startswith("127."):
                    time.sleep(interval)
                    continue

                # 只有 IP 正常才进行网络连通性测试
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
        """持续读取日志文件"""
        max_iterations = MAX_LOG_ITERATIONS
        iteration_count = 0

        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(0, 2)  # 移到文件末尾
                last_check = time.time()

                while True:
                    iteration_count += 1
                    if iteration_count > max_iterations:
                        logger.warning(f"达到最大迭代次数 {max_iterations}，重启日志监控")
                        return

                    # 定期检查是否有新日志文件
                    if time.time() - last_check > 5:
                        new_log = self.get_latest_log()
                        if new_log and new_log != log_file:
                            rest = f.read()
                            if rest:
                                for line in rest.splitlines():
                                    self.process_line(line)
                            logger.info(f"切换到新日志: {new_log}")
                            return  # 退出当前循环，让外层重新打开新文件
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

        # 只在有活动时每30秒检查一次温度，而不是每行都检查
        now = time.time()
        if now - self._last_temp_check > TEMP_CHECK_INTERVAL:
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
