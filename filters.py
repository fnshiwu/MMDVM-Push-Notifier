# Push filters and quiet mode | 推送过滤与静音模式
#
# Includes whitelist/blacklist, min duration, duplicate suppression
# 包含白/黑名单、最小时长、重复抑制

from datetime import datetime
import time
import re
from functools import lru_cache

# Accept ";" "；" "," "，" and whitespace as separators | 支持中英文分号、逗号、空白分隔
_SPLIT_RE = re.compile(r'[;；,，\s]+')
_CS_RE = re.compile(r'^[A-Z0-9][A-Z0-9/\-]*$')

# Dedup store growth guards | 去重表容量上限
_MAX_SEEN_ENTRIES = 512   # Start pruning above this | 超过后开始清理过期项
_HARD_SEEN_ENTRIES = 4096  # Absolute ceiling: reset rather than leak | 硬上限，超出直接清空


@lru_cache(maxsize=256)
def _parse_list_cached(s: str):
    items = [item.strip().upper() for item in _SPLIT_RE.split(s) if item.strip()]
    return tuple(i for i in items if _CS_RE.match(i) and not i.isdigit())


def _parse_list(data):
    if isinstance(data, (list, tuple, set)):
        data = ";".join(map(str, data))
    if not data or not isinstance(data, str):
        return set()
    s = data.strip()
    if not s:
        return set()
    return set(_parse_list_cached(s))


def _base_call(call: str) -> str:
    """Strip SSID suffix: BA4SMQ-1 -> BA4SMQ | 去掉 SSID 后缀"""
    return (call or "").split("-")[0].upper()


def _validate_time(time_str: str) -> bool:
    """Validate time format HH:MM | 验证时间格式 HH:MM"""
    try:
        parts = str(time_str).split(':')
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

    now = datetime.now().strftime("%H:%M")

    if start <= end:
        return start <= now <= end
    # Cross-day setting (e.g. 23:00 to 07:00) | 跨天设置
    return now >= start or now <= end


def _prune_seen(seen: dict, now: float, window: float):
    """Drop entries that can no longer block anything | 清理已过期的去重记录"""
    if len(seen) <= _MAX_SEEN_ENTRIES:
        return
    cutoff = now - max(window, 1.0)
    for key in [k for k, ts in seen.items() if ts < cutoff]:
        seen.pop(key, None)
    if len(seen) > _HARD_SEEN_ENTRIES:
        # A burst of unique calls inside one window cannot be pruned; dropping the
        # table only costs a possible duplicate, never memory growth.
        # 窗口内的大量唯一呼号无法清理；清空只会多推一条，不会让内存无限增长。
        seen.clear()


def should_push(conf: dict, event: dict, last_msg: dict = None, seen: dict = None) -> bool:
    """Decide whether to push based on filters and deduplication | 根据过滤器和去重逻辑判断是否推送

    ``seen`` is a ``(call, target) -> timestamp`` map owned by the caller. When it is
    provided, a passing event is recorded into it, so A-B-A alternation is deduped
    correctly (the legacy single-entry ``last_msg`` comparison is kept as fallback).
    ``seen`` 为调用方持有的 `(呼号, 目标) -> 时间戳` 表；传入时通过的事件会被登记，
    这样 A-B-A 交替不会再重复推送；不传时退回旧的单条比较逻辑。
    """
    focus = _parse_list(conf.get('focus_list', []))
    ignore = _parse_list(conf.get('ignore_list', []))
    my_callsign = _base_call(conf.get('my_callsign', '') or '')
    min_duration = float(conf.get('min_duration', 1.0))
    dedup_window = float(conf.get('dedup_window', 3.0))

    call = event['call'].upper()
    target = event['target']
    dur = float(event['dur'])
    call_base = _base_call(call)

    # 1. Whitelist check (Focus list) | 白名单
    if focus and call not in focus and call_base not in focus:
        return False

    # 2. Blacklist check (Ignore list) | 黑名单
    if call in ignore or call_base in ignore:
        return False

    # 3. Self suppression & Duration check | 本台呼号与最小时长
    #    Compare base callsign so that BA4SMQ-1 matches BA4SMQ
    if my_callsign and call_base == my_callsign:
        return False
    if dur < min_duration:
        return False

    # 4. Deduplication | 去重
    now = time.time()
    key = (call, target)

    if seen is not None:
        _prune_seen(seen, now, dedup_window)
        last_ts = seen.get(key)
        if last_ts is not None and now - last_ts < dedup_window:
            return False
        seen[key] = now
        return True

    last_msg = last_msg or {}
    if (call == (last_msg.get("call") or "") and
            target == (last_msg.get("target") or "") and
            (now - float(last_msg.get("ts") or 0)) < dedup_window):
        return False

    return True


def forget_pushed(seen: dict, event: dict) -> None:
    """Allow the same QSO to be pushed again after a delivery failure | 推送失败后允许重发"""
    if not seen:
        return
    try:
        seen.pop((event['call'].upper(), event['target']), None)
    except Exception:
        pass
