# Push message formatter | 推送消息格式化器
#
# Formats bilingual titles and body for voice/data events
# 为语音/数据事件生成中英文标题与内容
#
# IMPORTANT: the body is built with HTML markup (<b>) and every dynamic value is
# HTML-escaped. Telegram (parse_mode=HTML) and PushPlus (template=html) consume it
# verbatim; Feishu's lark_md has different rules, so notifier converts the markup
# with html_to_lark_md() before sending. Never interpolate a raw variable here.
# 重要：正文统一用 HTML 标记（<b>），所有动态值都经过 HTML 转义。Telegram 与
# PushPlus 原样使用；飞书 lark_md 规则不同，由 notifier 转换后再发送。
from datetime import datetime
from html import escape as _escape


def _e(value) -> str:
    """Escape a dynamic value for HTML/Telegram markup | 转义动态值"""
    return _escape(str(value), quote=False)


def _mode_suffix(event: dict) -> str:
    """Append digital mode to the title when available | 有模式信息时附加到标题"""
    mode = (event.get('mode') or '').strip()
    return f" · {_e(mode)}" if mode else ""


def format_message(conf: dict, event: dict, temp_str: str, info: dict):
    """Build type label and body text according to UI language | 根据界面语言生成类型标签与正文"""
    lang = (conf.get('ui_lang', 'cn') or 'cn').lower()
    call = _e(event['call'])
    target = _e(event['target'])
    dur = _e(event['dur'])
    loss = _e(event['loss'])
    ber = _e(event['ber'])
    slot = _e(event['slot'])
    mode = (event.get('mode') or '').strip()
    rssi = (event.get('rssi') or '').strip()
    loc_en = _e(info.get('loc_en', info.get('loc', '')))
    loc_cn = _e(info.get('loc_cn', info.get('loc', '')))
    now = datetime.now()
    date_str = now.strftime('%Y-%m-%d')
    time_str = now.strftime('%H:%M:%S')
    suffix = _mode_suffix(event)

    if lang == 'en':
        body_parts = [
            f"👤 <b>Callsign</b>: {call}{_e(info.get('name', ''))}",
            f"👥 <b>Talkgroup</b>: {target}",
            f"📍 <b>Location</b>: {loc_en}",
            f"📅 <b>Date</b>: {date_str}",
            f"⏰ <b>Time</b>: {time_str}",
            f"⏳ <b>Duration</b>: {dur}s",
            f"📦 <b>Loss</b>: {loss}%",
            f"📉 <b>BER</b>: {ber}%",
        ]
        if mode:
            body_parts.append(f"📶 <b>Mode</b>: {_e(mode)}")
        if rssi:
            body_parts.append(f"📡 <b>RSSI</b>: {_e(rssi)} dBm")
        body_parts.append(f"🌡️ <b>Temp</b>: {_e(temp_str)}")
        body = "\n".join(body_parts)
        type_label = f"{'🎙️ Voice QSO' if event['is_voice'] else '💾 Data Mode'}{suffix}{slot}"
    else:
        body_parts = [
            f"👤 <b>呼号</b>: {call}{_e(info.get('name', ''))}",
            f"👥 <b>群组</b>: {target}",
            f"📍 <b>地区</b>: {loc_cn}",
            f"📅 <b>日期</b>: {date_str}",
            f"⏰ <b>时间</b>: {time_str}",
            f"⏳ <b>时长</b>: {dur}秒",
            f"📦 <b>丢失</b>: {loss}%",
            f"📉 <b>误码</b>: {ber}%",
        ]
        if mode:
            body_parts.append(f"📶 <b>模式</b>: {_e(mode)}")
        if rssi:
            body_parts.append(f"📡 <b>信号</b>: {_e(rssi)} dBm")
        body_parts.append(f"🌡️ <b>温度</b>: {_e(temp_str)}")
        body = "\n".join(body_parts)
        type_label = f"{'🎙️ 语音通联' if event['is_voice'] else '💾 数据模式'}{suffix}{slot}"
    return type_label, body


