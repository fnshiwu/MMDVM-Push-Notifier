import os
import mmap
import logging
from functools import lru_cache
from threading import Semaphore
from typing import Dict
from notify_fmt import resolve_loc

_io_lock = Semaphore(4)

@lru_cache(maxsize=4096)
def _lookup(id_file: str, callsign: str) -> Dict[str, str]:
    default_result = {"name": "", "loc_en": "Unknown", "loc_cn": "未知"}
    try:
        if not os.path.exists(id_file):
            return default_result
        if not _io_lock.acquire(timeout=2):
            logging.getLogger(__name__).warning(f"IO lock timeout: {callsign}")
            return default_result
        try:
            file_size = os.path.getsize(id_file)
            if file_size == 0:
                return default_result
            with open(id_file, "rb") as f:
                with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                    query = f",{callsign},".encode("utf-8")
                    idx = mm.find(query)
                    if idx == -1:
                        return default_result
                    start = mm.rfind(b"\n", 0, idx) + 1
                    end = mm.find(b"\n", idx)
                    if end == -1:
                        end = len(mm)
                    line_bytes = mm[start:end]
                    try:
                        line = line_bytes.decode("utf-8")
                    except UnicodeDecodeError:
                        line = line_bytes.decode("gb18030", errors="ignore")
                    parts = line.split(",")
                    first_name = parts[2].strip() if len(parts) > 2 else ""
                    last_name = parts[3].strip() if len(parts) > 3 else ""
                    city = parts[4].strip().title() if len(parts) > 4 else ""
                    state = parts[5].strip().upper() if len(parts) > 5 else ""
                    country = parts[6].strip() if len(parts) > 6 else ""
                    loc_en, loc_cn = resolve_loc(city, state, country)
                    full_name = f"{first_name} {last_name}".strip().upper()
                    name_part = f" ({full_name})" if full_name else ""
                    return {"name": name_part, "loc_en": loc_en, "loc_cn": loc_cn}
        except (OSError, ValueError) as e:
            logging.getLogger(__name__).debug(f"Lookup error for {callsign}: {e}")
            return default_result
        finally:
            try:
                _io_lock.release()
            except Exception:
                pass
    except Exception:
        return default_result

class Identity:
    def __init__(self, id_file: str):
        self.id_file = id_file
    def get_info(self, callsign: str) -> Dict[str, str]:
        return _lookup(self.id_file, callsign)
