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
from config import ConfigManager, PUSH_MAX_WORKERS, PUSH_RETRY

# =========================
# Global Constants | 全局常量
# =========================
VERSION = "v3.4.0"
CONFIG_FILE = "/etc/mmdvm_push.json"
MMDVM_LOG_DIR = "/var/log/pi-star/"
LOCAL_ID_FILE = "/usr/local/etc/nextionUsers.csv"
MEMORY_CHECK_INTERVAL = 3600  # Memory check interval in seconds | 内存检查间隔（秒）
MEMORY_THRESHOLD_KB = 100000  # Memory threshold in KB | 内存阈值（KB）
MAX_LOG_ITERATIONS = 100000  # Max log loop iterations | 日志循环最大迭代次数
SECONDS_PER_HOUR = 3600  # Seconds per hour | 一小时的秒数
# Polling interval thresholds | 轮询间隔阈值
ACTIVE_IDLE_THRESHOLD = 60  # Seconds to consider as active | 视为活跃的秒数
MODERATE_IDLE_THRESHOLD = 300  # Seconds to consider as moderate activity | 视为中等活跃的秒数
ACTIVE_POLL_INTERVAL = 0.3  # Poll interval when active | 活跃时的轮询间隔
MODERATE_POLL_INTERVAL = 0.5  # Poll interval when moderately active | 中等活跃时的轮询间隔
IDLE_POLL_INTERVAL = 1.0  # Poll interval when idle | 空闲时的轮询间隔

# Quick version query without logging initialization | 版本查询快速返回，避免初始化日志
if len(sys.argv) > 1 and sys.argv[1] == "--version":
    print(VERSION)
    sys.exit(0)

# Dynamically adjust log directory permissions | 动态调整日志目录权限
APP_LOG_DIR = "/var/log/pi-star/"
if not os.path.exists(APP_LOG_DIR) or not os.access(APP_LOG_DIR, os.W_OK):
    APP_LOG_DIR = tempfile.gettempdir()

def setup_logging():
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
    if APP_LOG_DIR != "/var/log/pi-star/":
        logging.getLogger(__name__).warning(f"No write permission for /var/log/pi-star/. Falling back to {APP_LOG_DIR}")

atexit.register(PushService.shutdown)

