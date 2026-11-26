# MMDVM-Push-Notifier

<p align="center">
  A high-performance notification system for Pi-Star / MMDVM<br>
  专为 Pi-Star / MMDVM 设计的高性能通联与系统状态推送工具
</p>

<p align="center">
  <a href="https://github.com/fnshiwu/MMDVM-Push-Notifier/releases"><img src="https://img.shields.io/github/v/release/fnshiwu/MMDVM-Push-Notifier?style=flat-square&color=blue" alt="release"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.9--3.13-blue.svg?style=flat-square" alt="python"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green.svg?style=flat-square" alt="license"></a>
</p>

---

<details>
<summary><img src="https://img.shields.io/badge/阅读-中文-de3618?style=for-the-badge" alt="中文"></summary>

# 🇨🇳 中文

面向 Pi-Star 的长期稳定运行场景设计，已在 **Pi-Star 4.3.7（Debian 12 Bookworm）** 实机验证，并向下兼容 **Pi-Star 4.2.x（Bullseye）**。

> **v3.6.4 更新重点（冷启动校时 / 飞书 19021 修复版）**
> * 修复 Pi-Star 冷启动无 RTC 导致时钟未校时、飞书签名被拒（`19021: timestamp is not within one hour`）的问题
> * 启动通知前等待 NTP 校时（默认最多 60 秒，可用 `clock_sync_wait` 配置，0 表示关闭），无论如何都不会阻塞日志监听
> * 飞书签名被拒时，用响应头 `Date` 表示的服务器时间重签并重试一次；日志明确提示「系统时钟未同步，请启用 NTP」，不再误判为密钥错误
> * 安装/更新脚本幂等启用 systemd 时间同步（`timedatectl set-ntp true` + `systemd-timesyncd`），systemd 单元增加 `Wants=time-sync.target`
> * 测试从 86 项增加到 97 项
>
> **v3.6.3 更新重点（安装/卸载修复版）**
> * 修复卸载后重新安装时 `/admin/` 返回 HTTP 500：安装脚本不再把 `echo` 插进另一条 `echo` 的字符串中间，改为在行首插入独立语句；卸载脚本先恢复备份再删除，并遍历所有候选 `index.php`
> * 修复 PHP 语法被注释锚点破坏的问题，`php -l` 校验纳入恢复流程
> * 新增 `recover_dashboard.py`：一条命令修复已被破坏的面板、恢复「推送设置」入口
> * 测试从 83 项增加到 86 项
>
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

## 📌 项目简介

**MMDVM-Push-Notifier** 是一个专为 **Pi-Star 数字语音热点** 设计的实时推送通知工具。它通过解析 `MMDVMHost` 运行日志，自动识别 **语音 / 数据通联事件**，并将结构化信息推送至多个平台。

**支持平台：**
* 📢 Telegram
* 📢 微信（PushPlus）
* 📢 飞书（Lark Webhook）

## ✨ 功能特性

### 🔔 通联推送
* 语音 / 数据通联自动识别
* 呼号、群组、时长、误码率、丢包率、RSSI 解析
* DMR Slot 1 / Slot 2 自动识别
* 多模式识别：DMR / D-Star / YSF / P25 / NXDN / M17 / POCSAG
* 最短通联时长过滤

### 🌍 呼号与地区解析
* 本地解析 `nextionUsers.csv`（无需外部 API）
* 姓名 + 地区显示（如可用）
* 国家 Emoji + 中文名称映射
* mmap + LRU Cache，高性能低占用

### 🧰 系统状态推送
* 系统启动上线通知
* IP / CPU / 内存 / 温度信息
* 硬件高温告警（可配置）

### 🧹 智能过滤
* 呼号白名单 (`focus_list`) / 黑名单 (`ignore_list`)
* 免打扰时段 (`quiet mode`)
* 重复推送抑制

### 🌐 Web 管理界面
* Pi-Star Dashboard 原生集成
* 无需手动编辑 JSON / 配置热加载即时生效
* 内置健康面板：版本、系统、日志目录/文件可读性、解析器自检、CPU/内存、日志尾部

