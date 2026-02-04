# Push message formatter | 推送消息格式化器
#
# Formats bilingual titles and body for voice/data events
# 为语音/数据事件生成中英文标题与内容
from datetime import datetime

def format_message(conf: dict, event: dict, temp_str: str, info: dict):
    # Build type label and body text according to UI language
    # 根据界面语言生成类型标签与正文
    lang = (conf.get('ui_lang', 'cn') or 'cn').lower()
    call = event['call']
    target = event['target']
    dur = event['dur']
    loss = event['loss']
    ber = event['ber']
    slot = event['slot']
    loc_en = info.get('loc_en', info.get('loc', ''))
    loc_cn = info.get('loc_cn', info.get('loc', ''))
    if lang == 'en':
        body = (
            f"👤 <b>Callsign</b>: {call}{info.get('name','')}\n"
            f"👥 <b>Talkgroup</b>: {target}\n"
            f"📍 <b>Location</b>: {loc_en}\n"
            f"📅 <b>Date</b>: {datetime.now().strftime('%Y-%m-%d')}\n"
            f"⏰ <b>Time</b>: {datetime.now().strftime('%H:%M:%S')}\n"
            f"⏳ <b>Duration</b>: {dur}s\n"
            f"📦 <b>Loss</b>: {loss}%\n"
            f"📉 <b>BER</b>: {ber}%\n"
            f"🌡️ <b>Temp</b>: {temp_str}"
        )
        type_label = f"{'🎙️ Voice QSO' if event['is_voice'] else '💾 Data Mode'}{slot}"
    else:
        body = (
            f"👤 <b>呼号</b>: {call}{info.get('name','')}\n"
            f"👥 <b>群组</b>: {target}\n"
            f"📍 <b>地区</b>: {loc_cn}\n"
            f"📅 <b>日期</b>: {datetime.now().strftime('%Y-%m-%d')}\n"
            f"⏰ <b>时间</b>: {datetime.now().strftime('%H:%M:%S')}\n"
            f"⏳ <b>时长</b>: {dur}秒\n"
            f"📦 <b>丢失</b>: {loss}%\n"
            f"📉 <b>误码</b>: {ber}%\n"
            f"🌡️ <b>温度</b>: {temp_str}"
        )
        type_label = f"{'🎙️ 语音通联' if event['is_voice'] else '💾 数据模式'}{slot}"
    return type_label, body
def format_boot_notice(conf: dict, version: str, ip: str, temp_str: str, cpu: str, mem: str, network_ok: bool):
    lang = (conf.get('ui_lang', 'cn') or 'cn').lower()
    if lang == 'en':
        status = "✅ Online" if network_ok else "⚠️ Packet loss/timeout"
        body = (
            f"🚀 <b>Device Online</b> ({version})\n"
            f"🌐 <b>Network</b>: {status}\n"
            f"🛠️ <b>Admin IP</b>: {ip}\n"
            f"🌡️ <b>System Temp</b>: {temp_str}\n"
            f"📊 <b>CPU</b>: {cpu}%\n"
            f"💾 <b>Memory</b>: {mem}\n"
            f"⏰ <b>Time</b>: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        return "⚙️ Boot Notice", body
    status = "✅ 连通" if network_ok else "⚠️ 丢包/超时"
    body = (
        f"🚀 <b>设备已上线</b> ({version})\n"
        f"🌐 <b>网络状态</b>: {status}\n"
        f"🛠️ <b>管理IP</b>: {ip}\n"
        f"🌡️ <b>系统温度</b>: {temp_str}\n"
        f"📊 <b>CPU占用</b>: {cpu}%\n"
        f"💾 <b>内存占用</b>: {mem}\n"
        f"⏰ <b>时间</b>: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    return "⚙️ 系统启动通知", body
def format_temp_alert(conf: dict, display_str: str, threshold: float):
    lang = (conf.get('ui_lang', 'cn') or 'cn').lower()
    if lang == 'en':
        body = (
            f"🚨 <b>High Temperature Alert</b>\n"
            f"🔥 <b>Current Temp</b>: {display_str}\n"
            f"⚠️ <b>Threshold</b>: {threshold:.1f}°{conf.get('temp_unit', 'C')}\n"
            f"⏰ <b>Time</b>: {datetime.now().strftime('%H:%M:%S')}"
        )
        return "🌡️ Hardware Status Warning", body
    body = (
        f"🚨 <b>硬件高温预警</b>\n"
        f"🔥 <b>当前温度</b>: {display_str}\n"
        f"⚠️ <b>预警阈值</b>: {threshold:.1f}°{conf.get('temp_unit', 'C')}\n"
        f"⏰ <b>检测时间</b>: {datetime.now().strftime('%H:%M:%S')}"
    )
    return "🌡️ 硬件状态警告", body
def format_test_push(conf: dict, version: str, ip: str, temp_str: str, cpu: str, mem: str):
    lang = (conf.get('ui_lang', 'cn') or 'cn').lower()
    if lang == 'en':
        body = (
            f"Channel test success ({version})\n"
            f"🌐 <b>IP</b>: {ip}\n"
            f"🌡️ <b>Temp</b>: {temp_str}\n"
            f"📊 <b>CPU (System)</b>: {cpu}%\n"
            f"💾 <b>Memory</b>: {mem}\n"
            f"⏰ <b>Time</b>: {datetime.now().strftime('%H:%M:%S')}"
        )
        return "🔔 Test Notification", body
    body = (
        f"通道测试成功 ({version})\n"
        f"🌐 <b>IP</b>: {ip}\n"
        f"🌡️ <b>温度</b>: {temp_str}\n"
        f"📊 <b>CPU（整机）</b>: {cpu}%\n"
        f"💾 <b>内存</b>: {mem}\n"
        f"⏰ <b>时间</b>: {datetime.now().strftime('%H:%M:%S')}"
    )
    return "🔔 测试推送", body
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
    "Austria": "🇦🇹 奥地利",
    "Sweden": "🇸🇪 瑞典", "Norway": "🇳🇴 挪威",
    "Denmark": "🇩🇰 丹麦",
    "Finland": "🇫🇮 芬兰", "Poland": "🇵🇱 波兰",
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
    "Kenya": "🇰🇪 肯尼亚",
    "Morocco": "🇲🇦 摩洛哥",
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
    "Austria": "🇦🇹 Austria",
    "Sweden": "🇸🇪 Sweden", "Norway": "🇳🇴 Norway",
    "Denmark": "🇩🇰 Denmark",
    "Finland": "🇫🇮 Finland", "Poland": "🇵🇱 Poland",
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
def resolve_loc(city: str, state: str, country: str):
    if any('\u4e00' <= c <= '\u9fff' for c in country):
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
