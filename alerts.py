# Alert management module | 告警管理模块
#
# Handles temperature and system alerts
# 处理温度和系统告警

import time
from typing import Optional, Tuple, Dict
from hardware import Hardware
from filters import should_temp_alert
from notify_fmt import format_temp_alert


class AlertManager:
    """Manages system alerts with rate limiting | 管理系统告警并限制频率"""

    def __init__(self, hardware: Hardware):
        self.hardware = hardware
        self.last_temp_alert_time: float = 0.0
        self.last_temp_check_time: float = 0.0

    def check_temp_alert(self, conf: Dict) -> Optional[Tuple[str, str]]:
        """
        Check if temperature alert should be triggered
        检查是否应触发温度告警

        Returns:
            Tuple of (title, body) if alert should be sent, None otherwise
            如果需要发送告警则返回 (标题, 正文)，否则返回 None
        """
        now = time.time()

        # Use configurable temp_interval instead of hardcoded 60 seconds | 使用可配置的 temp_interval 而非硬编码的60秒
        temp_interval = int(conf.get('temp_interval', 30))
        if now - self.last_temp_check_time < temp_interval:
            return None

        self.last_temp_check_time = now

        # Get current temperature
        display_str, current_val = self.hardware.get_current_temp(conf)

        # Check if alert should be triggered
        if should_temp_alert(conf, self.last_temp_alert_time, now, current_val):
            self.last_temp_alert_time = now
            threshold = float(conf.get("temp_threshold", 65.0))
            return format_temp_alert(conf, display_str, threshold)

        return None
