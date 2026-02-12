# Push message formatter | 推送消息格式化器
#
# Formats bilingual titles and body for voice/data events
# 为语音/数据事件生成中英文标题与内容
from datetime import datetime
from typing import TYPE_CHECKING

# Avoid circular import at runtime
if TYPE_CHECKING:
    from identity import resolve_loc

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
    now = datetime.now()
    date_str = now.strftime('%Y-%m-%d')
    time_str = now.strftime('%H:%M:%S')
    if lang == 'en':
        body = (
            f"👤 <b>Callsign</b>: {call}{info.get('name','')}\n"
            f"👥 <b>Talkgroup</b>: {target}\n"
            f"📍 <b>Location</b>: {loc_en}\n"
            f"📅 <b>Date</b>: {date_str}\n"
            f"⏰ <b>Time</b>: {time_str}\n"
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
            f"📅 <b>日期</b>: {date_str}\n"
            f"⏰ <b>时间</b>: {time_str}\n"
            f"⏳ <b>时长</b>: {dur}秒\n"
            f"📦 <b>丢失</b>: {loss}%\n"
            f"📉 <b>误码</b>: {ber}%\n"
            f"🌡️ <b>温度</b>: {temp_str}"
        )
        type_label = f"{'🎙️ 语音通联' if event['is_voice'] else '💾 数据模式'}{slot}"
    return type_label, body
def format_boot_notice(conf: dict, version: str, ip: str, temp_str: str, cpu: str, mem: str, network_ok: bool):
    lang = (conf.get('ui_lang', 'cn') or 'cn').lower()
    now = datetime.now()
    datetime_str = now.strftime('%Y-%m-%d %H:%M:%S')
    if lang == 'en':
        status = "✅ Online" if network_ok else "⚠️ Packet loss/timeout"
        body = (
            f"🚀 <b>Device Online</b> ({version})\n"
            f"🌐 <b>Network</b>: {status}\n"
            f"🛠️ <b>Admin IP</b>: {ip}\n"
            f"🌡️ <b>System Temp</b>: {temp_str}\n"
            f"📊 <b>CPU</b>: {cpu}%\n"
            f"💾 <b>Memory</b>: {mem}\n"
            f"⏰ <b>Time</b>: {datetime_str}"
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
        f"⏰ <b>时间</b>: {datetime_str}"
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