### 🔄 在线更新
* 一键更新脚本 `update.sh`（自动备份旧版本、保留用户配置、语法检查失败自动回滚）

## 🧱 系统要求

| 项目 | 要求 |
| --- | --- |
| 系统 | Pi-Star 4.2.x (Bullseye) / 4.3.x (Bookworm) |
| Python | 3.9 - 3.13（无需 pip 安装任何第三方包） |
| PHP | 7.4 - 8.4（仅 Web 面板需要，Pi-Star 自带） |
| 服务 | 运行中的 `mmdvmhost.service` |
| 日志 | `/var/log/pi-star/MMDVM-YYYY-MM-DD.log`（可配置，自动探测） |

## 📁 项目结构

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

## 🚀 安装方法

```bash
rpi-rw
cd /home/pi-star
git clone https://github.com/fnshiwu/MMDVM-Push-Notifier.git
cd MMDVM-Push-Notifier
sudo bash install.sh
```

安装脚本会：检测 Pi-Star/Debian 版本 → 创建 `mmdvm-push` 服务用户并加入 `pi-star`/`adm` 组 → 校验 Python 语法 → 部署 Web 面板 → 写入 sudoers → 启动服务并输出健康状态。

## 🧪 测试与诊断

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

## 🩺 常见问题

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

## 🌐 Web 管理界面

* **访问地址 / Access:** `http://pi-star.local/admin/push_admin.php`
* **配置文件 / Configuration:** `/etc/mmdvm_push.json`
* *提示：配置修改后自动生效，无需重启服务。*

## 🔄 在线更新

⚠️ **请勿重复运行 `install.sh` 进行升级！** 使用 `update.sh`（会备份旧版本并保留配置）。

```bash
rpi-rw
cd /home/pi-star/MMDVM-Push-Notifier
sudo bash update.sh
```

## 🛑 卸载

```bash
rpi-rw
cd /home/pi-star/MMDVM-Push-Notifier
sudo bash uninstall.sh
```

## 🧠 设计说明

* mmap + regex based log parsing（单条正则 + 模式识别，优先性能）
* ThreadPool + semaphore controlled concurrency
* Hot-reload configuration design
* 日志轮转/截断/inode 变化检测，跨天自动切换
* 去重按 `(呼号, 目标)` 记录，A-B-A 交替不会再重复推送；投递失败会释放该记录
* 推送队列有上限（`PUSH_MAX_QUEUE=64`）＋ 单渠道总耗时预算（`PUSH_TIME_BUDGET=25s`），网络长时间中断只丢新通知，不拖垮进程
* 只读根文件系统友好：运行期只读配置，写入失败自动降级到 `/tmp`
* Deep integration with Pi-Star filesystem and permission model

## 📡 作者 | Author

* Callsign: **BA4SMQ**
* QTH: Jiangsu Funing, China

</details>

<details>
<summary><img src="https://img.shields.io/badge/Read%20in-English-1f6feb?style=for-the-badge" alt="English"></summary>

# 🇬🇧 English

Designed for long-term, unattended operation on Pi-Star systems. Validated on **Pi-Star 4.3.7 (Debian 12 Bookworm)** and still compatible with **Pi-Star 4.2.x (Bullseye)**.