def format_boot_notice(conf: dict, version: str, ip: str, temp_str: str, cpu: str, mem: str, network_ok: bool):
    lang = (conf.get('ui_lang', 'cn') or 'cn').lower()
    now = datetime.now()
    datetime_str = now.strftime('%Y-%m-%d %H:%M:%S')
    if lang == 'en':
        status = "✅ Online" if network_ok else "⚠️ Packet loss/timeout"
        body = (
            f"🚀 <b>Device Online</b> ({_e(version)})\n"
            f"🌐 <b>Network</b>: {status}\n"
            f"🛠️ <b>Admin IP</b>: {_e(ip)}\n"
            f"🌡️ <b>System Temp</b>: {_e(temp_str)}\n"
            f"📊 <b>CPU</b>: {_e(cpu)}%\n"
            f"💾 <b>Memory</b>: {_e(mem)}\n"
            f"⏰ <b>Time</b>: {datetime_str}"
        )
        return "⚙️ Boot Notice", body
    status = "✅ 连通" if network_ok else "⚠️ 丢包/超时"
    body = (
        f"🚀 <b>设备已上线</b> ({_e(version)})\n"
        f"🌐 <b>网络状态</b>: {status}\n"
        f"🛠️ <b>管理IP</b>: {_e(ip)}\n"
        f"🌡️ <b>系统温度</b>: {_e(temp_str)}\n"
        f"📊 <b>CPU占用</b>: {_e(cpu)}%\n"
        f"💾 <b>内存占用</b>: {_e(mem)}\n"
        f"⏰ <b>时间</b>: {datetime_str}"
    )
    return "⚙️ 系统启动通知", body


def format_temp_alert(conf: dict, display_str: str, threshold: float):
    lang = (conf.get('ui_lang', 'cn') or 'cn').lower()
    unit = _e(conf.get('temp_unit', 'C'))
    if lang == 'en':
        body = (
            f"🚨 <b>High Temperature Alert</b>\n"
            f"🔥 <b>Current Temp</b>: {_e(display_str)}\n"
            f"⚠️ <b>Threshold</b>: {threshold:.1f}°{unit}\n"
            f"⏰ <b>Time</b>: {datetime.now().strftime('%H:%M:%S')}"
        )
        return "🌡️ Hardware Status Warning", body
    body = (
        f"🚨 <b>硬件高温预警</b>\n"
        f"🔥 <b>当前温度</b>: {_e(display_str)}\n"
        f"⚠️ <b>预警阈值</b>: {threshold:.1f}°{unit}\n"
        f"⏰ <b>检测时间</b>: {datetime.now().strftime('%H:%M:%S')}"
    )
    return "🌡️ 硬件状态警告", body


def format_test_push(conf: dict, version: str, ip: str, temp_str: str, cpu: str, mem: str):
    lang = (conf.get('ui_lang', 'cn') or 'cn').lower()
    if lang == 'en':
        body = (
            f"Channel test success ({_e(version)})\n"
            f"🌐 <b>IP</b>: {_e(ip)}\n"
            f"🌡️ <b>Temp</b>: {_e(temp_str)}\n"
            f"📊 <b>CPU (System)</b>: {_e(cpu)}%\n"
            f"💾 <b>Memory</b>: {_e(mem)}\n"
            f"⏰ <b>Time</b>: {datetime.now().strftime('%H:%M:%S')}"
        )
        return "🔔 Test Notification", body
    body = (
        f"通道测试成功 ({_e(version)})\n"
        f"🌐 <b>IP</b>: {_e(ip)}\n"
        f"🌡️ <b>温度</b>: {_e(temp_str)}\n"
        f"📊 <b>CPU（整机）</b>: {_e(cpu)}%\n"
        f"💾 <b>内存</b>: {_e(mem)}\n"
        f"⏰ <b>时间</b>: {datetime.now().strftime('%H:%M:%S')}"
    )
    return "🔔 测试推送", body
