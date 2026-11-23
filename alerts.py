# Alert management module | 告警管理模块
#
# Handles temperature and system alerts logic
# 处理温度和系统告警逻辑 (Logic decoupled from scheduling)

import logging
from typing import Optional, Tuple, Dict
from hardware import Hardware
from notify_fmt import format_temp_alert

# Cooling required before the alert re-arms | 温度需回落到阈值以下多少才重新武装
DEFAULT_HYSTERESIS = 3.0


class AlertManager:
    """
    Manages system alerts logic.
    管理系统告警逻辑。

    Refactored to remove internal scheduling/rate-limiting.
    Scheduling is now fully controlled by the main loop in mmdvm_push.py.
    重构后移除了内部的调度/频率限制，现在完全由主循环控制。

    A temperature alert uses rising-edge triggering with hysteresis: it fires once
    when the temperature crosses the threshold and stays silent until the sensor
    reads ``threshold - hysteresis`` again. Without this, a hotspot hovering at
    the threshold pushed an alert on every check interval.
    高温告警采用上升沿 + 迟滞：越过阈值只报一次，直到温度回落到
    `阈值 - 迟滞` 以下才重新武装。否则温度在阈值附近抖动时会反复推送。
    """

    def __init__(self, hardware: Hardware, hysteresis: float = DEFAULT_HYSTERESIS):
        self.hardware = hardware
        self._hysteresis = hysteresis
        self._armed = True

    @property
    def armed(self) -> bool:
        """True when the next threshold crossing will fire | 下次越限是否会触发"""
        return self._armed

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

        # Handle sensor errors: keep the current state, do not re-arm blindly
        # 传感器异常时保持状态，避免异常读数反复触发/复位
        if current_val < -1.5:  # -2.0 is ERROR
            return None

        # 3. Check Threshold logic
        threshold = float(conf.get('temp_threshold', 65.0))
        try:
            hysteresis = max(0.5, float(conf.get('temp_hysteresis', self._hysteresis)))
        except (TypeError, ValueError):
            hysteresis = self._hysteresis

        if current_val > threshold:
            if self._armed:
                self._armed = False
                logging.getLogger(__name__).info(
                    "Temp alert fired at %.1f (threshold %.1f), will re-arm below %.1f",
                    current_val, threshold, threshold - hysteresis)
                return format_temp_alert(conf, display_str, threshold)
            return None

        # Below threshold: re-arm only after a clear cooldown
        # 回落到阈值以下足够幅度后才重新武装
        if not self._armed and current_val < threshold - hysteresis:
            self._armed = True
            logging.getLogger(__name__).info(
                "Temp alert re-armed at %.1f (cooldown below %.1f)",
                current_val, threshold - hysteresis)
        return None