> **v3.6.4 — cold-boot clock sync / Feishu 19021 fix**
> * Fixes Feishu signature rejection (`19021: timestamp is not within one hour`) caused by an unsynced clock on cold boot without an RTC.
> * Waits for NTP time sync before the boot notice (up to 60 s by default, configurable via `clock_sync_wait`; `0` disables it). Log tailing is never blocked.
> * On 19021, re-signs and retries once using the server time from the `Date` response header; logs now clearly say "system clock not synchronized, enable NTP" instead of suggesting a bad secret.
> * Install/update scripts idempotently enable systemd time sync (`timedatectl set-ntp true` + `systemd-timesyncd`); unit adds `Wants=time-sync.target`.
> * Tests increased from 86 to 97.
>
> **v3.6.3 — install/uninstall fix**
> * Fixes HTTP 500 on `/admin/` after reinstall: the installer no longer splices an `echo` into another `echo` string, it inserts a standalone statement at the line start. The uninstaller restores backups before deleting them and scans all candidate `index.php` files.
> * Fixes PHP syntax broken by comment anchors; `php -l` validation added to the recovery flow.
> * Adds `recover_dashboard.py` — one command repairs a broken panel and restores the "Push Settings" entry.
> * Tests increased from 83 to 86.
>
> **v3.6.2 — Open Code Review fixes**
> * `NaN` / `Inf` config values no longer abort validation of subsequent fields.
> * Fixed concurrent access to the dedup table shared by the tail and push threads.
> * Fixed Feishu webhook hook id leaking into error logs when the URL has a trailing slash.
> * Fixed false warnings from nested `sudo` in the diagnostic script and the `grep` fallback for failure counts.
> * Installer skips PHP comment lines when injecting the nav link ("link in file, no button on page").
> * Tests increased from 78 to 83.
>
> **v3.6.1 — audit fixes (recommended for all 3.6.0 users)**
> * Fixed "BER: None%" in push bodies when `ber` is missing (data frames / short lines).
> * Fixed false red health status caused by collecting as `www-data`.
> * Fixed Telegram messages rejected with 400 due to unescaped `&` / `<`.
> * Bounded push queue plus per-channel time budget; long outages no longer grow memory.
> * TLS downgrade only on certificate errors, with logging/counters; forbidden for channels with credentials in the URL (Telegram).
> * Failed pushes write a `PUSH_FAILED` marker; the panel shows recent failure count and last message; dedup entry is released so the next line can retry.
> * `update.sh` rollback now uses a full `git reset --hard <original commit>`.
> * Temperature alerts add hysteresis (`temp_hysteresis`, default 3.0).
> * Panel: masked token/secret, language switch via POST + CSRF, mount state restored, security headers.
> * Callsign lookup validates field positions so names/cities do not cause false hits.
> * Tests expanded from 26 to cover missing BER, HTML escaping, TLS/failure paths, queue bound, log truncation, hysteresis, callsign false hits.
>
> **v3.6.0 — full Pi-Star 4.3.7 / Bookworm adaptation**
> * Log directory auto-detection (`log_dir` configurable, no longer hardcoded).
> * Parser supports new MMDVMHost log lines and DMR / D-Star / YSF / P25 / NXDN / M17 / POCSAG.
> * Fixed the root cause of "no pushes at all": service user could not read `/var/log/pi-star` (installer adds it to `pi-star` group).
> * `--health` / `--parse` / `--selftest` emit clean JSON.
> * Push result validation (Telegram `ok`, PushPlus `code=200`, Feishu `code=0`).
> * Full PHP 8.2/8.3 compatibility; systemd unit adapted for systemd 252+.

## 📌 Project Overview

**MMDVM-Push-Notifier** is a real-time notification system designed specifically for **Pi-Star based MMDVM hotspots**. It monitors `MMDVMHost` logs and sends structured notifications for **voice and data transmissions**.

**Supported Platforms:**
* 📢 Telegram
* 📢 WeChat (PushPlus)
* 📢 Feishu (Lark Webhook)

## ✨ Features

### 🔔 QSO Notifications
* Automatic detection of voice and data transmissions
* Callsign, talkgroup, duration, BER, packet loss, RSSI parsing
* Automatic DMR Slot 1 / Slot 2 detection
* Multi-mode parsing: DMR / D-Star / YSF / P25 / NXDN / M17 / POCSAG
* Minimum transmission duration filter

### 🌍 Callsign & Location Lookup
* Local `nextionUsers.csv` lookup — no external API
* Name and location display when available
* Country emoji with Chinese localization
* High performance via mmap + LRU cache

### 🧰 System Status Notifications
* Boot / online notification
* IP, CPU, memory and temperature reporting
* Configurable high temperature alerts