# =========================
# Monitor Logic | 监控逻辑
# =========================
class MMDVMMonitor:
    """MMDVM log monitor and push notification manager | MMDVM 日志监控与推送管理器"""
    def __init__(self):
        self.last_msg: Dict[str, Any] = {"call": "", "target": "", "ts": 0}
        self.hw = Hardware()
        self.alerts = AlertManager(self.hw)
        self.identity = Identity(LOCAL_ID_FILE)
        self.last_activity_ts: float = time.time()  # Initialize to current time to avoid huge idle_time on startup | 初始化为当前时间避免启动时巨大的空闲时间

    def _send_boot_notice(self, conf: Dict, network_ok: bool):
        """Send boot notification | 发送启动通知"""
        ip, cpu, mem = self.hw.get_sys_info()
        temp_str, _ = self.hw.get_current_temp(conf)
        title, body = format_boot_notice(conf, VERSION, ip, temp_str, cpu, mem, network_ok)
        PushService.send(conf, title, body, is_voice=False, async_mode=False)

    def _proc_mem_rss_kb(self) -> str:
        """Get process memory RSS in KB | 获取进程内存 RSS（KB）"""
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
        """Get latest log file using UTC timezone | 获取最新日志文件（使用 UTC 时区）"""
        try:
            # Pi-Star uses UTC for log files | Pi-Star 日志文件使用 UTC 时区
            current_date = datetime.utcnow().date()
            utc_log = os.path.join(MMDVM_LOG_DIR, f"MMDVM-{current_date}.log")
            if os.path.exists(utc_log) and os.path.getsize(utc_log) > 0:
                return utc_log

            # Fallback: Check yesterday's log | 回退：检查昨天的日志
            yesterday = current_date - timedelta(days=1)
            yesterday_log = os.path.join(MMDVM_LOG_DIR, f"MMDVM-{yesterday}.log")
            if os.path.exists(yesterday_log) and os.path.getsize(yesterday_log) > 0:
                return yesterday_log

            # Final fallback: glob for most recent | 最终回退：查找最新文件
            log_files = [
                f for f in glob.glob(os.path.join(MMDVM_LOG_DIR, "MMDVM-*.log"))
                if os.path.isfile(f) and os.path.getsize(f) > 0
            ]
            return max(log_files, key=os.path.getmtime) if log_files else None
        except (OSError, ValueError) as e:
            logging.getLogger(__name__).error(f"Error finding log file: {e}")
            return None

    def check_network(self, max_attempts: int = 30, interval: float = 2) -> bool:
        """Check network connectivity | 检查网络连通性"""
        logger = logging.getLogger(__name__)
        logger.info("正在进入冷启动网络探测循环...")

        for i in range(max_attempts):
            try:
                # Validate subprocess output before using | 使用前验证子进程输出
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

                # Network connectivity test | 网络连通性测试
                urllib.request.urlopen(
                    "http://www.apple.com/library/test/success.html",
                    timeout=3
                )
                logger.info(f"网络就绪 (尝试 {i+1}/{max_attempts})")
                return True
            except subprocess.TimeoutExpired:
                # Subprocess timeout | 子进程超时
                logger.debug(f"hostname command timeout on attempt {i+1}")
            except (urllib.error.URLError, urllib.error.HTTPError, socket.timeout) as e:
                # Expected network errors | 预期的网络错误
                logger.debug(f"Network check attempt {i+1}/{max_attempts} failed: {e}")
            except subprocess.SubprocessError as e:
                # hostname command failed | hostname 命令失败
                logger.warning(f"Failed to get IP address: {e}")
            except Exception as e:
                # Unexpected errors - log with full traceback | 意外错误 - 记录完整堆栈
                logger.error(f"Unexpected error in network check: {e}", exc_info=True)

            time.sleep(interval)

        logger.warning(f"网络探测超时 (已尝试 {max_attempts} 次)")
        return False

    def run(self):
        """Main monitoring loop | 主监控循环"""
        logger = logging.getLogger(__name__)
        conf = ConfigManager.get_config()
        network_ok = self.check_network()

        if conf.get('boot_push_enabled', True):
            if network_ok:
                self._send_boot_notice(conf, True)
            else:
                # Network unavailable, retry with shorter parameters for faster startup | 网络不可用，使用更短参数快速重试
                logger.info("首次网络检查失败，进行快速重试（冷启动场景）...")
                network_ok_retry = self.check_network(max_attempts=10, interval=1)
                self._send_boot_notice(conf, network_ok_retry)

        logger.info(f"{VERSION} 监控就绪，正在监听日志行...")

        # Memory monitoring | 内存监控
        last_mem_check = time.time()
        # Temperature monitoring | 温度监控
        last_temp_check = time.time()

        while True:
            try:
                # Check memory every hour | 每小时检查一次内存
                if time.time() - last_mem_check > MEMORY_CHECK_INTERVAL:
                    rss_kb = int(self._proc_mem_rss_kb())
                    if rss_kb > MEMORY_THRESHOLD_KB:
                        logger.warning(f"内存占用过高: {rss_kb}KB，建议重启服务")
                    else:
                        logger.info(f"内存占用正常: {rss_kb}KB")
                    last_mem_check = time.time()

                # Check temperature periodically | 定期检查温度
                temp_interval = conf.get('temp_interval', 30)
                if time.time() - last_temp_check > temp_interval:
                    self.check_temp_alert(conf)
                    last_temp_check = time.time()

                current_log = self.get_latest_log()
                if not current_log:
                    if not hasattr(self, '_log_warning_shown'):
                        logger.warning(
                            f"No MMDVM log files found in {MMDVM_LOG_DIR}. "
                            f"Waiting for log file to appear..."
                        )
                        self._log_warning_shown = True
                    time.sleep(5)
                    continue

                self._tail_log(current_log)

            except KeyboardInterrupt:
                logging.getLogger(__name__).info("收到中断信号，正在退出...")
                break
            except Exception as e:
                logging.getLogger(__name__).error(f"循环异常: {e}")
                time.sleep(5)

    def _tail_log(self, log_file: str):
        """Continuously read log file with rotation support | 持续读取日志文件（支持轮转）"""
        logger = logging.getLogger(__name__)
        max_iterations = MAX_LOG_ITERATIONS
        iteration_count = 0
        start_time = time.time()

        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(0, 2)  # Seek to end of file | 移到文件末尾
                last_check = time.time()

                while True:
                    # Reset counter every hour to prevent overflow | 每小时重置计数器防止溢出
                    if time.time() - start_time >= SECONDS_PER_HOUR:
                        iteration_count = 0
                        start_time = time.time()
                        logger.info(f"Iteration counter reset for active log: {log_file}")

                    iteration_count += 1

                    if iteration_count > max_iterations:
                        logger.warning(f"达到最大迭代次数 {max_iterations}，重启日志监控")
                        return

                    # Check if file still exists and is readable | 检查文件是否仍存在且可读
                    if not os.path.exists(log_file):
                        logger.warning(f"Log file deleted: {log_file}")
                        return

                    # Periodically check for new log file (increased interval for performance) | 定期检查是否有新日志文件（增加间隔以提升性能）
                    if time.time() - last_check > 10:
                        new_log = self.get_latest_log()
                        # Only switch if new log is different AND newer | 仅在新日志不同且更新时切换
                        if new_log and new_log != log_file:
                            try:
                                # Verify new log is actually newer before switching | 切换前验证新日志确实更新
                                if os.path.getmtime(new_log) > os.path.getmtime(log_file):
                                    # Read all remaining content from current file before switching | 切换前读取当前文件所有剩余内容
                                    remaining_content = []
                                    while True:
                                        line = f.readline()
                                        if not line:
                                            break
                                        remaining_content.append(line)

                                    # Process all remaining lines | 处理所有剩余行
                                    for line in remaining_content:
                                        self.process_line(line)

                                    logger.info(f"切换到新日志: {new_log}")
                                    return  # Exit loop to reopen new file | 退出循环重新打开新文件
                            except OSError as e:
                                logger.warning(f"Failed to compare log file times: {e}")
                        last_check = time.time()

                    line = f.readline()
                    if not line:
                        # Dynamically adjust polling interval based on activity | 根据活跃度动态调整轮询间隔
                        idle_time = time.time() - self.last_activity_ts
                        if idle_time < ACTIVE_IDLE_THRESHOLD:
                            interval = ACTIVE_POLL_INTERVAL  # Active within 1 minute | 1分钟内活跃
                        elif idle_time < MODERATE_IDLE_THRESHOLD:
                            interval = MODERATE_POLL_INTERVAL  # Within 5 minutes | 5分钟内
                        else:
                            interval = IDLE_POLL_INTERVAL  # Long idle | 长时间无活动
                        time.sleep(interval)
                        continue

                    self.process_line(line)

        except FileNotFoundError:
            logging.getLogger(__name__).warning(f"日志文件不存在: {log_file}")
        except PermissionError:
            logging.getLogger(__name__).error(f"无权限读取日志: {log_file}")

    def process_line(self, line: str):
        """Process a single log line | 处理单行日志"""
        event = parse_line(line)
        if not event:
            return
        conf = ConfigManager.get_config()

        if quiet_time(conf):
            return
        if not should_push(conf, event, self.last_msg):
            return
        curr_ts = time.time()
        self.last_msg.update({"call": event['call'], "target": event['target'], "ts": curr_ts})
        info = self.identity.get_info(event['call'])
        temp_str, _ = self.hw.get_current_temp(conf)
        type_label, body = format_message(conf, event, temp_str, info)
        self.last_activity_ts = time.time()
        PushService.send(conf, type_label, body, is_voice=event['is_voice'])
        logging.getLogger(__name__).info(f"推送完成: {event['call']} -> {event['target']}")

# =========================
# Entry Point | 入口点
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
        # Health check mode - gracefully handle permission errors | 健康检查模式 - 优雅处理权限错误
        try:
            conf = ConfigManager.get_config()
            config_valid = isinstance(conf, dict) and len(conf) > 0
        except Exception:
            conf = {}
            config_valid = False

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
            "config_valid": config_valid,
            "config_readable": os.access(CONFIG_FILE, os.R_OK) if os.path.exists(CONFIG_FILE) else False,
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
        # Simple readiness wait: log dir exists + IP obtained | 简单就绪等待：日志目录存在 + 获取 IP 成功
        start_t = time.time()
        for i in range(10):
            try:
                # Use subprocess.run() instead of getoutput() | 使用 subprocess.run() 替代 getoutput()
                result = subprocess.run(
                    ["hostname", "-I"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False
                )
                ip_parts = result.stdout.strip().split() if result.returncode == 0 else []
                _ip = ip_parts[0] if ip_parts else ""
            except Exception:
                _ip = ""
            if os.path.exists(MMDVM_LOG_DIR) and _ip:
                break
            time.sleep(2)
        monitor.run()
