# Hardware metrics module | 硬件指标模块
#
# Reads system metrics: CPU, memory, temperature
# 读取系统指标：CPU、内存、温度

import os
import time
import subprocess
import logging
import re
from typing import Tuple, Dict

# Constants for performance tuning | 性能调优常量
CPU_CACHE_TIMEOUT = 3.0  # CPU 缓存超时（秒）
TEMP_MIN_CELSIUS = -50.0  # 最低温度（摄氏度）
TEMP_MAX_CELSIUS = 150.0  # 最高温度（摄氏度）
SUBPROCESS_TIMEOUT = 5  # 子进程超时（秒）


class Hardware:
    """System hardware metrics reader | 系统硬件指标读取器"""

    def __init__(self):
        self._cpu_prev_total = None
        self._cpu_prev_idle = None
        self._last_cpu_read = 0.0  # CPU 缓存时间戳
        self._cached_cpu = "0"     # CPU 缓存值
        self._cache_start_time = time.time()  # MEDIUM #12 fix: track cache age

    def _reset_cpu_cache_if_needed(self):
        """Reset CPU cache after 24 hours to prevent overflow (MEDIUM #12 fix)"""
        if time.time() - self._cache_start_time > 86400:
            self._cpu_prev_total = None
            self._cpu_prev_idle = None
            self._last_cpu_read = 0.0
            self._cache_start_time = time.time()
            logging.getLogger(__name__).info("CPU cache reset after 24 hours")
    def _cpu_percent_top(self) -> str:
        """
        Get system CPU usage using top command
        使用 top 命令获取系统 CPU 占用率
        """
        # Reset cache if needed (MEDIUM #12 fix)
        self._reset_cpu_cache_if_needed()

        # 如果距离上次读取不到3秒，直接返回缓存值
        now = time.time()
        if now - self._last_cpu_read < CPU_CACHE_TIMEOUT:
            return self._cached_cpu

        try:
            result = subprocess.run(
                ["top", "-bn1"],
                capture_output=True,
                text=True,
                timeout=SUBPROCESS_TIMEOUT,
                check=False
            )
            out = result.stdout
            if out:
                # Search for Cpu(s) line
                for line in out.splitlines():
                    if 'Cpu(s)' in line or 'cpu(s)' in line.lower():
                        out = line
                        break
                m = re.search(r'(\d+(?:\.\d+)?)\s*id', out)
                if m:
                    idle = float(m.group(1))
                    busy = max(0.0, min(100.0, 100.0 - idle))
                    result_str = f"{busy:.1f}"
                    self._last_cpu_read = now
                    self._cached_cpu = result_str
                    return result_str
                comps = {}
                for key in ("us", "sy", "ni", "wa", "hi", "si", "st"):
                    m2 = re.search(r'(\d+(?:\.\d+)?)\s*' + key, out)
                    if m2:
                        comps[key] = float(m2.group(1))
                if comps:
                    busy = sum(comps.values())
                    result_str = f"{busy:.1f}"
                    self._last_cpu_read = now
                    self._cached_cpu = result_str
                    return result_str
        except Exception as e:
            logging.getLogger(__name__).debug(f"top command failed: {e}")
            # Fallthrough to /proc/stat fallback

        # Fallback to /proc/stat
        try:
            return self._cpu_from_proc_stat()
        except Exception as e:
            logging.getLogger(__name__).debug(f"/proc/stat read failed: {e}")
            return self._cached_cpu if self._cached_cpu else "0"

    def _parse_proc_stat_line(self, parts: list) -> Tuple[int, int]:
        """
        Parse /proc/stat line and return (total, idle)
        解析 /proc/stat 行返回 (总计, 空闲)

        Args:
            parts: Split line from /proc/stat

        Returns:
            Tuple of (total_cpu_time, idle_cpu_time)
        """
        if not parts or parts[0] != "cpu":
            return 0, 0
        nums = [int(x) for x in parts[1:]]
        user = nums[0] if len(nums) > 0 else 0
        nice = nums[1] if len(nums) > 1 else 0
        system = nums[2] if len(nums) > 2 else 0
        idle = nums[3] if len(nums) > 3 else 0
        iowait = nums[4] if len(nums) > 4 else 0
        irq = nums[5] if len(nums) > 5 else 0
        softirq = nums[6] if len(nums) > 6 else 0
        steal = nums[7] if len(nums) > 7 else 0
        idleall = idle
        nonidle = user + nice + system + irq + softirq + steal + iowait
        total = idleall + nonidle
        return total, idleall

    def _cpu_from_proc_stat(self) -> str:
        """
        Get CPU from /proc/stat with caching
        从 /proc/stat 获取 CPU（带缓存）

        Returns:
            CPU usage percentage as string (e.g., "45.2")
        """
        now = time.time()

        with open("/proc/stat", "r") as f:
            parts = f.readline().split()
        total, idleall = self._parse_proc_stat_line(parts)
        if total == 0:
            return "0"

        prev_total = self._cpu_prev_total
        prev_idle = self._cpu_prev_idle

        if prev_total is None or prev_idle is None:
            # First call: sleep and measure again
            time.sleep(1.0)
            with open("/proc/stat", "r") as f2:
                parts2 = f2.readline().split()
            total2, idleall2 = self._parse_proc_stat_line(parts2)
            if total2 == 0:
                return "0"

            totald_i = total2 - total
            idled_i = idleall2 - idleall
            self._cpu_prev_total = total2
            self._cpu_prev_idle = idleall2
            pct_i = 0.0 if totald_i <= 0 else (totald_i - idled_i) * 100.0 / totald_i
            pct_i = max(0.0, min(100.0, pct_i))
            result = f"{pct_i:.1f}"
            self._last_cpu_read = now
            self._cached_cpu = result
            return result

        # Use cached previous values
        self._cpu_prev_total = total
        self._cpu_prev_idle = idleall
        totald = total - prev_total
        idled = idleall - prev_idle
        pct = 0.0 if totald <= 0 else (totald - idled) * 100.0 / totald
        pct = max(0.0, min(100.0, pct))
        result = f"{pct:.1f}"
        self._last_cpu_read = now
        self._cached_cpu = result
        return result

    def _mem_percent_proc(self) -> str:
        """
        Get memory usage from /proc/meminfo
        从 /proc/meminfo 获取内存占用率

        Returns:
            Memory usage percentage as string (e.g., "65.3%")
        """
        mt = ma = None
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    mt = float(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    ma = float(line.split()[1])
                if mt is not None and ma is not None:
                    break
        if mt and ma and mt > 0:  # ISSUE #4 fix: check mt > 0
            used = (mt - ma) / mt * 100.0
            return f"{used:.1f}%"
        return "0%"

    def _cpu_percent_process(self, interval: float = 1.0) -> str:
        """
        Get process CPU usage by reading /proc/stat
        通过读取 /proc/stat 获取进程 CPU 占用率
        """
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
            cpus = os.cpu_count() or 1
            pct = 0.0 if delta_total <= 0 else (delta_proc * 100.0 / delta_total) * cpus
            if pct < 0.0:
                pct = 0.0
            max_pct = 100.0 * cpus
            if pct > max_pct:
                pct = max_pct
            return f"{pct:.1f}"
        except Exception as e:
            logging.getLogger(__name__).debug(f"Process CPU read failed: {e}")
            return "0"

    def _cpu_percent_process_top(self) -> str:
        """
        Get process CPU usage using ps command
        使用 ps 命令获取进程 CPU 占用率
        """
        try:
            pid = os.getpid()
            result = subprocess.run(
                ["ps", "-p", str(pid), "-o", "%cpu", "--no-headers"],
                capture_output=True,
                text=True,
                timeout=SUBPROCESS_TIMEOUT,
                check=False
            )
            val = result.stdout.strip()
            if not val:
                return self._cpu_percent_process(interval=1.0)
            f = float(val)
            return f"{f:.1f}"
        except Exception as e:
            logging.getLogger(__name__).debug(f"ps command failed: {e}")
            return self._cpu_percent_process(interval=1.0)

    def get_sys_info(self) -> Tuple[str, str, str]:
        """
        Get system information: IP, CPU, memory
        获取系统信息：IP、CPU、内存

        Returns:
            Tuple of (ip, cpu_percent, mem_percent)
        """
        try:
            result = subprocess.run(
                ["hostname", "-I"],
                capture_output=True,
                text=True,
                timeout=SUBPROCESS_TIMEOUT,
                check=False
            )
            # ISSUE #17 fix: check array before accessing
            ip_parts = result.stdout.split()
            ip = ip_parts[0] if ip_parts else "Unknown"
        except (IndexError, Exception):
            ip = "Unknown"
        cpu = self._cpu_percent_top()
        try:
            mem = self._mem_percent_proc()
        except Exception as e:
            logging.getLogger(__name__).debug(f"Memory read from /proc failed: {e}")
            try:
                mem = subprocess.getoutput("free -m | awk 'NR==2{printf \"%.1f%%\", $3*100/$2 }'").strip()
            except Exception as e2:
                logging.getLogger(__name__).debug(f"Memory read from free failed: {e2}")
                mem = "0%"
        return ip, cpu, mem

    def get_current_temp(self, conf: Dict) -> Tuple[str, float]:
        """
        Get current system temperature (MEDIUM #10 fix: distinguish error types)
        获取当前系统温度

        Args:
            conf: Configuration dict with temp_unit setting

        Returns:
            Tuple of (formatted_string, raw_value)
            - ("N/A", -1.0) if sensor not available
            - ("ERROR", -2.0) if sensor read error
            - (formatted, value) if successful
        """
        try:
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                temp_c = float(f.read().strip()) / 1000.0

            # Validate temperature is within reasonable bounds
            if temp_c < TEMP_MIN_CELSIUS or temp_c > TEMP_MAX_CELSIUS:
                logging.getLogger(__name__).warning(f"Temperature out of range: {temp_c}°C")
                return "ERROR", -2.0

            unit = str(conf.get("temp_unit", "C")).upper()
            val = (temp_c * 9/5) + 32 if unit == "F" else temp_c
            return f"{val:.1f}°{unit}", val

        except FileNotFoundError:
            # Sensor not available (expected on some systems)
            return "N/A", -1.0
        except (ValueError, OSError) as e:
            # Sensor read error (unexpected)
            logging.getLogger(__name__).error(f"Temperature sensor error: {e}")
            return "ERROR", -2.0

