import re

_re_master = re.compile(
    r'end of (?P<v_type>(?:voice\s*|data\s*)?)transmission from '
    r'(?P<call>[A-Z0-9/\-]+) to (?P<target>[A-Z0-9/\-\s]+?), '
    r'(?P<dur>\d+\.?\d*) seconds'
    r'(?:, (?P<loss>\d+)% packet loss)?'
    r'(?:, BER: (?P<ber>\d+\.?\d*)%)?',
    re.IGNORECASE
)

def parse_line(line: str):
    if "end of" not in line.lower():
        return None
    m = _re_master.search(line)
    if not m:
        return None
    call = m.group('call').upper()
    target = m.group('target').strip()
    try:
        dur = float(m.group('dur'))
    except Exception:
        return None
    v_type = m.group('v_type') or ''
    is_voice = 'data' not in v_type.lower()
    slot = ""
    if "Slot 1" in line:
        slot = " (Slot 1)"
    elif "Slot 2" in line:
        slot = " (Slot 2)"
    loss = m.group('loss') or '0'
    ber = m.group('ber') or '0.0'
    return {
        "call": call,
        "target": target,
        "dur": dur,
        "loss": loss,
        "ber": ber,
        "is_voice": is_voice,
        "slot": slot
    }
