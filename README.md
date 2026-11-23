# MMDVM-Push-Notifier

一个专为 **Pi-Star / MMDVM** 设计的高性能通联与系统状态推送工具  
*A high-performance notification system for Pi-Star / MMDVM*

[![GitHub release](https://img.shields.io/github/v/release/fnshiwu/MMDVM-Push-Notifier?style=flat-square&color=blue)](https://github.com/fnshiwu/MMDVM-Push-Notifier/releases)
[![Python Version](https://img.shields.io/badge/python-3.9--3.13-blue.svg?style=flat-square)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg?style=flat-square)](LICENSE)

---

**Project Status | 项目状态**  
Designed for long-term, unattended operation on Pi-Star systems. Validated on **Pi-Star 4.3.7 (Debian 12 Bookworm)** and still compatible with **Pi-Star 4.2.x (Bullseye)**.  
本项目面向 Pi-Star 的长期稳定运行场景设计，已在 Pi-Star 4.3.7（Debian 12 Bookworm）实机验证，并向下兼容 4.2.x。

> **v3.6.2 更新重点（Open Code Review 审计修复版）**
> * 修复 `NaN` / `Inf` 配置值绕过校验：单个非有限数值不再中断后续所有字段的清洗
> * 修复去重表跨线程并发访问：`tail` 线程与推送线程共用同一把锁，繁忙中继下不会因 `dictionary changed size during iteration` 停掉日志监听
> * 修复飞书 webhook 带尾部斜杠时 hook id 明文进入错误日志的问题
> * 修复诊断脚本嵌套 `sudo` 造成的假告警，并修正推送失败计数的 `grep` 兜底
> * 安装脚本注入导航链接时跳过 PHP 注释行，避免「文件里有链接、页面上没按钮」
> * 测试从 78 项增加到 83 项
>
> **v3.6.1 更新重点（审核修复版，建议所有 3.6.0 用户升级）**
> * 修复 `ber` 缺失时推送正文出现「误码: None%」（数据帧/短格式行会触发）
> * 修复 Web 面板以 `www-data` 身份采集健康数据导致的假红灯（改以服务用户身份采集，缺规则时明确标注「仅供参考」）
> * 修复 Telegram 消息未转义 `&` / `<` 导致整条推送被 400 拒绝（飞书 lark_md 单独转换）
> * 推送队列改为有上限 + 单渠道总耗时预算，网络长时间中断不再堆积内存
> * TLS 降级只对证书错误生效、有日志与计数；Telegram（token 在 URL 里）禁止降级
> * 推送失败会写 `PUSH_FAILED` 标记，面板显示「最近推送失败」次数与最后一条；失败后释放去重记录，同一通联的下一行还能补推
> * `update.sh` 回滚改为整体 `git reset --hard <原提交>`，不再出现「半新半旧」工作区
> * 高温告警加迟滞（`temp_hysteresis`，默认 3.0），温度在阈值附近抖动不再反复推送
> * 面板：token/secret 改为掩码显示（留空即不修改）、语言切换改走 POST+CSRF、读写挂载状态按原样恢复、增加安全响应头
> * 呼号表检索校验字段位置，姓名/城市里出现同串不再误命中
> * 测试从 26 项扩展，覆盖无 BER 行、HTML 转义、TLS/失败路径、队列上限、日志截断、告警迟滞、呼号误命中
>
> **v3.6.0 更新重点（Pi-Star 4.3.7 / Bookworm 完整适配）**
> * 日志目录自动探测（`log_dir` 可配置，不再写死 `/var/log/pi-star`）
> * 解析器支持新版 MMDVMHost 日志行（`received RF/network end of voice transmission ... RSSI: -45 dBm`），并支持 DMR / D-Star / YSF / P25 / NXDN / M17 / POCSAG 多模式
> * 修复服务用户读不到 `/var/log/pi-star` 导致「一条推送都收不到」的根因（安装/更新脚本自动加入 `pi-star` 组）
> * `--health` / `--parse` / `--selftest` 输出纯净 JSON，不再被日志污染
> * 推送结果校验（Telegram `ok`、PushPlus `code=200`、飞书 `code=0`），失败不再静默当成功
> * PHP 8.2/8.3 完全兼容；systemd 单元适配 systemd 252+

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
* 呼号、群组、时长、误码率、丢包率、RSSI 解析 *(Callsign, talkgroup, duration, BER, packet loss, RSSI)*
* DMR Slot 1 / Slot 2 自动识别 *(Automatic Slot 1 / Slot 2 detection)*
* 多模式识别：DMR / D-Star / YSF / P25 / NXDN / M17 / POCSAG *(Multi-mode parsing)*
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
* 重复推送抑制 *(Configurable duplicate suppression)*

### 🌐 Web 管理界面 | Web Admin Panel
* Pi-Star Dashboard 原生集成 *(Native Pi-Star dashboard integration)*
* 无需手动编辑 JSON / 配置热加载即时生效 *(No manual JSON editing, hot-reload support)*
* 内置健康面板：版本、系统、日志目录/文件可读性、解析器自检、CPU/内存、日志尾部

### 🔄 在线更新 | Online Update
* 一键更新脚本 `update.sh`（自动备份旧版本、保留用户配置、语法检查失败自动回滚）

---

## 🧱 系统要求 | Requirements

| 项目 | 要求 |
| --- | --- |
| 系统 | Pi-Star 4.2.x (Bullseye) / 4.3.x (Bookworm) |
| Python | 3.9 - 3.13（无需 pip 安装任何第三方包） |
| PHP | 7.4 - 8.4（仅 Web 面板需要，Pi-Star 自带） |
| 服务 | 运行中的 `mmdvmhost.service` |
| 日志 | `/var/log/pi-star/MMDVM-YYYY-MM-DD.log`（可配置，自动探测） |

---

## 📁 项目结构 | Project Structure

```text
MMDVM-Push-Notifier/
├── mmdvm_push.py        # 核心服务入口，日志轮询/推送/健康输出
├── alerts.py            # 告警管理和触发
├── parser.py            # 日志解析（多模式、呼号、时长、时隙、RSSI 等）
├── identity.py          # 呼号检索与缓存（呼号、姓名、地区等）
├── hardware.py          # 系统资源与温度报警（IP、内存，CPU等）
├── notifier.py          # 推送服务及重试逻辑（微信、TG、飞书等）
├── config.py            # 配置加载与校验（检验现有配置）
├── filters.py           # 过滤策略（白/黑名单、静音时段、重复抑制等）
├── notify_fmt.py        # 推送文案格式化（中英文/i18n）
├── push_admin.php       # Web 管理面板（含健康状态只读面板）
├── install.sh           # 安装脚本（版本检测、权限组、语法检查、最小权限）
├── update.sh            # 更新脚本（备份/回滚、权限修复、健康输出）
├── uninstall.sh         # 卸载脚本（多路径清理、sudoers.d 规则清理）
├── diagnose.sh          # 诊断脚本（权限/日志/解析/网络/推送逐层检查）
├── mmdvm_push.service   # systemd 服务（systemd 252+、自动重启、资源限制）
└── tests/               # 单元测试（parser/config/filters/notify_fmt/notifier/alerts/identity/service）
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

安装脚本会：检测 Pi-Star/Debian 版本 → 创建 `mmdvm-push` 服务用户并加入 `pi-star`/`adm` 组 → 校验 Python 语法 → 部署 Web 面板 → 写入 sudoers → 启动服务并输出健康状态。

---

## 🧪 测试与诊断 | Testing & Diagnostics

```bash
# 1) 推送测试（会真实发送一条消息，以服务用户身份运行）
sudo -u mmdvm-push python3 /home/pi-star/MMDVM-Push-Notifier/mmdvm_push.py --test

# 2) 健康检查（纯 JSON，适合脚本/面板调用）
sudo -u mmdvm-push python3 /home/pi-star/MMDVM-Push-Notifier/mmdvm_push.py --health

# 3) 解析器自检
sudo python3 /home/pi-star/MMDVM-Push-Notifier/mmdvm_push.py --selftest

# 4) 用真实日志行验证解析（排查「日志格式变了」最有效）
sudo python3 /home/pi-star/MMDVM-Push-Notifier/mmdvm_push.py --parse "$(grep -a 'end of' /var/log/pi-star/MMDVM-$(date -u +%F).log | tail -1)"

# 5) 一键诊断
cd /home/pi-star/MMDVM-Push-Notifier && sudo bash diagnose.sh

# 6) 单元测试（无第三方依赖）
cd /home/pi-star/MMDVM-Push-Notifier && python3 -m unittest discover -s tests -t . -v
```

`diagnose.sh` 会自动检查：服务状态、进程身份、**日志目录/日志文件对服务用户是否可读**、配置 JSON、解析器、网络、推送通道、sudoers。

---

## 🩺 常见问题 | Troubleshooting

### 服务在跑，但一条推送都收不到
按顺序排查（`diagnose.sh` 已覆盖前三项）：

1. **服务用户读不到日志**（最常见）
   ```bash
   sudo -u mmdvm-push test -r /var/log/pi-star && echo readable || echo NOT-readable
   # 修复：
   sudo usermod -a -G pi-star mmdvm-push && sudo systemctl restart mmdvm_push
   ```
2. **日志路径/文件名不同**：查看面板「当前跟踪日志」一行；若不是你的日志文件，在面板「高级：日志目录」里填写正确目录（或 `log_dir` 留空让其自动探测）。
3. **日志格式变了**：运行 `--parse "<最后一条通联行>"`，无输出说明解析器未匹配，请把该行贴到 Issue。
4. **通道被拒**：面板点「发送测试」，失败会显示平台返回的错误摘要（Token 失效、Chat ID 错误、机器人未入群等）。
5. `sudo journalctl -u mmdvm_push -n 50 --no-pager`

### 面板打不开 / 报 500
* 确认 `php -v` 正常；访问 `http://<ip>/admin/push_admin.php`
* 若提示保存失败：系统处于只读模式，先 `rpi-rw` 或使用面板按钮（会自动申请读写）
* 导航链接未出现属于正常现象（新版 Pi-Star 的 `admin/index.php` 结构变化时会跳过注入），直接访问上面的地址即可

### 面板显示「最近推送失败 N 次」
服务每次投递失败都会在运行日志里写一行 `PUSH_FAILED`，面板统计的是最近 64 KB 日志里的失败条数。
```bash
grep -a PUSH_FAILED /var/log/pi-star/mmdvm_push.log | tail -5
```
常见原因：Token 失效、Chat ID 填的是用户名而不是数字 ID、飞书机器人被移出群。失败后去重记录会被释放，同一通联的后续日志行还会再试一次。

### 日志里出现 TLS / certificate 相关错误
服务只对**证书校验错误**做降级，并且对「凭据在 URL 里」的渠道（Telegram、飞书）**禁止降级**，所以这类错误会直接失败而不是悄悄降级。

```bash
sudo apt install --reinstall ca-certificates    # 修复 CA 证书库后重启服务
sudo systemctl restart mmdvm_push
```
需要说明的是：这是有意的取舍 —— 与其在不校验证书的连接上把 bot token 送出去，不如明确失败并告诉你来修证书。

### 温度在阈值附近反复推送
v3.6.1 起高温告警带迟滞：越过阈值只报一次，回落到「阈值 − `temp_hysteresis`（默认 3.0）」以下才重新触发。可在 `/etc/mmdvm_push.json` 里调 `temp_hysteresis`。

### 更新后仍无推送
```bash
cd /home/pi-star/MMDVM-Push-Notifier
sudo bash update.sh          # 会自动备份、检查语法、失败回滚
sudo bash diagnose.sh
```

---

## 🌐 Web 管理界面 | Web Interface

* **访问地址 / Access:** `http://pi-star.local/admin/push_admin.php`
* **配置文件 / Configuration:** `/etc/mmdvm_push.json`
* *提示：配置修改后自动生效，无需重启服务。*

---

## 🔄 在线更新 | Updating

⚠️ **请勿重复运行 `install.sh` 进行升级！** 使用 `update.sh`（会备份旧版本并保留配置）。

```bash
rpi-rw
cd /home/pi-star/MMDVM-Push-Notifier
sudo bash update.sh
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

* mmap + regex based log parsing（单条正则 + 模式识别，优先性能）
* ThreadPool + semaphore controlled concurrency
* Hot-reload configuration design
* 日志轮转/截断/inode 变化检测，跨天自动切换
* 去重按 `(呼号, 目标)` 记录，A-B-A 交替不会再重复推送；投递失败会释放该记录
* 推送队列有上限（`PUSH_MAX_QUEUE=64`）＋ 单渠道总耗时预算（`PUSH_TIME_BUDGET=25s`），网络长时间中断只丢新通知，不拖垮进程
* 只读根文件系统友好：运行期只读配置，写入失败自动降级到 `/tmp`
* Deep integration with Pi-Star filesystem and permission model

---

## 📡 作者 | Author

* Callsign: **BA4SMQ**
* QTH: Jiangsu Funing, China
