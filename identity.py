import os
import mmap
import logging
from functools import lru_cache
from threading import Semaphore
from typing import Dict, Tuple

# Lock ordering: Always acquire _io_lock before any other locks
# 锁顺序：始终在其他锁之前获取 _io_lock
# This prevents deadlock when multiple modules interact
_io_lock = Semaphore(4)

# Geographic location mapping | 地理位置映射
geo_map_cn = {
    "China": "🇨🇳 中国", "Hong Kong": "🇭🇰 中国香港", "Macao": "🇲🇴 中国澳门",
    "Taiwan": "🇹🇼 中国台湾", "Japan": "🇯🇵 日本", "Korea": "🇰🇷 韩国",
    "South Korea": "🇰🇷 韩国", "North Korea": "🇰🇵 朝鲜", "Thailand": "🇹🇭 泰国",
    "Singapore": "🇸🇬 新加坡", "Malaysia": "🇲🇾 马来西亚", "Indonesia": "🇮🇩 印度尼西亚",
    "Philippines": "🇵🇭 菲律宾", "Vietnam": "🇻🇳 越南", "India": "🇮🇳 印度",
    "Pakistan": "🇵🇰 巴基斯坦", "Sri Lanka": "🇱🇰 斯里兰卡", "Bangladesh": "🇧🇩 孟加拉国",
    "Nepal": "🇳🇵 尼泊尔", "Mongolia": "🇲🇳 蒙古",
    "United Arab Emirates": "🇦🇪 阿联酋", "UAE": "🇦🇪 阿联酋", "Saudi Arabia": "🇸🇦 沙特",
    "Israel": "🇮🇱 以色列", "Turkey": "🇹🇷 土耳其", "Iran": "🇮🇷 伊朗",
    "Iraq": "🇮🇶 伊拉克", "Kuwait": "🇰🇼 科威特", "Oman": "🇴🇲 阿曼",
    "Qatar": "🇶🇦 卡塔尔", "Jordan": "🇯🇴 约旦", "Lebanon": "🇱🇧 黎巴嫩",
    "Kazakhstan": "🇰🇿 哈萨克斯坦", "Uzbekistan": "🇺🇿 乌兹别克斯坦",
    "United Kingdom": "🇬🇧 英国", "UK": "🇬🇧 英国", "Germany": "🇩🇪 德国",
    "France": "🇫🇷 法国", "Italy": "🇮🇹 意大利", "Spain": "🇪🇸 西班牙",
    "Portugal": "🇵🇹 葡萄牙", "Russia": "🇷🇺 俄罗斯", "Russian Federation": "🇷🇺 俄罗斯",
    "Netherlands": "🇳🇱 荷兰", "Belgium": "🇧🇪 比利时", "Switzerland": "🇨🇭 瑞士",
    "Austria": "🇦🇹 奥地利", "Sweden": "🇸🇪 瑞典", "Norway": "🇳🇴 挪威",
    "Denmark": "🇩🇰 丹麦", "Finland": "🇫🇮 芬兰", "Poland": "🇵🇱 波兰",
    "Czech Republic": "🇨🇿 捷克", "Czechia": "🇨🇿 捷克", "Hungary": "🇭🇺 匈牙利",
    "Greece": "🇬🇷 希腊", "Ireland": "🇮🇪 爱尔兰", "Romania": "🇷🇴 罗马尼亚",
    "Bulgaria": "🇧🇬 保加利亚", "Ukraine": "🇺🇦 乌克兰", "Belarus": "🇧🇾 白俄罗斯",
    "Slovakia": "🇸🇰 斯洛伐克", "Croatia": "🇭🇷 克罗地亚", "Serbia": "🇷🇸 塞尔维亚",
    "Slovenia": "🇸🇮 斯洛文尼亚", "Estonia": "🇪🇪 爱沙尼亚", "Latvia": "🇱🇻 拉脱维亚",
    "Lithuania": "🇱🇹 立陶宛", "Iceland": "🇮🇸 冰岛", "Luxembourg": "🇱🇺 卢森堡",
    "Monaco": "🇲🇨 摩纳哥", "Cyprus": "🇨🇾 塞浦路斯", "Malta": "🇲🇹 马耳他",
    "United States": "🇺🇸 美国", "USA": "🇺🇸 美国", "Canada": "🇨🇦 加拿大",
    "Mexico": "🇲🇽 墨西哥", "Cuba": "🇨🇺 古巴", "Jamaica": "🇯🇲 牙买加",
    "Puerto Rico": "🇵🇷 波多黎各", "Dominican Republic": "🇩🇴 多米尼加",
    "Costa Rica": "🇨🇷 哥斯达黎加", "Panama": "🇵🇦 巴拿马", "Guatemala": "🇬🇹 危地马拉",
    "Honduras": "🇭🇳 洪都拉斯", "Brazil": "🇧🇷 巴西", "Argentina": "🇦🇷 阿根廷",
    "Chile": "🇨🇱 智利", "Colombia": "🇨🇴 哥伦比亚", "Peru": "🇵🇪 秘鲁",
    "Venezuela": "🇻🇪 委内瑞拉", "Uruguay": "🇺🇾 乌拉圭", "Paraguay": "🇵🇾 巴拉圭",
    "Ecuador": "🇪🇨 厄瓜多尔", "Bolivia": "🇧🇴 玻利维亚",
    "Australia": "🇦🇺 澳大利亚", "New Zealand": "🇳🇿 新西兰", "Fiji": "🇫🇯 斐济",
    "Papua New Guinea": "🇵🇬 巴布亚新几内亚",
    "South Africa": "🇿🇦 南非", "Egypt": "🇪🇬 埃及", "Nigeria": "🇳🇬 尼日利亚",
    "Kenya": "🇰🇪 肯尼亚", "Morocco": "🇲🇦 摩洛哥",
    "Algeria": "🇩🇿 阿尔及利亚", "Ethiopia": "🇪🇹 埃塞俄比亚", "Ghana": "🇬🇭 加纳",
    "Tanzania": "🇹🇿 坦桑尼亚", "Uganda": "🇺🇬 乌干达", "Mauritius": "🇲🇺 毛里求斯",
    "Seychelles": "🇸🇨 塞舌尔"
}