### 🧹 Smart Filtering
* Callsign whitelist (`focus_list`) / blacklist (`ignore_list`)
* Quiet mode
* Configurable duplicate suppression

### 🌐 Web Admin Panel
* Native Pi-Star dashboard integration
* No manual JSON editing, hot-reload support
* Built-in health panel: version, system, log directory/file readability, parser self-test, CPU/memory, log tail

### 🔄 Online Update
* One-command `update.sh` (automatic backup, preserves user config, auto-rollback on syntax check failure)

## 🧱 Requirements

| Item | Requirement |
| --- | --- |
| OS | Pi-Star 4.2.x (Bullseye) / 4.3.x (Bookworm) |
| Python | 3.9 - 3.13 (no third-party pip packages) |
| PHP | 7.4 - 8.4 (Web panel only, bundled with Pi-Star) |
| Service | Running `mmdvmhost.service` |
| Log | `/var/log/pi-star/MMDVM-YYYY-MM-DD.log` (configurable, auto-detected) |

## 📁 Project Structure

```text
MMDVM-Push-Notifier/
├── mmdvm_push.py        # core service: log tailing / push / health output
├── alerts.py            # alert management and triggering
├── parser.py            # log parsing (multi-mode, callsign, duration, slot, RSSI...)
├── identity.py          # callsign lookup and cache (callsign, name, location...)
├── hardware.py          # system resources and temperature alerts (IP, memory, CPU...)
├── notifier.py          # push service and retry logic (Telegram, PushPlus, Feishu...)
├── config.py            # configuration loading and validation
├── filters.py           # filtering policies (whitelist/blacklist, quiet hours, dedup...)
├── notify_fmt.py        # push message formatting (i18n)
├── push_admin.php       # Web admin panel (with read-only health view)
├── install.sh           # installer (version detection, groups, syntax check, least privilege)
├── update.sh            # updater (backup/rollback, permission fix, health output)
├── uninstall.sh         # uninstaller (multi-path cleanup, sudoers.d cleanup)
├── diagnose.sh          # diagnostic (permissions / logs / parsing / network / push)
├── mmdvm_push.service   # systemd unit (systemd 252+, auto-restart, resource limits)
└── tests/               # unit tests (parser/config/filters/notify_fmt/notifier/alerts/identity/service)
```

## 🚀 Installation

```bash
rpi-rw
cd /home/pi-star
git clone https://github.com/fnshiwu/MMDVM-Push-Notifier.git
cd MMDVM-Push-Notifier
sudo bash install.sh
```

The installer detects the Pi-Star/Debian version → creates the `mmdvm-push` service user and adds it to the `pi-star`/`adm` groups → validates Python syntax → deploys the Web panel → writes sudoers → starts the service and prints health status.

## 🧪 Testing & Diagnostics

```bash
# 1) Push test (sends a real message as the service user)
sudo -u mmdvm-push python3 /home/pi-star/MMDVM-Push-Notifier/mmdvm_push.py --test

# 2) Health check (pure JSON, suitable for scripts/panels)
sudo -u mmdvm-push python3 /home/pi-star/MMDVM-Push-Notifier/mmdvm_push.py --health

# 3) Parser self-test
sudo python3 /home/pi-star/MMDVM-Push-Notifier/mmdvm_push.py --selftest

# 4) Verify parsing with a real log line (best way to debug "log format changed")
sudo python3 /home/pi-star/MMDVM-Push-Notifier/mmdvm_push.py --parse "$(grep -a 'end of' /var/log/pi-star/MMDVM-$(date -u +%F).log | tail -1)"

# 5) One-click diagnostics
cd /home/pi-star/MMDVM-Push-Notifier && sudo bash diagnose.sh

# 6) Unit tests (no third-party dependencies)
cd /home/pi-star/MMDVM-Push-Notifier && python3 -m unittest discover -s tests -t . -v
```

`diagnose.sh` checks: service status, process identity, **log directory/file readability for the service user**, configuration JSON, parser, network, push channels, sudoers.

## 🩺 Troubleshooting

### Service is running but no pushes arrive
Check in order (the first three are covered by `diagnose.sh`):

