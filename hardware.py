# Hardware metrics module | 硬件指标模块
#
# Reads system metrics: CPU, memory, temperature
# 读取系统指标：CPU、内存、温度

import os
import subprocess
from typing import Tuple, Dict


class Hardware:
    """System hardware metrics reader | 系统硬件指标读取器"""

    def __init__(self):
        self._cpu_prev_total = None
        self._cpu_prev_idle = None
    def _cpu_percent_top(self) -> str:
        """
        Get system CPU usage using top command
        使用 top 命令获取系统 CPU 占用率
        """
        try:
            out = subprocess.getoutput("top -bn1 | grep 'Cpu(s)'")
            if out:
                import re
                m = re.search(r'(\d+(?:\.\d+)?)\s*id', out)
                if m:
                    idle = float(m.group(1))
                    busy = max(0.0, min(100.0, 100.0 - idle))
                    return f"{busy:.1f}"
                comps = {}
                for key in ("us", "sy", "ni", "wa", "hi", "si", "st"):
                    m2 = re.search(r'(\d+(?:\.\d+)?)\s*' + key, out)
                    if m2:
                        comps[key] = float(m2.group(1))
                if comps:
                    busy = sum(comps.values())
                    return f"{busy:.1f}"
        except Exception:
            pass
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
            idleall = idle
            nonidle = user + nice + system + irq + softirq + steal + iowait
            total = idleall + nonidle
            prev_total = self._cpu_prev_total
            prev_idle = self._cpu_prev_idle
            if prev_total is None or prev_idle is None:
                import time as _t
                _t.sleep(1.0)
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
                idleall2 = idle2
                nonidle2 = user2 + nice2 + system2 + irq2 + softirq2 + steal2 + iowait2
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

    def _mem_percent_proc(self) -> str:
        """
        Get memory usage from /proc/meminfo
        从 /proc/meminfo 获取内存占用率
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
        if mt and ma:
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
        except Exception:
            return "0"

    def _cpu_percent_process_top(self) -> str:
        """
        Get process CPU usage using ps command
        使用 ps 命令获取进程 CPU 占用率
        """
        try:
            pid = os.getpid()
            val = subprocess.getoutput(f"ps -p {pid} -o %cpu --no-headers").strip()
            if not val:
                return self._cpu_percent_process(interval=1.0)
            f = float(val)
            return f"{f:.1f}"
        except Exception:
            return self._cpu_percent_process(interval=1.0)

    def get_sys_info(self) -> Tuple[str, str, str]:
        """
        Get system information: IP, CPU, memory
        获取系统信息：IP、CPU、内存

        Returns:
            Tuple of (ip, cpu_percent, mem_percent)
        """
        try:
            ip = subprocess.getoutput("hostname -I").split()[0]
        except (IndexError, Exception):
            ip = "Unknown"
        cpu = self._cpu_percent_top()
        try:
            mem = self._mem_percent_proc()
        except Exception:
            try:
                mem = subprocess.getoutput("free -m | awk 'NR==2{printf \"%.1f%%\", $3*100/$2 }'").strip()
            except Exception:
                mem = "0%"
        return ip, cpu, mem

    def get_current_temp(self, conf: Dict) -> Tuple[str, float]:
        """
        Get current system temperature
        获取当前系统温度

        Args:
            conf: Configuration dict with temp_unit setting

        Returns:
            Tuple of (formatted_string, raw_value)
        """
        try:
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                temp_c = float(f.read().strip()) / 1000.0
            unit = str(conf.get("temp_unit", "C")).upper()
            val = (temp_c * 9/5) + 32 if unit == "F" else temp_c
            return f"{val:.1f}°{unit}", val
        except (FileNotFoundError, ValueError, OSError):
            return "N/A", 0.0

