# MMDVM-Push-Notifier

> 一个为 **Pi-Star / MMDVM** 设计的高性能通联与系统状态推送通知工具
> 作者：BA4SMQ

---

## 📌 项目简介

**MMDVM-Push-Notifier** 是一个专为 **Pi-Star 数字语音热点** 设计的实时推送通知系统。

它通过解析 `MMDVMHost` 运行日志，自动识别 **语音 / 数据通联事件**，并将结构化信息推送至：

* 📢 Telegram
* 📢 微信（PushPlus）
* 📢 飞书（Webhook 机器人）

同时支持 **网页端配置管理**、**黑白名单过滤**、**免打扰时段**、**硬件温度告警** 以及 **系统上线通知**。

本项目并非简单脚本，而是一个：

* 长时间运行稳定
* 面向 Pi-Star 环境深度适配
* 支持在线更新与持续维护

的完整通知子系统。

---

## ✨ 功能特性

### 🔔 通联推送

* 自动识别 **语音 / 数据** 通联
* 解析呼号、群组、时长、误码率、丢包率
* 自动区分 **Slot 1 / Slot 2**（DMR）
* 支持最短通联时长过滤

### 🌍 呼号与地区解析

* 本地解析 `nextionUsers.csv`
* 显示姓名（如可用）
* 国家/地区 Emoji + 中文映射
* 高性能 mmap + LRU Cache

### 🧰 系统状态推送

* 系统启动上线通知
* 当前 IP / CPU / 内存 / 温度
* 硬件高温告警（可配置阈值与频率）

### 🧹 智能过滤

* 呼号白名单（focus_list）
* 呼号黑名单（ignore_list）
* 免打扰时段（quiet mode）
* 重复推送抑制

### 🌐 Web 管理界面

* Pi-Star Dashboard 原生集成
* 无需手动编辑 JSON
* 即改即生效（自动热加载配置）

### 🔄 在线更新

* 一键更新脚本 `update.sh`
* 保留所有用户配置
* 自动修复权限并重启服务

---

## 🧱 系统要求

* Pi-Star（官方或兼容版本）
* Python 3（Pi-Star 默认已包含）
* 已正常运行的 MMDVMHost

---

## 📁 项目结构

```
MMDVM-Push-Notifier/
├── mmdvm_push.py        # 核心推送服务
├── push_admin.php       # Web 管理页面
├── install.sh           # 初次安装脚本
├── update.sh            # 一键更新脚本
├── mmdvm_push.service   # systemd 服务文件
```

---

## 🚀 安装方法（首次安装）

```bash
ssh pi-star@pi-star.local
rpi-rw
cd /home/pi-star
git clone https://github.com/fnshiwu/MMDVM-Push-Notifier.git
cd MMDVM-Push-Notifier
sudo bash install.sh
```

安装完成后，服务将自动注册并启动。

---

## 🌐 Web 管理界面

在浏览器中访问：

```
http://pi-star.local/admin/push_admin.php
```

（或使用 Pi-Star 的 IP 地址）

可在页面中完成：

* 推送平台启用/关闭
* Token / Webhook 配置
* 黑白名单编辑（支持多分隔符）
* 最短通联时长
* 温度告警与免打扰设置
* 一键测试推送

所有配置保存在：

```
/etc/mmdvm_push.json
```

> 配置文件支持 **热加载**，无需重启服务。

---

## 🔔 推送平台说明

### Telegram

需要：

* Bot Token
* Chat ID（个人或群组）

### 微信（PushPlus）

* 申请 PushPlus Token
* 关注 PushPlus 官方公众号

### 飞书

* 创建群机器人
* 配置 Webhook
* （可选）签名密钥

---

## 🔄 在线更新（强烈推荐）

当项目发布新版本时，请 **不要重新安装**，而是使用更新脚本。

```bash
ssh pi-star@pi-star.local
rpi-rw
cd /home/pi-star/MMDVM-Push-Notifier
sudo bash update.sh
```

### 更新脚本会自动：

* 强制同步 GitHub 最新代码
* **保留 `/etc/mmdvm_push.json` 配置**
* 修复 Web 页面与配置文件权限
* 重启推送服务
* 显示当前运行版本

---

## 🧪 测试推送

### Web 页面

点击 **SEND TEST** 按钮

### 命令行

```bash
python3 /home/pi-star/MMDVM-Push-Notifier/mmdvm_push.py --test
```

---

## 🛑 卸载方法

```bash
rpi-rw
sudo systemctl stop mmdvm_push.service
sudo systemctl disable mmdvm_push.service
sudo rm -rf /home/pi-star/MMDVM-Push-Notifier
sudo rm -f /etc/mmdvm_push.json
sudo rm -f /var/www/dashboard/admin/push_admin.php
sudo systemctl daemon-reload
```

---

## 🧠 设计说明（给高级用户）

* 使用 mmap + 正则解析日志，低 CPU 占用
* ThreadPool + Semaphore 控制并发推送
* 配置文件修改自动生效（非轮询阻塞）
* 针对 Pi-Star 目录结构与权限模型定制

---

## 📜 License

MIT License

---

## 📡 作者

* 呼号：BA4SMQ
* QTH：江苏阜宁

欢迎 Issue / PR / 交流改进 👋
