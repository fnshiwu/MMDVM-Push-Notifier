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

def re_split(data: str):
    return [s for s in _SPLIT_RE.split(data) if s.strip()]

def quiet_time(conf: dict) -> bool:
    # Check quiet time window; supports cross-day ranges
    # 检查静音时段窗口；支持跨天时间范围
    qc = conf.get('quiet_mode', {})
    if not qc.get('enabled'):
        return False
    now = datetime.now().strftime("%H:%M")
    start = qc.get('start', '23:00')
    end = qc.get('end', '07:00')
    if start <= end:
        return start <= now <= end
    return now >= start or now <= end

def should_push(conf: dict, event: dict, last_msg: dict) -> bool:
    # Decide whether to push based on config and deduplication
    # 根据配置与去重逻辑判断是否推送
    focus = _parse_list(conf.get('focus_list', []))
    ignore = _parse_list(conf.get('ignore_list', []))
    my_callsign = (conf.get('my_callsign', '') or '').upper()
    min_duration = float(conf.get('min_duration', 1.0))
    call = event['call']
    dur = float(event['dur'])
    if focus and call not in focus:
        return False
    if call == my_callsign or call in ignore or dur < min_duration:
        return False
    curr_ts = time.time()
    if call == (last_msg.get("call") or "") and (curr_ts - float(last_msg.get("ts") or 0)) < 3:
        return False
    return True
def should_temp_alert(conf: dict, last_alert_time: float, now: float, current_val: float) -> bool:
    if not conf.get('temp_alert_enabled'):
        return False
    threshold = float(conf.get('temp_threshold', 65.0))
    if current_val < threshold:
        return False
    interval_sec = int(conf.get('temp_interval', 30)) * 60
    return (now - last_alert_time) > interval_sec
