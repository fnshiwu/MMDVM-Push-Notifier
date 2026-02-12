# MMDVM-Push-Notifier

> **Project Status | 项目状态**
> Designed for long-term, unattended operation on Pi-Star systems.
> Actively maintained and validated in real-world hotspot deployments.
>
> 本项目面向 Pi-Star 的长期稳定运行场景设计，
> 已在真实热点环境中验证并持续维护，
> 优先保证稳定性、性能与兼容性。

---

> A high-performance notification system for **Pi-Star / MMDVM**
> 一个为 **Pi-Star / MMDVM** 设计的高性能通联与系统状态推送工具

---

## 📌 项目简介 | Project Overview

**MMDVM-Push-Notifier** 是一个专为 **Pi-Star 数字语音热点** 设计的实时推送通知工具。

它通过解析 `MMDVMHost` 运行日志，自动识别 **语音 / 数据通联事件**，并将结构化信息推送至多个平台。

**MMDVM-Push-Notifier** is a real-time notification system designed specifically for **Pi-Star based MMDVM hotspots**.
It monitors `MMDVMHost` logs and sends structured notifications for **voice and data transmissions**.

支持 / Supported platforms:

* 📢 Telegram
* 📢 WeChat (PushPlus)
* 📢 Feishu (Lark Webhook)

---

## ✨ 功能特性 | Features

### 🔔 通联推送 | QSO Notifications

* 语音 / 数据通联自动识别
  Automatic detection of voice and data transmissions
* 呼号、群组、时长、误码率、丢包率解析
  Callsign, talkgroup, duration, BER and packet loss parsing
* DMR Slot 1 / Slot 2 自动识别
  Automatic Slot 1 / Slot 2 detection
* 最短通联时长过滤
  Minimum transmission duration filter

### 🌍 呼号与地区解析 | Callsign & Location Lookup

* 本地解析 `nextionUsers.csv`（无需外部 API）
  Local lookup via `nextionUsers.csv` (no external API)
* 姓名 + 地区显示（如可用）
  Name and location display when available
* 国家 Emoji + 中文名称映射
  Country emoji with Chinese localization
* mmap + LRU Cache，高性能低占用
  High performance via mmap + LRU cache

### 🧰 系统状态推送 | System Status Notifications

* 系统启动上线通知
  Boot / online notification
* IP / CPU / 内存 / 温度信息
  IP, CPU, memory and temperature reporting
* 硬件高温告警（可配置）
  Configurable high temperature alerts

### 🧹 智能过滤 | Smart Filtering

* 呼号白名单（focus_list）
  Callsign whitelist
* 呼号黑名单（ignore_list）
  Callsign blacklist
* 免打扰时段（quiet mode）
  Quiet hours / Do-Not-Disturb mode
* 重复推送抑制
  Duplicate notification suppression

### 🌐 Web 管理界面 | Web Admin Panel

* Pi-Star Dashboard 原生集成
  Native Pi-Star dashboard integration
* 无需手动编辑 JSON
  No manual JSON editing required
* 配置热加载（即时生效）
  Hot-reload configuration without restart

### 🔄 在线更新 | Online Update

* 一键更新脚本 `update.sh`
  One-click update script
* 保留所有用户配置
  User configuration preserved
* 自动修复权限并重启服务
  Automatic permission fix and service restart

---

## 🧱 系统要求 | Requirements

* Pi-Star (official or compatible build)
* Python 3 (included in Pi-Star)
* Running MMDVMHost service

---

## 📁 项目结构 | Project Structure

```
MMDVM-Push-Notifier/
├── mmdvm_push.py        # 核心服务入口，日志轮询/推送/健康输出
├── alerts.py            # 告警管理和触发
├── parser.py            # 日志解析（语音/数据、呼号、时长、时隙等）
├── identity.py          # 呼号检索与缓存（呼号、姓名、地区等）
├── hardware.py          # 系统资源与温度报警（IP、内存，CPU等）
├── notifier.py          # 推送服务及重试逻辑（微信、TG、飞书等）
├── config.py            # 配置加载与校验（检验现有配置）
├── filters.py           # 过滤策略（白/黑名单、静音时段、重复抑制等）
├── notify_fmt.py        # 推送文案格式化（中英文/i18n）
├── push_admin.php       # Web 管理面板（含健康状态只读面板）
├── install.sh           # 安装脚本（完整性检查、最小权限）
├── update.sh            # 更新脚本（完整性检查、健康输出）
├── uninstall.sh         # 卸载脚本（多路径清理、sudoers.d 规则清理）
├── diagnose.sh          # 诊断脚本（一键检查服务状态、日志、网络、推送测试）
├── mmdvm_push.service   # systemd 服务（资源限制、自动重启）
└── tests/               # 轻量单元测试（parser/filters/notify）
```

