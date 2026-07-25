# Push filters and quiet mode | 推送过滤与静音模式
#
# Includes whitelist/blacklist, min duration, duplicate suppression
# 包含白/黑名单、最小时长、重复抑制

from datetime import datetime
import time
import re
from functools import lru_cache

_SPLIT_RE = re.compile(r'[;；]+')
_CS_RE = re.compile(r'^[A-Z0-9][A-Z0-9/\-]*$')

@lru_cache(maxsize=256)
def _parse_list_cached(s: str):
    items = [item.strip().upper() for item in _SPLIT_RE.split(s) if item.strip()]
    return tuple(i for i in items if _CS_RE.match(i) and not i.isdigit())

def _parse_list(data):
    if isinstance(data, list):
        data = ";".join(map(str, data))
    if not data or not isinstance(data, str):
        return set()
    s = data.strip()
    if not s:
        return set()
    return set(_parse_list_cached(s))

def _validate_time(time_str: str) -> bool:
    """Validate time format HH:MM | 验证时间格式 HH:MM"""
    try:
        parts = time_str.split(':')
        if len(parts) != 2:
            return False
        h, m = int(parts[0]), int(parts[1])
        return 0 <= h <= 23 and 0 <= m <= 59
    except (ValueError, TypeError):
        return False

def quiet_time(conf: dict) -> bool:
    """
    Check if current time is within quiet hours
    检查当前时间是否在静音时段内
    """
    qm = conf.get('quiet_mode', {})
    if not isinstance(qm, dict) or not qm.get('enabled'):
        return False

    start = qm.get('start', '23:00')
    end = qm.get('end', '07:00')

    # Validate format to prevent errors
    if not _validate_time(start) or not _validate_time(end):
        return False

    now_dt = datetime.now()
    now = now_dt.strftime("%H:%M")

    if start <= end:
        return start <= now <= end
    else:
        # Cross-day setting (e.g. 23:00 to 07:00)
        return now >= start or now <= end

def should_push(conf: dict, event: dict, last_msg: dict) -> bool:
    """Decide whether to push based on filters and deduplication | 根据过滤器和去重逻辑判断是否推送"""
    focus = _parse_list(conf.get('focus_list', []))
    ignore = _parse_list(conf.get('ignore_list', []))
    my_callsign = (conf.get('my_callsign', '') or '').upper()
    min_duration = float(conf.get('min_duration', 1.0))
    
    call = event['call']
    target = event['target']
    dur = float(event['dur'])

    # 1. Whitelist check (Focus list)
    if focus and call not in focus:
        return False

    # 2. Blacklist check (Ignore list)
    if call in ignore:
        return False

    # 3. Self suppression & Duration check
    if call == my_callsign or dur < min_duration:
        return False

    # 4. Deduplication logic
    curr_ts = time.time()
    # Improved deduplication: check both call and target
    # 改进的去重：同时检查呼号和目标
    if (call == (last_msg.get("call") or "") and
        target == (last_msg.get("target") or "") and
        (curr_ts - float(last_msg.get("ts") or 0)) < 3):
        return False

    return True
