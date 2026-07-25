# Parser for MMDVMHost log lines | MMDVMHost 日志解析器
#
# Extracts callsign, target, duration, loss, BER, mode, slot
# 提取呼号、群组、时长、丢包、误码、模式、时隙

import re
import logging

_re_master = re.compile(
    r'end of (?P<v_type>(?:voice\s*|data\s*)?)transmission from '
    r'(?P<call>[A-Z0-9/\-]+) to (?P<target>[A-Z0-9/\-\s]+?), '
    r'(?P<dur>\d+\.?\d*) seconds'
    r'(?:, (?P<loss>\d+)% packet loss)?'
    r'(?:, BER: (?P<ber>\d+\.?\d*)%)?',
    re.IGNORECASE
)

def parse_line(line: str):
    # Parse a single log line; return event dict or None
    # 解析单行日志；返回事件字典或 None
    # Optimized: use regex directly without lower() | 优化：直接使用正则表达式，无需 lower()
    m = _re_master.search(line)
    if not m:
        return None
    call = m.group('call').upper()
    target = m.group('target').strip()

    # Parse and validate duration
    try:
        dur = float(m.group('dur'))
        if dur < 0 or dur > 86400:  # Max 24 hours
            logging.getLogger(__name__).warning(f"Invalid duration: {dur}s")
            return None
    except (ValueError, TypeError) as e:
        logging.getLogger(__name__).warning(f"Failed to parse duration '{m.group('dur')}': {e}")
        return None

    # Parse and validate loss percentage
    try:
        loss_str = m.group('loss') or '0'
        loss_val = int(loss_str)
        if loss_val < 0 or loss_val > 100:
            logging.getLogger(__name__).warning(f"Invalid loss percentage: {loss_val}%")
            loss_str = '0'
    except (ValueError, TypeError):
        loss_str = '0'

    # Parse and validate BER percentage
    try:
        ber_str = m.group('ber') or '0.0'
        ber_val = float(ber_str)
        if ber_val < 0 or ber_val > 100:
            logging.getLogger(__name__).warning(f"Invalid BER percentage: {ber_val}%")
            ber_str = '0.0'
    except (ValueError, TypeError):
        ber_str = '0.0'

    v_type = m.group('v_type') or ''
    is_voice = 'data' not in v_type.lower()
    slot = ""
    if "Slot 1" in line:
        slot = " (Slot 1)"
    elif "Slot 2" in line:
        slot = " (Slot 2)"

    return {
        "call": call,
        "target": target,
        "dur": dur,
        "loss": loss_str,
        "ber": ber_str,
        "is_voice": is_voice,
        "slot": slot
    }