geo_map_en = {
    "China": "🇨🇳 China", "Hong Kong": "🇭🇰 Hong Kong", "Macao": "🇲🇴 Macao",
    "Taiwan": "🇹🇼 Taiwan", "Japan": "🇯🇵 Japan", "Korea": "🇰🇷 Korea",
    "South Korea": "🇰🇷 South Korea", "North Korea": "🇰🇵 North Korea", "Thailand": "🇹🇭 Thailand",
    "Singapore": "🇸🇬 Singapore", "Malaysia": "🇲🇾 Malaysia", "Indonesia": "🇮🇩 Indonesia",
    "Philippines": "🇵🇭 Philippines", "Vietnam": "🇻🇳 Vietnam", "India": "🇮🇳 India",
    "Pakistan": "🇵🇰 Pakistan", "Sri Lanka": "🇱🇰 Sri Lanka", "Bangladesh": "🇧🇩 Bangladesh",
    "Nepal": "🇳🇵 Nepal", "Mongolia": "🇲🇳 Mongolia",
    "United Arab Emirates": "🇦🇪 United Arab Emirates", "UAE": "🇦🇪 United Arab Emirates", "Saudi Arabia": "🇸🇦 Saudi Arabia",
    "Israel": "🇮🇱 Israel", "Turkey": "🇹🇷 Turkey", "Iran": "🇮🇷 Iran",
    "Iraq": "🇮🇶 Iraq", "Kuwait": "🇰🇼 Kuwait", "Oman": "🇴🇲 Oman",
    "Qatar": "🇶🇦 Qatar", "Jordan": "🇯🇴 Jordan", "Lebanon": "🇱🇧 Lebanon",
    "Kazakhstan": "🇰🇿 Kazakhstan", "Uzbekistan": "🇺🇿 Uzbekistan",
    "United Kingdom": "🇬🇧 United Kingdom", "UK": "🇬🇧 United Kingdom", "Germany": "🇩🇪 Germany",
    "France": "🇫🇷 France", "Italy": "🇮🇹 Italy", "Spain": "🇪🇸 Spain",
    "Portugal": "🇵🇹 Portugal", "Russia": "🇷🇺 Russia", "Russian Federation": "🇷🇺 Russia",
    "Netherlands": "🇳🇱 Netherlands", "Belgium": "🇧🇪 Belgium", "Switzerland": "🇨🇭 Switzerland",
    "Austria": "🇦🇹 Austria", "Sweden": "🇸🇪 Sweden", "Norway": "🇳🇴 Norway",
    "Denmark": "🇩🇰 Denmark", "Finland": "🇫🇮 Finland", "Poland": "🇵🇱 Poland",
    "Czech Republic": "🇨🇿 Czech Republic", "Czechia": "🇨🇿 Czech Republic", "Hungary": "🇭🇺 Hungary",
    "Greece": "🇬🇷 Greece", "Ireland": "🇮🇪 Ireland", "Romania": "🇷🇴 Romania",
    "Bulgaria": "🇧🇬 Bulgaria", "Ukraine": "🇺🇦 Ukraine", "Belarus": "🇧🇾 Belarus",
    "Slovakia": "🇸🇰 Slovakia", "Croatia": "🇭🇷 Croatia", "Serbia": "🇷🇸 Serbia",
    "Slovenia": "🇸🇮 Slovenia", "Estonia": "🇪🇪 Estonia", "Latvia": "🇱🇻 Latvia",
    "Lithuania": "🇱🇹 Lithuania", "Iceland": "🇮🇸 Iceland", "Luxembourg": "🇱🇺 Luxembourg",
    "Monaco": "🇲🇨 Monaco", "Cyprus": "🇨🇾 Cyprus", "Malta": "🇲🇹 Malta",
    "United States": "🇺🇸 United States", "USA": "🇺🇸 United States", "Canada": "🇨🇦 Canada",
    "Mexico": "🇲🇽 Mexico", "Cuba": "🇨🇺 Cuba", "Jamaica": "🇯🇲 Jamaica",
    "Puerto Rico": "🇵🇷 Puerto Rico", "Dominican Republic": "🇩🇴 Dominican Republic",
    "Costa Rica": "🇨🇷 Costa Rica", "Panama": "🇵🇦 Panama", "Guatemala": "🇬🇹 Guatemala",
    "Honduras": "🇭🇳 Honduras", "Brazil": "🇧🇷 Brazil", "Argentina": "🇦🇷 Argentina",
    "Chile": "🇨🇱 Chile", "Colombia": "🇨🇴 Colombia", "Peru": "🇵🇪 Peru",
    "Venezuela": "🇻🇪 Venezuela", "Uruguay": "🇺🇾 Uruguay", "Paraguay": "🇵🇾 Paraguay",
    "Ecuador": "🇪🇨 Ecuador", "Bolivia": "🇧🇴 Bolivia",
    "Australia": "🇦🇺 Australia", "New Zealand": "🇳🇿 New Zealand", "Fiji": "🇫🇯 Fiji"
}

