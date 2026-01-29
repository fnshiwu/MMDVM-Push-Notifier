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
