#!/bin/bash
# MMDVM-Push-Notifier S+ 自动更新脚本 (v3.1.6-S+)

set -e
INSTALL_DIR="/home/pi-star/MMDVM-Push-Notifier"
CONFIG_FILE="/etc/mmdvm_push.json"
SCRIPT="$INSTALL_DIR/mmdvm_push.py"
SERVICE="mmdvm_push.service"

echo "--- 开始一键更新 ---"

# 磁盘切换为读写
sudo mount -o remount,rw / 2>/dev/null || true
sudo /usr/local/bin/rpi-rw 2>/dev/null || true

# 进入安装目录
cd "$INSTALL_DIR" || { echo "错误: $INSTALL_DIR 不存在"; exit 1; }

# Git 拉取最新
git config --global --add safe.directory "$INSTALL_DIR"
sudo git fetch --all || { echo "⚠️ Git fetch 失败"; exit 1; }
sudo git reset --hard origin/main || { echo "⚠️ Git reset 失败"; exit 1; }

# 同步服务文件
if [ -f "mmdvm_push.service" ]; then
  sudo cp mmdvm_push.service /etc/systemd/system/
  sudo systemctl daemon-reload
fi

# 修复配置文件权限
if [ -f "$CONFIG_FILE" ]; then
  sudo chown www-data:www-data "$CONFIG_FILE"
  sudo chmod 666 "$CONFIG_FILE"
fi

# 重启服务
if systemctl is-active --quiet $SERVICE; then
  sudo systemctl restart $SERVICE || echo "⚠️ 服务重启失败"
else
  sudo systemctl start $SERVICE || echo "⚠️ 服务启动失败"
fi

# 读取版本号
ACTUAL_VER=$(python3 "$SCRIPT" --version 2>/dev/null)
if [ -z "$ACTUAL_VER" ]; then
  ACTUAL_VER="v3.1.6-S+ (默认)"
fi
echo "更新完成, 当前版本: $ACTUAL_VER"
sudo systemctl status $SERVICE --no-pager | grep -E "Active:|Main PID:"