def resolve_loc(city: str, state: str, country: str) -> Tuple[str, str]:
    """Resolve location to bilingual format | 解析地理位置为双语格式"""
    if any('\u4e00' <= c <= '\u9fff' for c in country):
        # Country name is in Chinese, reverse lookup
        for k, v in geo_map_cn.items():
            if country == v:
                country_cn = v
                country_en = geo_map_en.get(k, k)
                break
        else:
            country_cn = country
            country_en = country
    else:
        country_cn = geo_map_cn.get(country, country)
        country_en = geo_map_en.get(country, country)
    loc_en = f"{city}, {state} ({country_en})" if city or state else country_en
    loc_cn = f"{city}, {state} ({country_cn})" if city or state else country_cn
    return loc_en, loc_cn

def _lookup(id_file: str, callsign: str) -> Dict[str, str]:
    """
    Lookup callsign info with file mtime for cache invalidation
    查找呼号信息（带文件修改时间缓存失效）

    Args:
        id_file: Path to ID file
        callsign: Callsign to lookup

    Returns:
        Dict with name, loc_en, loc_cn
    """
    try:
        mtime = os.path.getmtime(id_file)
    except OSError:
        mtime = 0
    return _lookup_cached(id_file, callsign, mtime)

@lru_cache(maxsize=4096)
def _lookup_cached(id_file: str, callsign: str, mtime: float) -> Dict[str, str]:
    """
    Cached lookup with mtime-based invalidation
    带 mtime 失效的缓存查找

    Args:
        id_file: Path to ID file
        callsign: Callsign to lookup
        mtime: File modification time for cache key

    Returns:
        Dict with name, loc_en, loc_cn
    """
    default_result = {"name": "", "loc_en": "Unknown", "loc_cn": "未知"}

    # Log cache statistics periodically
    cache_info = _lookup_cached.cache_info()
    if cache_info.hits + cache_info.misses > 0 and (cache_info.hits + cache_info.misses) % 1000 == 0:
        hit_rate = cache_info.hits / (cache_info.hits + cache_info.misses) * 100
        logging.getLogger(__name__).info(
            f"Cache stats: hits={cache_info.hits}, misses={cache_info.misses}, "
            f"hit_rate={hit_rate:.1f}%, size={cache_info.currsize}/{cache_info.maxsize}"
        )

    if not _io_lock.acquire(timeout=2):
        logging.getLogger(__name__).warning(f"IO lock timeout: {callsign}")
        return default_result

    try:
        file_size = os.path.getsize(id_file)
        if file_size == 0:
            _io_lock.release()
            return default_result
        with open(id_file, "rb") as f:
            with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                query = f",{callsign},".encode("utf-8")
                idx = mm.find(query)
                if idx == -1:
                    _io_lock.release()
                    return default_result
                start = mm.rfind(b"\n", 0, idx) + 1
                end = mm.find(b"\n", idx)
                if end == -1:
                    end = len(mm)
                line_bytes = mm[start:end]
                try:
                    line = line_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    line = line_bytes.decode("gb18030", errors="replace")
                parts = line.split(",")
                first_name = parts[2].strip() if len(parts) > 2 else ""
                last_name = parts[3].strip() if len(parts) > 3 else ""
                city = parts[4].strip().title() if len(parts) > 4 else ""
                state = parts[5].strip().upper() if len(parts) > 5 else ""
                country = parts[6].strip() if len(parts) > 6 else ""
                loc_en, loc_cn = resolve_loc(city, state, country)
                full_name = f"{first_name} {last_name}".strip().upper()
                name_part = f" ({full_name})" if full_name else ""
                _io_lock.release()
                return {"name": name_part, "loc_en": loc_en, "loc_cn": loc_cn}
    except (OSError, ValueError) as e:
        logging.getLogger(__name__).debug(f"Lookup error for {callsign}: {e}")
        _io_lock.release()
        return default_result
    except Exception as e:
        logging.getLogger(__name__).error(f"Unexpected error in lookup for {callsign}: {e}")
        _io_lock.release()
        return default_result

class Identity:
    def __init__(self, id_file: str):
        self.id_file = id_file
    def get_info(self, callsign: str) -> Dict[str, str]:
        return _lookup(self.id_file, callsign)
