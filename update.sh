#!/bin/bash
# MMDVM-Push-Notifier 一键更新脚本 (v3.0.12) - 修正版

echo "--- 开始执行一键更新流程 ---"

# 1. 切换至读写模式 (解决 sudo 找不到命令的问题)
[ -f /usr/local/bin/rpi-rw ] && sudo /usr/local/bin/rpi-rw || sudo rpi-rw

# 2. 进入项目目录
INSTALL_DIR="/home/pi-star/MMDVM-Push-Notifier"
cd $INSTALL_DIR || { echo "错误: 找不到项目目录 $INSTALL_DIR"; exit 1; }

# 3. 解决 Git 安全目录信任问题
echo "正在检查 Git 目录信任设置..."
git config --global --add safe.directory $INSTALL_DIR

# 4. 从 GitHub 强制同步最新代码
echo "正在拉取远程仓库代码..."
sudo git fetch --all
sudo git reset --hard origin/main

# 5. 自动同步服务文件 (mmdvm_push.service) 到系统目录
if [ -f "mmdvm_push.service" ]; then
    echo "正在同步服务配置文件..."
    sudo cp mmdvm_push.service /etc/systemd/system/
    sudo systemctl daemon-reload
fi

# 6. 修复并加固配置文件权限 (666)
CONFIG_FILE="/etc/mmdvm_push.json"
if [ -f "$CONFIG_FILE" ]; then
    echo "正在加固配置文件权限 (666)..."
    sudo chown www-data:www-data $CONFIG_FILE
    sudo chmod 666 $CONFIG_FILE
fi

# 7. 脚本自身与安装脚本赋权
sudo chmod +x install.sh update.sh

# 8. 重启核心程序
echo "正在重启 MMDVM 推送服务..."
sudo systemctl restart mmdvm_push.service

echo "--- 更新完成 ---"
CURRENT_VER=$(python3 $INSTALL_DIR/mmdvm_push.py --version 2>/dev/null || echo "v3.0.12")
echo "当前版本: $CURRENT_VER"
sudo systemctl status mmdvm_push.service --no-pager