---

## 🚀 安装方法 | Installation

```bash
rpi-rw
cd /home/pi-star
git clone https://github.com/fnshiwu/MMDVM-Push-Notifier.git
cd MMDVM-Push-Notifier
sudo bash install.sh
```

---

## 📖 使用说明 | Usage Guide

### 1️⃣ 配置管理 | Configuration

#### Web 界面配置（推荐）| Web Interface (Recommended)

访问 Web 管理界面：
```
http://pi-star.local/admin/push_admin.php
```

支持配置项：
- 📱 推送平台设置（Telegram / WeChat / Feishu）
- 🔔 通联过滤（最短时长、白名单、黑名单）
- 🌙 免打扰时段（静音模式）
- 🌡️ 温度告警阈值
- 🌐 界面语言（中文 / English）

配置修改后**自动生效**，无需重启服务。
Configuration changes take effect **automatically** without restarting.

#### 手动编辑配置 | Manual Configuration

配置文件位置：`/etc/mmdvm_push.json`

```bash
rpi-rw
sudo nano /etc/mmdvm_push.json
```

配置示例：
```json
{
  "my_callsign": "BA4SMQ",
  "min_duration": 4.0,
  "temp_threshold": 65.0,
  "temp_interval": 30,
  "temp_unit": "C",
  "ui_lang": "cn",
  "push_tg_enabled": true,
  "tg_token": "your_bot_token",
  "tg_chat_id": "your_chat_id",
  "quiet_mode": {
    "enabled": true,
    "start": "23:00",
    "end": "07:00"
  }
}
```

**重要配置说明：**
- `temp_interval`: 温度检查间隔，单位为**秒**（默认30秒）
- `min_duration`: 最短通联时长，单位为**秒**（默认4秒）
- `quiet_mode`: 免打扰时段，支持跨天设置（如 23:00-07:00）

---

### 2️⃣ 服务管理 | Service Management

#### 查看服务状态 | Check Service Status
```bash
sudo systemctl status mmdvm_push
```

#### 启动服务 | Start Service
```bash
sudo systemctl start mmdvm_push
```

#### 停止服务 | Stop Service
```bash
sudo systemctl stop mmdvm_push
```

#### 重启服务 | Restart Service
```bash
sudo systemctl restart mmdvm_push
```

#### 查看实时日志 | View Live Logs
```bash
sudo journalctl -u mmdvm_push -f
```

或查看日志文件：
```bash
tail -f /var/log/pi-star/mmdvm_push.log
# 或
tail -f /tmp/mmdvm_push.log
```

---

### 3️⃣ 测试与诊断 | Testing & Diagnostics

#### 测试推送 | Test Notification
发送测试推送消息，验证推送通道是否正常：
```bash
python3 /home/pi-star/MMDVM-Push-Notifier/mmdvm_push.py --test
```

成功输出：`Success`

#### 健康检查 | Health Check
查看系统运行状态和配置信息：
```bash
python3 /home/pi-star/MMDVM-Push-Notifier/mmdvm_push.py --health
```

输出 JSON 格式的健康信息，包括：
- 版本号
- 配置状态
- IP 地址
- CPU / 内存占用
- 日志目录状态

#### 一键诊断 | Quick Diagnostics
运行完整的诊断脚本，自动检查所有关键项：
```bash
cd /home/pi-star/MMDVM-Push-Notifier
sudo bash diagnose.sh
```

诊断内容包括：
1. ✅ 服务状态检查
2. ✅ 进程运行检查
3. ✅ 日志文件查看
4. ✅ 配置文件验证
5. ✅ MMDVM 日志检查
6. ✅ 网络连通性测试
7. ✅ 推送功能测试
8. ✅ 系统健康检查

**适用场景：**
- 首次安装后验证
- 推送不工作时排查
- 定期健康检查
- 向开发者报告问题

---

### 4️⃣ 推送平台配置 | Push Platform Setup

#### Telegram 配置

