#!/bin/bash
# MMDVM-Push-Notifier 核心更新脚本 (v3.0.15)

echo "--- 开始执行一键更新流程 ---"

# 1. 切换磁盘至读写模式 (原生指令，不依赖 rpi-rw)
echo "正在请求磁盘写入权限..."
sudo mount -o remount,rw / 2>/dev/null
# 尝试调用可能的路径，如果失败则静默跳过
sudo /usr/local/bin/rpi-rw 2>/dev/null || sudo /usr/bin/rpi-rw 2>/dev/null

# 2. 进入项目目录并修复 Git 信任问题
INSTALL_DIR="/home/pi-star/MMDVM-Push-Notifier"
cd $INSTALL_DIR || { echo "错误: 无法进入目录 $INSTALL_DIR"; exit 1; }

echo "正在解决 Git 信任限制..."
git config --global --add safe.directory $INSTALL_DIR

# 3. 从 GitHub 同步所有核心文件 (py, php, service, sh)
echo "正在拉取远程仓库最新代码..."
sudo git fetch --all
sudo git reset --hard origin/main

# 4. 同步系统服务配置
if [ -f "mmdvm_push.service" ]; then
    echo "正在同步服务配置文件..."
    sudo cp mmdvm_push.service /etc/systemd/system/
    sudo systemctl daemon-reload
fi

# 5. 权限重置与加固 (确保网页端可保存)
CONFIG_FILE="/etc/mmdvm_push.json"
if [ -f "$CONFIG_FILE" ]; then
    echo "正在修复配置文件权限 (666)..."
    sudo chown www-data:www-data $CONFIG_FILE
    sudo chmod 666 $CONFIG_FILE
fi

# 6. 赋予脚本自身执行权限
sudo chmod +x install.sh update.sh

# 7. 重启推送服务以生效
echo "正在重启 MMDVM 推送服务..."
sudo systemctl restart mmdvm_push.service

echo "--- 更新完成 ---"
# 显示版本号确认更新成功
python3 mmdvm_push.py --version 2>/dev/null || echo "当前版本: v3.0.15"
sudo systemctl status mmdvm_push.service --no-pager
