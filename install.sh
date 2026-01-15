#!/bin/bash
# MMDVM-Push-Notifier S+ 安装脚本 (v3.1.6-S+)
# 功能: 安装核心、Web、服务文件，并保证权限与防护

set -e

if [ "$EUID" -ne 0 ]; then
  echo "请使用 sudo 运行: sudo ./install.sh"
  exit 1
fi

INSTALL_DIR="/home/pi-star/MMDVM-Push-Notifier"
CONFIG_FILE="/etc/mmdvm_push.json"
WEB_DIR="/var/www/dashboard/admin"
SERVICE_FILE="$INSTALL_DIR/mmdvm_push.service"
UPDATE_SCRIPT="$INSTALL_DIR/update.sh"

echo "--- 安装目录准备 ---"
mkdir -p "$INSTALL_DIR"
chown -R pi-star:pi-star "$INSTALL_DIR"
chmod -R 755 "$INSTALL_DIR"

echo "--- 配置文件初始化 ---"
if [ ! -f "$CONFIG_FILE" ]; then
  echo '{"my_callsign":"BA4SMQ","min_duration":5.0,"ui_lang":"cn"}' > "$CONFIG_FILE"
fi
chown www-data:www-data "$CONFIG_FILE"
chmod 666 "$CONFIG_FILE"

echo "--- 部署 Web 管理页面 ---"
if [ -d "$WEB_DIR" ]; then
  ln -sf "$INSTALL_DIR/push_admin.php" "$WEB_DIR/push_admin.php"
  ln -sf "$INSTALL_DIR/push_admin.php" /var/www/dashboard/push_admin.php
  chown www-data:www-data "$INSTALL_DIR/push_admin.php"
fi

echo "--- 授权网页端更新脚本免密 ---"
chmod +x "$UPDATE_SCRIPT"
if ! grep -q "$UPDATE_SCRIPT" /etc/sudoers; then
  echo "www-data ALL=(ALL) NOPASSWD: $UPDATE_SCRIPT" | tee -a /etc/sudoers
fi

echo "--- 部署 systemd 服务 ---"
if [ -f "$SERVICE_FILE" ]; then
  cp "$SERVICE_FILE" /etc/systemd/system/
  chmod 644 /etc/systemd/system/mmdvm_push.service
else
  echo "错误: 找不到服务文件 $SERVICE_FILE"
  exit 1
fi

# 清理内存盘日志防止挂载失败
mount -o remount,size=32M /run 2>/dev/null || true
rm -rf /run/log/journal/* 2>/dev/null || true

systemctl daemon-reload
systemctl enable mmdvm_push.service
systemctl restart mmdvm_push.service

# ===== 版本号读取保护 =====
ACTUAL_VER=$(python3 "$INSTALL_DIR/mmdvm_push.py" --version 2>/dev/null)
if [ -z "$ACTUAL_VER" ]; then
  ACTUAL_VER="v3.1.6-S+ (默认)"
fi
echo "当前部署版本: $ACTUAL_VER"
systemctl status mmdvm_push.service --no-pager | grep -E "Active:|Main PID:"
echo "--- 安装完成 ---"