1. 创建 Bot：与 [@BotFather](https://t.me/BotFather) 对话，获取 `bot_token`
2. 获取 Chat ID：与 [@userinfobot](https://t.me/userinfobot) 对话，获取你的 `chat_id`
3. 在 Web 界面或配置文件中填入：
   - `tg_token`: Bot Token
   - `tg_chat_id`: 你的 Chat ID
   - 启用 Telegram 推送

#### WeChat (PushPlus) 配置

1. 访问 [PushPlus 官网](http://www.pushplus.plus/)
2. 微信扫码登录，获取 `token`
3. 在配置中填入：
   - `wx_token`: PushPlus Token
   - 启用 WeChat 推送

#### Feishu (飞书) 配置

1. 在飞书群中添加自定义机器人
2. 获取 Webhook URL 和签名密钥（可选）
3. 在配置中填入：
   - `fs_webhook`: Webhook URL
   - `fs_secret`: 签名密钥（可选）
   - 启用 Feishu 推送

---

### 5️⃣ 高级功能 | Advanced Features

#### 呼号过滤 | Callsign Filtering

**白名单模式（focus_list）：**
只推送指定呼号的通联
```json
{
  "focus_list": "BA4SMQ;BG4ABC;BD7XYZ"
}
```

**黑名单模式（ignore_list）：**
忽略指定呼号的通联
```json
{
  "ignore_list": "TEST;PARROT;N0CALL"
}
```

支持分隔符：`;` 或 `；`（中英文分号）

#### 免打扰时段 | Quiet Hours

设置夜间免打扰时段，避免深夜推送：
```json
{
  "quiet_mode": {
    "enabled": true,
    "start": "23:00",
    "end": "07:00"
  }
}
```

支持跨天设置（如 23:00 到次日 07:00）

#### 温度告警 | Temperature Alerts

当系统温度超过阈值时自动推送告警：
```json
{
  "temp_alert_enabled": true,
  "temp_threshold": 65.0,
  "temp_interval": 1800,
  "temp_unit": "C"
}
```

- `temp_threshold`: 告警温度阈值（摄氏度或华氏度）
- `temp_interval`: 告警间隔（秒），避免频繁推送
- `temp_unit`: 温度单位（`C` 或 `F`）

---

### 6️⃣ 故障排查 | Troubleshooting

#### 推送不工作？

1. **运行诊断脚本：**
   ```bash
   sudo bash diagnose.sh
   ```

2. **检查配置：**
   - Token / Webhook 是否正确
   - 推送平台是否启用
   - 网络是否连通

3. **测试推送：**
   ```bash
   python3 mmdvm_push.py --test
   ```

4. **查看日志：**
   ```bash
   tail -50 /var/log/pi-star/mmdvm_push.log
   ```

#### 服务无法启动？

1. **检查权限：**
   ```bash
   ls -l /home/pi-star/MMDVM-Push-Notifier/
   ```

2. **重新安装：**
   ```bash
   sudo bash install.sh
   ```

3. **查看错误日志：**
   ```bash
   sudo journalctl -u mmdvm_push -n 50
   ```

#### 没有收到通联推送？

1. **确认 MMDVM 有新通联：**
   ```bash
   tail -20 /var/log/pi-star/MMDVM-$(date -u +%Y-%m-%d).log
   ```

2. **检查过滤条件：**
   - 通联时长是否低于 `min_duration`
   - 呼号是否在黑名单中
   - 是否在免打扰时段

3. **查看服务日志：**
   ```bash
   sudo journalctl -u mmdvm_push -f
   ```

---

## 🌐 Web 管理界面 | Web Interface

访问 / Access:

```
http://pi-star.local/admin/push_admin.php
```

配置文件 / Configuration file:

```
/etc/mmdvm_push.json
```

配置修改后自动生效，无需重启服务。
Configuration changes take effect automatically without restarting the service.

---

## 🔄 在线更新 | Updating

⚠️ **请勿重复运行 install.sh**
⚠️ **Do NOT reinstall for upgrades**

```bash
rpi-rw
cd /home/pi-star/MMDVM-Push-Notifier
sudo bash update.sh
```

---

## 🧪 测试推送 | Test Notification

```bash
python3 /home/pi-star/MMDVM-Push-Notifier/mmdvm_push.py --test
```

---

## 🛑 卸载 | Uninstall

```bash
rpi-rw
cd /home/pi-star/MMDVM-Push-Notifier
sudo bash uninstall.sh
```

---

## 🧠 设计说明 | Design Notes

* mmap + regex based log parsing
* ThreadPool + semaphore controlled concurrency
* Hot-reload configuration design
* Deep integration with Pi-Star filesystem and permission model

---

## 📡 作者 | Author

* Callsign: **BA4SMQ**
* QTH: Jiangsu Funing, China

---
