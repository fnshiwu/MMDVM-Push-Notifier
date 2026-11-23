# Parser for MMDVMHost log lines | MMDVMHost 日志解析器
#
# Extracts callsign, target, duration, loss, BER, mode, slot
# 提取呼号、群组、时长、丢包、误码、模式、时隙
#
# Compatible with the log formats produced by:
#   - MMDVMHost 2019 ~ 2022  : "end of voice transmission from X to Y, 3.2 seconds"
#   - MMDVMHost 2023 ~ 2026  : "DMR Slot 2, received RF end of voice transmission from X to Y,
#                               3.2 seconds, 0% packet loss, BER: 0.1%, RSSI: -45 dBm"
#   - Multi-mode lines (DMR / D-Star / YSF / P25 / NXDN / M17 / POCSAG / FM)
# 兼容 2019-2026 各版本 MMDVMHost 的日志格式（含 Pi-Star 4.3.x 上的新版）

import re
import logging

# Mode detection | 模式识别（顺序敏感：DMR 放在最前）
_MODE_PATTERNS = (
    ("DMR", re.compile(r'\bDMR\b', re.IGNORECASE)),
    ("D-Star", re.compile(r'\bD-?STAR\b', re.IGNORECASE)),
    ("YSF", re.compile(r'\bYSF\b', re.IGNORECASE)),
    ("P25", re.compile(r'\bP25\b', re.IGNORECASE)),
    ("NXDN", re.compile(r'\bNXDN\b', re.IGNORECASE)),
    ("M17", re.compile(r'\bM17\b', re.IGNORECASE)),
    ("POCSAG", re.compile(r'\bPOCSAG\b', re.IGNORECASE)),
    ("FM", re.compile(r'\bFM\b', re.IGNORECASE)),
)

# Master pattern | 主匹配模式
#   "end of [voice|data] transmission from <call> to <target>, <dur> second(s)[, N% packet loss]
#    [, BER: x.x%][, RSSI: -nn dBm]"
# forward slashes are literal here, no escaping problem
_re_master = re.compile(
    r'end\s+of\s+(?P<v_type>voice\s+|data\s+)?transmission\s+from\s+'
    r'(?P<call>[A-Z0-9][A-Z0-9/\-]*)\s+to\s+'
    r'(?P<target>[^,]+?)\s*,\s*'
    r'(?P<dur>\d+(?:\.\d+)?)\s*(?:seconds?|secs?)'
    r'(?:\s*,\s*(?P<loss>\d+)\s*%\s*packet\s+loss)?'
    r'(?:\s*,\s*BER\s*:\s*(?P<ber>\d+(?:\.\d+)?)\s*%)?'
    r'(?:\s*,\s*RSSI\s*:\s*(?P<rssi>-?\d+(?:\.\d+)?)\s*dBm)?',
    re.IGNORECASE,
)

_re_slot1 = re.compile(r'\bslot\s*1\b', re.IGNORECASE)
_re_slot2 = re.compile(r'\bslot\s*2\b', re.IGNORECASE)


def _detect_mode(line: str) -> str:
    """Detect digital mode from the log line | 从日志行识别数字模式"""
    for name, pattern in _MODE_PATTERNS:
        if pattern.search(line):
            return name
    return ""


def _clean_target(target: str) -> str:
    """Normalise talkgroup / destination field | 规范目标字段"""
    target = " ".join(target.split())
    # "TG 46001" -> keep readable but collapse double spaces
    return target.strip()


def parse_line(line: str):
    """Parse a single log line; return event dict or None | 解析单行日志；返回事件字典或 None"""
    if not line:
        return None

    m = _re_master.search(line)
    if not m:
        return None

    call = m.group('call').upper()
    target = _clean_target(m.group('target'))
    if not call or not target:
        return None

    # Parse and validate duration | 解析并校验时长
    try:
        dur = float(m.group('dur'))
        if dur < 0 or dur > 86400:  # Max 24 hours
            logging.getLogger(__name__).warning("Invalid duration: %ss", dur)
            return None
    except (ValueError, TypeError):
        return None

    # Parse and validate loss percentage | 解析并校验丢包率
    loss_str = m.group('loss') or '0'
    try:
        loss_val = int(loss_str)
        if loss_val < 0 or loss_val > 100:
            logging.getLogger(__name__).warning("Invalid loss percentage: %s%%", loss_val)
            loss_str = '0'
        else:
            loss_str = str(loss_val)
    except (ValueError, TypeError):
        loss_str = '0'

    # Parse and validate BER percentage | 解析并校验误码率
    # Some MMDVMHost builds omit "BER:" entirely (data frames, truncated lines),
    # so the fallback must never resurrect the raw None group.
    # 部分固件（数据帧、被截断的行）不含 BER 字段，兜底值不能被原始分组覆盖。
    ber_str = m.group('ber') or '0.0'
    try:
        ber_val = float(ber_str)
        if ber_val < 0 or ber_val > 100:
            logging.getLogger(__name__).warning("Invalid BER percentage: %s%%", ber_val)
            ber_str = '0.0'
        else:
            ber_str = str(ber_val)
    except (ValueError, TypeError):
        ber_str = '0.0'

    rssi_str = m.group('rssi') or ''
    if rssi_str:
        try:
            rssi_str = str(int(float(rssi_str)))
        except (ValueError, TypeError):
            rssi_str = ''

    v_type = (m.group('v_type') or '').lower()
    is_voice = 'data' not in v_type
    mode = _detect_mode(line)

    slot = ""
    if mode in ("", "DMR"):
        if _re_slot2.search(line):
            slot = " (Slot 2)"
        elif _re_slot1.search(line):
            slot = " (Slot 1)"

    return {
        "call": call,
        "target": target,
        "dur": dur,
        "loss": loss_str,
        "ber": ber_str,
        "rssi": rssi_str,
        "is_voice": is_voice,
        "slot": slot,
        "mode": mode,
    }

