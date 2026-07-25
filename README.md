# MMDVM-Push-Notifier

一个专为 **Pi-Star / MMDVM** 设计的高性能通联与系统状态推送工具  
*A high-performance notification system for Pi-Star / MMDVM*

[![GitHub release](https://img.shields.io/github/v/release/fnshiwu/MMDVM-Push-Notifier?style=flat-square&color=blue)](https://github.com/fnshiwu/MMDVM-Push-Notifier/releases)
[![Python Version](https://img.shields.io/badge/python-3.x-blue.svg?style=flat-square)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg?style=flat-square)](LICENSE)

---

**Project Status | 项目状态**  
Designed for long-term, unattended operation on Pi-Star systems. Actively maintained and validated in real-world hotspot deployments.  
本项目面向 Pi-Star 的长期稳定运行场景设计，已在真实热点环境中验证并持续维护，优先保证稳定性、性能与兼容性。

---

## 📌 项目简介 | Project Overview

**MMDVM-Push-Notifier** 是一个专为 **Pi-Star 数字语音热点** 设计的实时推送通知工具。它通过解析 `MMDVMHost` 运行日志，自动识别 **语音 / 数据通联事件**，并将结构化信息推送至多个平台。

> **MMDVM-Push-Notifier** is a real-time notification system designed specifically for **Pi-Star based MMDVM hotspots**. It monitors `MMDVMHost` logs and sends structured notifications for **voice and data transmissions**.

**支持平台 / Supported Platforms:**
* 📢 Telegram
* 📢 WeChat (PushPlus)
* 📢 Feishu (Lark Webhook)

---

## ✨ 功能特性 | Features

### 🔔 通联推送 | QSO Notifications
* 语音 / 数据通联自动识别 *(Automatic detection of voice and data transmissions)*
* 呼号、群组、时长、误码率、丢包率解析 *(Callsign, talkgroup, duration, BER and packet loss parsing)*
* DMR Slot 1 / Slot 2 自动识别 *(Automatic Slot 1 / Slot 2 detection)*
* 最短通联时长过滤 *(Minimum transmission duration filter)*

### 🌍 呼号与地区解析 | Callsign & Location Lookup
* 本地解析 `nextionUsers.csv`（无需外部 API）*(Local lookup via CSV, no external API)*
* 姓名 + 地区显示（如可用）*(Name and location display when available)*
* 国家 Emoji + 中文名称映射 *(Country emoji with Chinese localization)*
* mmap + LRU Cache，高性能低占用 *(High performance via mmap + LRU cache)*

### 🧰 系统状态推送 | System Status Notifications
* 系统启动上线通知 *(Boot / online notification)*
* IP / CPU / 内存 / 温度信息 *(IP, CPU, memory and temperature reporting)*
* 硬件高温告警（可配置）*(Configurable high temperature alerts)*

### 🧹 智能过滤 | Smart Filtering
* 呼号白名单 (`focus_list`) / 黑名单 (`ignore_list`)
* 免打扰时段 (`quiet mode`)
* 重复推送抑制 *(Duplicate notification suppression)*

### 🌐 Web 管理界面 | Web Admin Panel
* Pi-Star Dashboard 原生集成 *(Native Pi-Star dashboard integration)*
* 无需手动编辑 JSON / 配置热加载即时生效 *(No manual JSON editing, hot-reload support)*

### 🔄 在线更新 | Online Update
* 一键更新脚本 `update.sh`（保留用户配置，自动修复权限并重启服务）

---

## 🧱 系统要求 | Requirements

* Pi-Star (official or compatible build)
* Python 3 (included in Pi-Star)
* Running MMDVMHost service

---

## 📁 项目结构 | Project Structure

```text
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

🚀 安装方法 | Installation
Bash
rpi-rw
cd /home/pi-star
git clone [https://github.com/fnshiwu/MMDVM-Push-Notifier.git](https://github.com/fnshiwu/MMDVM-Push-Notifier.git)
cd MMDVM-Push-Notifier
sudo bash install.sh

🧪 测试与诊断 | Testing & Diagnostics
1. 测试推送 | Test Notification
Bash
sudo python3 /home/pi-star/MMDVM-Push-Notifier/mmdvm_push.py --test
2. 健康检查 | Health Check
Bash
sudo python3 /home/pi-star/MMDVM-Push-Notifier/mmdvm_push.py --health
3. 一键诊断 | Quick Diagnostics
Bash
cd /home/pi-star/MMDVM-Push-Notifier
sudo bash diagnose.sh
自动检查项：服务状态、进程、日志、配置、网络、推送功能。

🌐 Web 管理界面 | Web Interface
访问地址 / Access: http://pi-star.local/admin/push_admin.php

配置文件 / Configuration: /etc/mmdvm_push.json

提示：配置修改后自动生效，无需重启服务。

🔄 在线更新 | Updating
⚠️ 请勿重复运行 install.sh 进行升级！

⚠️ Do NOT reinstall for upgrades, use update.sh instead.

Bash
rpi-rw
cd /home/pi-star/MMDVM-Push-Notifier
sudo bash update.sh
🛑 卸载 | Uninstall
Bash
rpi-rw
cd /home/pi-star/MMDVM-Push-Notifier
sudo bash uninstall.sh
🧠 设计说明 | Design Notes  
mmap + regex based log parsing  

ThreadPool + semaphore controlled concurrency  

Hot-reload configuration design  

Deep integration with Pi-Star filesystem and permission model  

📡 作者 | Author  
Callsign: BA4SMQ

QTH: Jiangsu Funing, China