1. **Service user cannot read logs** (most common)
   ```bash
   sudo -u mmdvm-push test -r /var/log/pi-star && echo readable || echo NOT-readable
   # Fix:
   sudo usermod -a -G pi-star mmdvm-push && sudo systemctl restart mmdvm_push
   ```
2. **Different log path/filename**: check the "currently tailing" line in the panel; if it is not your log, set the correct directory in "Advanced: log directory" (or leave `log_dir` empty for auto-detection).
3. **Log format changed**: run `--parse "<last QSO line>"`; no output means the parser did not match — please post that line in an Issue.
4. **Channel rejected**: click "Send test" in the panel; failures show the platform's error summary (bad token, wrong chat id, bot removed from group, etc.).
5. `sudo journalctl -u mmdvm_push -n 50 --no-pager`

### Panel won't open / HTTP 500
* Confirm `php -v` works; visit `http://<ip>/admin/push_admin.php`
* If saving fails: the filesystem is read-only — run `rpi-rw` first or use the panel button (it requests read/write automatically)
* A missing nav link is expected on some Pi-Star versions where `admin/index.php` layout changed (injection is skipped) — open the address above directly

### Panel shows "Recent push failures: N"
Every failed delivery writes a `PUSH_FAILED` line to the runtime log; the panel counts entries in the last 64 KB.
```bash
grep -a PUSH_FAILED /var/log/pi-star/mmdvm_push.log | tail -5
```
Common causes: expired token, chat id is a username instead of the numeric id, Feishu bot removed from the group. After a failure the dedup entry is released, so subsequent lines for the same QSO are retried.

### TLS / certificate errors in the log
The service only downgrades on **certificate verification errors**, and **never** for channels with credentials in the URL (Telegram, Feishu), so these errors fail explicitly rather than silently downgrading.
```bash
sudo apt install --reinstall ca-certificates    # repair CA store, then restart
sudo systemctl restart mmdvm_push
```
This is a deliberate trade-off: better to fail loudly than send a bot token over an unverified connection.

### Temperature alerts fire repeatedly near the threshold
Since v3.6.1, high-temperature alerts have hysteresis: it fires once when crossing the threshold and re-arms only after dropping below `threshold − temp_hysteresis` (default 3.0). Tune `temp_hysteresis` in `/etc/mmdvm_push.json`.

### Still no pushes after an update
```bash
cd /home/pi-star/MMDVM-Push-Notifier
sudo bash update.sh          # backs up, checks syntax, rolls back on failure
sudo bash diagnose.sh
```

## 🌐 Web Interface

* **Access:** `http://pi-star.local/admin/push_admin.php`
* **Configuration:** `/etc/mmdvm_push.json`
* *Tip: configuration changes take effect automatically; no service restart needed.*

## 🔄 Updating

⚠️ **Do not run `install.sh` again to upgrade!** Use `update.sh` (it backs up the old version and preserves configuration).

```bash
rpi-rw
cd /home/pi-star/MMDVM-Push-Notifier
sudo bash update.sh
```

## 🛑 Uninstall

```bash
rpi-rw
cd /home/pi-star/MMDVM-Push-Notifier
sudo bash uninstall.sh
```

## 🧠 Design Notes

* mmap + regex based log parsing (single regex + mode detection, performance first)
* ThreadPool + semaphore controlled concurrency
* Hot-reload configuration design
* Log rotation / truncation / inode change detection, automatic rollover across days
* Deduplication keyed by `(callsign, target)` so A-B-A alternation does not re-notify; failed delivery releases the entry
* Bounded push queue (`PUSH_MAX_QUEUE=64`) + per-channel time budget (`PUSH_TIME_BUDGET=25s`): long outages drop new notifications instead of crashing the process
* Read-only root filesystem friendly: runtime reads config only, writes fall back to `/tmp`
* Deep integration with the Pi-Star filesystem and permission model

## 📡 Author

* Callsign: **BA4SMQ**
* QTH: Jiangsu Funing, China

---

</details>
