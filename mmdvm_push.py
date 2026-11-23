#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MMDVM-Push-Notifier core service.

Parses MMDVMHost logs and pushes QSO / system notifications.
日志轮询 → 解析 → 过滤 → 推送。

Validated on Pi-Star 4.2.x (Bullseye) and Pi-Star 4.3.x (Bookworm, Python 3.11).
Tested against Python 3.9 - 3.13 (no removed/deprecated stdlib APIs).
"""
import os
import sys
import json
import glob
import time
import signal
import socket
import logging
import atexit
import tempfile
import platform
import threading
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Any, List

from parser import parse_line
from filters import quiet_time, should_push, forget_pushed
from notify_fmt import format_message, format_boot_notice, format_test_push
from identity import Identity
from hardware import Hardware
from alerts import AlertManager
from notifier import PushService
from config import ConfigManager

# =========================
# Global Constants | 全局常量
# =========================
VERSION = "v3.6.3"
CONFIG_FILE = os.environ.get("MMDVM_PUSH_CONFIG", "/etc/mmdvm_push.json")
LOCAL_ID_FILE = "/usr/local/etc/nextionUsers.csv"

# Log discovery | 日志目录探测（Pi-Star 4.2.x / 4.3.x 首选 /var/log/pi-star）
DEFAULT_LOG_DIR = "/var/log/pi-star"
LOG_DIR_CANDIDATES = ("/var/log/pi-star", "/var/log/mmdvm", "/var/log/mmdvmhost", "/var/log")
LOG_GLOBS = ("MMDVM-*.log", "MMDVM*.log", "mmdvmhost*.log", "mmdvm*.log")

MEMORY_CHECK_INTERVAL = 3600   # Seconds between self memory audits
MEMORY_THRESHOLD_KB = 96 * 1024  # Warn above 96 MB RSS
LOG_CHECK_INTERVAL = 5         # Seconds between rotation/truncation checks
MAX_LOG_ITERATIONS = 200000    # Max read loop iterations before reopening
STALE_LOG_WARN = 900           # Warn if the MMDVM log has not been written for 15 min
BOOT_NOTICE_ATTEMPTS = 5
BOOT_NOTICE_INTERVAL = 6

RUNNING = True


def _install_signal_handlers():
    """SIGTERM from systemd must exit cleanly so atexit can flush pushes."""
    def _handler(signum, frame):
        global RUNNING
        RUNNING = False
        logging.getLogger(__name__).info("Signal %s received, shutting down", signum)
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _handler)
        except (ValueError, OSError):
            pass


# =========================
# Environment & Version Detection | 环境与版本探测
# =========================
def _read_first_line(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            return fh.readline().strip()
    except OSError:
        return ""


PISTAR_VERSION = "unknown"
try:
    with open("/etc/pistar-release", "r", encoding="utf-8", errors="ignore") as _f:
        for _line in _f:
            if _line.startswith("Version="):
                PISTAR_VERSION = _line.strip().split("=", 1)[1].strip()
                break
except OSError:
    pass

DEBIAN_VERSION = _read_first_line("/etc/debian_version") or "unknown"
IS_BOOKWORM = DEBIAN_VERSION.startswith("12")
IS_TRIXIE = DEBIAN_VERSION.startswith("13")
if not IS_BOOKWORM and not IS_TRIXIE:
    # EXTERNALLY-MANAGED is the reliable marker on Debian 12+
    if glob.glob("/usr/lib/python3*/EXTERNALLY-MANAGED"):
        IS_BOOKWORM = True
PYTHON_VERSION = platform.python_version()

# Logging target | 日志目录
APP_LOG_DIR = "/var/log/pi-star/"
_APP_LOG_FILE = os.path.join(APP_LOG_DIR, "mmdvm_push.log")
# The directory may be root-owned (0755) while the log file itself is owned by the
# service user - accept either way before falling back to /tmp.
# 目录可能属 root，但日志文件已授权给服务用户，两种可写都算正常。
if not (os.path.isdir(APP_LOG_DIR)
        and (os.access(APP_LOG_DIR, os.W_OK) or os.access(_APP_LOG_FILE, os.W_OK))):
    APP_LOG_DIR = tempfile.gettempdir()

logger = logging.getLogger(__name__)


def setup_logging(quiet: bool = False):
    """Configure file + console logging. quiet=True keeps stdout clean (JSON modes)."""
    global logger
    handlers = []
    try:
        handlers.append(logging.FileHandler(os.path.join(APP_LOG_DIR, "mmdvm_push.log"),
                                            encoding="utf-8"))
    except (OSError, PermissionError):
        pass

    if not quiet:
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        handlers.append(console)

    formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s',
                                  datefmt='%Y-%m-%d %H:%M:%S')
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    for h in handlers:
        h.setFormatter(formatter)
        root.addHandler(h)
    if not handlers:
        root.addHandler(logging.NullHandler())
    root.setLevel(logging.INFO)
    logger = logging.getLogger(__name__)
    return logger


def _log_startup_banner():
    logger.info("MMDVM-Push-Notifier %s starting (pid %s)", VERSION, os.getpid())
    logger.info("Pi-Star %s / Debian %s / Python %s (bookworm=%s trixie=%s)",
                PISTAR_VERSION, DEBIAN_VERSION, PYTHON_VERSION, IS_BOOKWORM, IS_TRIXIE)


atexit.register(PushService.shutdown)


# =========================
# Log file helpers | 日志文件辅助函数
# =========================
def list_mmdvm_logs(directory: str) -> List[str]:
    """Return existing MMDVM log candidates inside a directory."""
    if not directory or not os.path.isdir(directory):
        return []
    found: List[str] = []
    for pattern in LOG_GLOBS:
        found.extend(glob.glob(os.path.join(directory, pattern)))
    return [p for p in found if os.path.isfile(p)]


def _usable(path: str) -> bool:
    """File exists, is not empty and is readable by the service user."""
    try:
        return os.path.isfile(path) and os.path.getsize(path) > 0 and os.access(path, os.R_OK)
    except OSError:
        return False


# =========================
# Monitor Logic | 监控逻辑
# =========================
class MMDVMMonitor:
    def __init__(self):
        self.last_msg: Dict[str, Any] = {"call": "", "target": "", "ts": 0}
        # Per-(call, target) dedup timestamps, so A-B-A alternation is handled
        # 按 (呼号, 目标) 记录去重时间，A-B-A 交替不会再重复推送
        self._seen: Dict[Any, float] = {}
        self._dedup_lock = threading.Lock()
        self.hw = Hardware()
        self.alerts = AlertManager(self.hw)
        self.identity = Identity(LOCAL_ID_FILE)
        self.last_activity_ts: float = 0.0
        self._last_temp_check: float = 0.0
        self._log_dir_cache: Optional[str] = None
        self._log_dir_ts: float = 0.0
        self.current_log: Optional[str] = None
        self._stale_warned_at: float = 0.0

    # ---------- log discovery ----------
    def resolve_log_dir(self, conf: Optional[Dict] = None) -> str:
        """Pick the MMDVM log directory, honouring env/config overrides."""
        now = time.time()
        if self._log_dir_cache and now - self._log_dir_ts < 60:
            return self._log_dir_cache

        conf = conf or {}
        candidates = [os.environ.get("MMDVM_LOG_DIR", ""), conf.get("log_dir", "")]
        for candidate in candidates:
            if candidate and os.path.isdir(candidate):
                self._log_dir_cache, self._log_dir_ts = candidate, now
                return candidate

        # Prefer directories that really contain MMDVM logs
        for directory in LOG_DIR_CANDIDATES:
            if list_mmdvm_logs(directory):
                self._log_dir_cache, self._log_dir_ts = directory, now
                return directory
        for directory in LOG_DIR_CANDIDATES:
            if os.path.isdir(directory):
                self._log_dir_cache, self._log_dir_ts = directory, now
                return directory

        self._log_dir_cache, self._log_dir_ts = DEFAULT_LOG_DIR, now
        return DEFAULT_LOG_DIR

    def get_latest_log(self, conf: Optional[Dict] = None) -> Optional[str]:
        """Return the newest usable MMDVM log (UTC name first, then local date)."""
        try:
            dirs: List[str] = []
            primary = self.resolve_log_dir(conf)
            dirs.append(primary)
            for directory in LOG_DIR_CANDIDATES:
                if directory not in dirs:
                    dirs.append(directory)

            now_utc = datetime.now(timezone.utc)
            now_local = datetime.now()
            dates = [now_utc.date(), now_local.date(),
                     now_utc.date() - timedelta(days=1), now_local.date() - timedelta(days=1)]

            seen = set()
            for directory in dirs:
                for day in dates:
                    candidate = os.path.join(directory, "MMDVM-%s.log" % day.isoformat())
                    if candidate in seen:
                        continue
                    seen.add(candidate)
                    if _usable(candidate):
                        return candidate

            files: List[str] = []
            for directory in dirs:
                files.extend(list_mmdvm_logs(directory))
            files = [f for f in files if _usable(f)]
            if files:
                return max(files, key=os.path.getmtime)
        except Exception as e:
            logger.error("Error finding log file: %s", e)
        return None

    # ---------- network ----------
    @staticmethod
    def _probe_network() -> bool:
        """Cheap connectivity probe: TCP 53 first, HTTP 204 as fallback."""
        for host, port in (("223.5.5.5", 53), ("1.1.1.1", 53), ("8.8.8.8", 53)):
            try:
                with socket.create_connection((host, port), timeout=3):
                    return True
            except OSError:
                continue
        import urllib.request
        for url in ("https://connectivitycheck.gstatic.com/generate_204",
                    "http://connectivitycheck.platform.hicloud.com/generate_204"):
            try:
                with urllib.request.urlopen(url, timeout=4) as resp:
                    if resp.status in (200, 204):
                        return True
            except Exception:
                continue
        return False

    def check_network(self, max_attempts: int = 30, interval: float = 2) -> bool:
        logger.info("Starting network check...")
        for attempt in range(max_attempts):
            if not RUNNING:
                return False
            if self._probe_network():
                logger.info("Network ready (attempt %s)", attempt + 1)
                return True
            time.sleep(interval)
        logger.warning("Network check timed out")
        return False

    # ---------- system helpers ----------
    def _send_boot_notice(self, conf: Dict, network_ok: bool):
        if not PushService.has_channel(conf):
            logger.warning("Boot notice skipped: no push channel enabled yet")
            return
        ip, cpu, mem = self.hw.get_sys_info()
        temp_str, _ = self.hw.get_current_temp(conf)
        title, body = format_boot_notice(conf, VERSION, ip, temp_str, cpu, mem, network_ok)
        for attempt in range(BOOT_NOTICE_ATTEMPTS):
            if not RUNNING:
                return
            if PushService.send(conf, title, body, is_voice=False, async_mode=False):
                logger.info("Boot notice delivered on attempt %s", attempt + 1)
                return
            time.sleep(BOOT_NOTICE_INTERVAL)
        logger.error("Boot notice could not be delivered, giving up")

    def _proc_mem_rss_kb(self) -> str:
        try:
            with open("/proc/%d/status" % os.getpid(), "r", encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("VmRSS:"):
                        parts = line.split()
                        return parts[1] if len(parts) >= 2 else "0"
            return "0"
        except Exception:
            return "0"

    # ---------- main loop ----------
    def run(self):
        conf = ConfigManager.get_config(CONFIG_FILE)
        log_dir = self.resolve_log_dir(conf)
        logger.info("Using MMDVM log directory: %s", log_dir)
        if not list_mmdvm_logs(log_dir):
            logger.warning("No MMDVM log found in %s yet (MMDVMHost may not have written one)",
                           log_dir)

        network_ok = self.check_network()
        if conf.get('boot_push_enabled', True):
            self._send_boot_notice(conf, network_ok)

        logger.info("%s Monitor ready, tailing logs...", VERSION)
        last_mem_check = time.time()
        self._last_temp_check = time.time()

        while RUNNING:
            try:
                # 1. Resource self-audit (hourly) | 每小时自查内存
                if time.time() - last_mem_check > MEMORY_CHECK_INTERVAL:
                    try:
                        rss_kb = int(self._proc_mem_rss_kb())
                        if rss_kb > MEMORY_THRESHOLD_KB:
                            logger.warning("High memory usage: %s KB", rss_kb)
                    except (TypeError, ValueError):
                        pass
                    last_mem_check = time.time()

                # 2. Log tailing | 日志跟踪
                conf = ConfigManager.get_config(CONFIG_FILE)
                current_log = self.get_latest_log(conf)
                if not current_log:
                    self._warn_no_log(conf)
                    self._maybe_temp_alert(conf)
                    time.sleep(5)
                    continue

                self.current_log = current_log
                self._tail_log(current_log)

            except KeyboardInterrupt:
                logger.info("Shutdown signal received.")
                break
            except Exception as e:
                logger.error("Main loop error: %s", e)
                time.sleep(5)

    def _warn_no_log(self, conf: Dict):
        """Explain once an hour why nothing is being monitored."""
        now = time.time()
        if now - self._stale_warned_at < 3600:
            return
        self._stale_warned_at = now
        directory = self.resolve_log_dir(conf)
        if not os.path.isdir(directory):
            logger.error("MMDVM log directory %s does not exist. "
                         "Check MMDVMHost / permission (service user must be able to read it).",
                         directory)
        else:
            logger.warning("No readable MMDVM-*.log in %s. "
                           "If MMDVMHost is running, check: ls -l %s", directory, directory)

    def _maybe_temp_alert(self, conf: Dict):
        """Send the temperature alert when its interval elapsed | 到点则检查并推送温度告警

        Shared by the tail loop and the "no log file" branch of run(), so a hotspot
        without an MMDVM log still gets overheating alerts.
        日志循环与「没有日志文件」分支共用，没有 MMDVM 日志时也能收到高温告警。
        """
        try:
            interval = float(conf.get('temp_interval', 1800))  # Already in seconds
        except (TypeError, ValueError):
            interval = 1800
        now_ts = time.time()
        if now_ts - self._last_temp_check <= interval:
            return
        try:
            alert_res = self.alerts.check_temp_alert(conf)
            if alert_res:
                title, body = alert_res
                PushService.send(conf, title, body, is_voice=False)
                logger.info("Temperature alert pushed")
        except Exception as e:
            logger.error("Temperature alert error: %s", e)
        self._last_temp_check = now_ts

    def _tail_log(self, log_file: str):
        iteration_count = 0
        start_time = time.time()

        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as fh:
                fh.seek(0, 2)
                st_open = os.fstat(fh.fileno())
                inode = st_open.st_ino
                # fh.tell() on a text stream is an opaque cookie, not a byte offset,
                # so truncation is detected by comparing successive stat() sizes.
                # 文本流的 tell() 是不透明 cookie，不能与 st_size 比较；改用两次 stat 的尺寸差判断截断。
                last_size = st_open.st_size
                last_check = time.time()

                while RUNNING:
                    iteration_count += 1

                    if time.time() - start_time > 3600:
                        iteration_count = 0
                        start_time = time.time()

                    if iteration_count > MAX_LOG_ITERATIONS:
                        logger.info("Max iterations reached, reloading log file...")
                        return

                    # Temperature alert is scheduled here (single owner) | 温度告警调度
                    conf = ConfigManager.get_config(CONFIG_FILE)
                    self._maybe_temp_alert(conf)

                    # Rotation / truncation / stale detection | 轮转、截断、静默检测
                    if time.time() - last_check > LOG_CHECK_INTERVAL:
                        last_check = time.time()
                        try:
                            st = os.stat(log_file)
                        except OSError:
                            return

                        if st.st_ino != inode:
                            logger.info("Log file was replaced (rotation), reopening")
                            return

                        if st.st_size < last_size:
                            # The file was rewritten from offset 0. Re-reading it
                            # would replay every historical QSO as a new event
                            # (dedup only covers a few seconds). Return so the main
                            # loop reopens the current log and tails from its end.
                            # 截断重写后从头读会把历史通联当新事件重推；返回让主循环
                            # 重新打开文件、从末尾继续跟踪。
                            logger.info("Log file was truncated (%s -> %s bytes), "
                                        "reopening from end to avoid replaying old entries",
                                        last_size, st.st_size)
                            return
                        last_size = st.st_size

                        new_log = self.get_latest_log(conf)
                        if new_log and os.path.abspath(new_log) != os.path.abspath(log_file):
                            for line in fh.readlines():
                                self.process_line(line)
                            return

                        if time.time() - st.st_mtime > STALE_LOG_WARN:
                            if time.time() - self._stale_warned_at > 3600:
                                self._stale_warned_at = time.time()
                                logger.warning(
                                    "No new MMDVM log lines for %d min (%s). "
                                    "Is MMDVMHost running and logging?",
                                    int((time.time() - st.st_mtime) / 60), log_file)

                    line = fh.readline()
                    if not line:
                        idle_time = time.time() - self.last_activity_ts
                        sleep_time = 0.3 if idle_time < 60 else (0.5 if idle_time < 300 else 1.0)
                        time.sleep(sleep_time)
                        continue

                    self.process_line(line)

        except Exception as e:
            logger.error("Tail log error: %s", e)

    def _on_push_done(self, future, event: Dict[str, Any]):
        """Release the dedup entry when delivery failed | 推送失败时释放去重记录"""
        try:
            ok = future.result()
        except Exception as e:
            logger.debug("Push future failed: %s", e)
            ok = False
        if ok:
            return

        # The tail thread also mutates _seen inside should_push(); this callback
        # runs on a push worker. Both sides must hold the same lock or pruning
        # can iterate a dict that is being popped (RuntimeError kills the tail).
        # tail 线程在 should_push() 中改 _seen，本回调在推送线程执行，必须共用同一把锁。
        with self._dedup_lock:
            forget_pushed(self._seen, event)
            if (self.last_msg.get("call") == event['call'] and
                    self.last_msg.get("target") == event['target']):
                self.last_msg = {"call": "", "target": "", "ts": 0}
        logger.warning("Push failed for %s -> %s, dedup entry released (will retry on next line)",
                       event['call'], event['target'])

    def process_line(self, line: str):
        event = parse_line(line)
        if not event:
            return

        conf = ConfigManager.get_config(CONFIG_FILE)

        if quiet_time(conf):
            return

        with self._dedup_lock:
            should = should_push(conf, event, self.last_msg, self._seen)
        if not should:
            return

        curr_ts = time.time()
        with self._dedup_lock:
            self.last_msg.update({"call": event['call'],
                                  "target": event['target'],
                                  "ts": curr_ts})
        self.last_activity_ts = curr_ts

        try:
            info = self.identity.get_info(event['call'])
        except Exception as e:
            logger.debug("Identity lookup failed for %s: %s", event['call'], e)
            info = {"name": "", "loc_en": "Unknown", "loc_cn": "未知"}

        temp_str, _ = self.hw.get_current_temp(conf)
        type_label, body = format_message(conf, event, temp_str, info)

        future = PushService.send(conf, type_label, body, is_voice=event['is_voice'])
        if future is not None:
            future.add_done_callback(lambda f, ev=dict(event): self._on_push_done(f, ev))
            logger.info("Push queued: %s -> %s (%ss%s)",
                        event['call'], event['target'], event['dur'],
                        (", " + event['mode']) if event.get('mode') else "")
        else:
            # Dropped (queue full / no channel): release the dedup entry so the
            # next line for this QSO can still be delivered.
            # 被丢弃（队列满/无可用通道）：释放去重记录，同一通联的下一行仍可补推。
            with self._dedup_lock:
                forget_pushed(self._seen, event)
                if (self.last_msg.get("call") == event['call'] and
                        self.last_msg.get("target") == event['target']):
                    self.last_msg = {"call": "", "target": "", "ts": 0}
            logger.warning("Push not queued for %s -> %s (dropped or no channel)",
                           event['call'], event['target'])

    # ---------- health ----------
    def health(self) -> Dict[str, Any]:
        conf = ConfigManager.get_config(CONFIG_FILE)
        ip, cpu_sys, mem_sys = self.hw.get_sys_info()
        try:
            cpu_proc = self.hw._cpu_percent_process(interval=0.1)
        except Exception:
            cpu_proc = "0"
        try:
            rss_kb = self._proc_mem_rss_kb()
        except Exception:
            rss_kb = "0"

        log_dir = self.resolve_log_dir(conf)
        latest = self.current_log if self.current_log and os.path.exists(self.current_log) \
            else self.get_latest_log(conf)

        log_dir_readable = os.path.isdir(log_dir) and os.access(log_dir, os.R_OK)
        sample = ("M: 2026-05-01 12:00:00.000 DMR Slot 2, received RF end of voice transmission "
                  "from BA4SMQ to TG 46001, 3.4 seconds, 0% packet loss, BER: 0.1%, RSSI: -45 dBm")
        parser_ok = False
        try:
            parser_ok = parse_line(sample) is not None
        except Exception:
            parser_ok = False

        push_fail = _recent_push_failures()

        return {
            "version": VERSION,
            "pistar_version": PISTAR_VERSION,
            "debian_version": DEBIAN_VERSION,
            "python_version": PYTHON_VERSION,
            "is_bookworm": IS_BOOKWORM,
            "is_trixie": IS_TRIXIE,
            "app_log_dir": APP_LOG_DIR,
            "app_log_file": os.path.join(APP_LOG_DIR, "mmdvm_push.log"),
            "app_log_dir_writable": os.access(APP_LOG_DIR, os.W_OK),
            # Pi-Star keeps /var/log/pi-star root-owned 0755: only the pre-created
            # file is writable by the service user, so check both.
            # Pi-Star 的日志目录属 root，只有预创建的文件对服务用户可写，两者都要看。
            "app_log_writable": (os.access(APP_LOG_DIR, os.W_OK) or
                                 os.access(os.path.join(APP_LOG_DIR, "mmdvm_push.log"), os.W_OK)),
            "log_dir": log_dir,
            "mmdvm_log_dir": log_dir,
            "mmdvm_log_exists": os.path.isdir(log_dir),
            "mmdvm_log_readable": log_dir_readable,
            "current_log": latest or "",
            "current_log_readable": bool(latest and _usable(latest)),
            "service_user": _current_user(),
            "config_path": CONFIG_FILE,
            "config_exists": os.path.exists(CONFIG_FILE),
            "config_valid": _config_is_valid(),
            "parser_selftest": parser_ok,
            "push_failures_recent": push_fail["count"],
            "push_failure_last": push_fail["last"],
            "ip": ip,
            "cpu_system": "%s%%" % cpu_sys,
            "cpu_process": "%s%%" % cpu_proc,
            "mem": mem_sys,
            "mem_rss_kb": rss_kb,
            "time": datetime.now().isoformat(timespec="seconds"),
        }


def _recent_push_failures(tail_bytes: int = 65536):
    """Count PUSH_FAILED markers in the tail of the app log | 统计日志尾部的推送失败

    The service writes one ``PUSH_FAILED`` line per undelivered notification, so the
    panel can surface "you missed N pushes" without any IPC.
    服务每次推送失败都会写一行 PUSH_FAILED，面板据此提示漏推次数，无需 IPC。
    """
    path = os.path.join(APP_LOG_DIR, "mmdvm_push.log")
    try:
        with open(path, "rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - tail_bytes))
            data = fh.read().decode("utf-8", errors="replace")
    except OSError:
        return {"count": 0, "last": ""}
    lines = [ln for ln in data.splitlines() if "PUSH_FAILED" in ln]
    return {"count": len(lines), "last": lines[-1].strip()[:200] if lines else ""}


def _config_is_valid() -> bool:
    """True only when the on-disk JSON parses | 只有磁盘上的 JSON 能解析才算有效"""
    if not os.path.exists(CONFIG_FILE):
        return False
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
            return isinstance(json.load(fh), dict)
    except (OSError, ValueError):
        return False


def _current_user() -> str:
    try:
        import pwd
        return pwd.getpwuid(os.getuid()).pw_name
    except Exception:
        pass
    try:
        import getpass
        return getpass.getuser()
    except Exception:
        return os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"


# =========================
# Entry
# =========================
def _print_json(payload: Dict[str, Any]):
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main() -> int:
    arg = sys.argv[1].lower() if len(sys.argv) > 1 else ""

    if arg == "--version":
        print(VERSION)
        return 0

    if arg == "--parse":
        setup_logging(quiet=True)
        text = " ".join(sys.argv[2:]).strip()
        event = parse_line(text) if text else None
        _print_json(event or {"matched": False})
        return 0 if event else 1

    if arg == "--selftest":
        setup_logging(quiet=True)
        monitor = MMDVMMonitor()
        status = monitor.health()
        _print_json({"parser_selftest": status["parser_selftest"],
                     "version": VERSION,
                     "log_dir": status["log_dir"],
                     "current_log": status["current_log"]})
        return 0 if status["parser_selftest"] else 1

    if arg == "--health":
        setup_logging(quiet=True)
        try:
            _print_json(MMDVMMonitor().health())
            return 0
        except Exception as e:
            _print_json({"error": str(e), "config_valid": False, "version": VERSION})
            return 1

    if arg == "--test":
        setup_logging()
        monitor = MMDVMMonitor()
        conf = ConfigManager.get_config(CONFIG_FILE)
        ip, cpu, mem = monitor.hw.get_sys_info()
        temp_str, _ = monitor.hw.get_current_temp(conf)
        title, body = format_test_push(conf, VERSION, ip, temp_str, cpu, mem)
        ok = PushService.send(conf, title, body, is_voice=False, async_mode=False)
        if ok:
            print("Success")
            logger.info("Test push delivered")
            return 0
        print("Failed: no channel accepted the message (check enable flags, tokens, network)")
        logger.error("Test push failed")
        return 1

    setup_logging()
    _install_signal_handlers()
    _log_startup_banner()

    monitor = MMDVMMonitor()
    monitor.run()

    logger.info("MMDVM-Push-Notifier stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
