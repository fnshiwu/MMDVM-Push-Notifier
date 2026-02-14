# Alert management module | 告警管理模块
#
# Handles temperature and system alerts logic
# 处理温度和系统告警逻辑 (Logic decoupled from scheduling)

from typing import Optional, Tuple, Dict
from hardware import Hardware
from notify_fmt import format_temp_alert

class AlertManager:
    """
    Manages system alerts logic.
    管理系统告警逻辑。
    
    Refactored to remove internal scheduling/rate-limiting. 
    Scheduling is now fully controlled by the main loop in mmdvm_push.py.
    重构后移除了内部的调度/频率限制，现在完全由主循环控制。
    """

    def __init__(self, hardware: Hardware):
        self.hardware = hardware

    def check_temp_alert(self, conf: Dict) -> Optional[Tuple[str, str]]:
        """
        Check if temperature alert should be triggered immediately.
        检查是否应立即触发温度告警。

        Args:
            conf: Current configuration dictionary

        Returns:
            Tuple of (title, body) if alert should be sent, None otherwise
        """
        # 1. Check if feature is enabled globally
        if not conf.get('temp_alert_enabled', True):
            return None

        # 2. Get current hardware metrics
        display_str, current_val = self.hardware.get_current_temp(conf)

        # Handle sensor errors
        if current_val < -1.5:  # -2.0 is ERROR
            return None

        # 3. Check Threshold logic
        # Get threshold from config (default 65.0)
        threshold = float(conf.get('temp_threshold', 65.0))

        if current_val > threshold:
            # Threshold exceeded, generate alert message
            # 超过阈值，生成告警消息
            return format_temp_alert(conf, display_str, current_val, threshold)
            
        return None
