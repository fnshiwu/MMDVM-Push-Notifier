#!/bin/bash
# MMDVM-Push-Notifier 一键更新脚本 (v3.0.12)
# 开发者: BA4SMQ

echo "--- 开始执行一键更新流程 ---"

# 1. 切换至读写模式，确保可以修改系统文件
sudo rpi-rw

# 2. 进入项目目录
INSTALL_DIR="/home/pi-star/MMDVM-Push-Notifier"
cd $INSTALL_DIR || { echo "错误: 找不到项目目录 $INSTALL_DIR"; exit 1; }

# 3. 从 GitHub 强制同步最新代码
echo "正在拉取远程仓库代码..."
# 放弃所有本地未提交的修改，强制对齐远程仓库
sudo git fetch --all
sudo git reset --hard origin/main

# 4. 修复关键配置文件权限
# 这是解决网页端“无法保存黑白名单”的核心步骤
CONFIG_FILE="/etc/mmdvm_push.json"
if [ -f "$CONFIG_FILE" ]; then
    echo "正在加固配置文件权限 (666)..."
    sudo chown www-data:www-data $CONFIG_FILE
    sudo chmod 666 $CONFIG_FILE
fi

# 5. 自动同步 PHP 管理页面
# 由于 install.sh 已经建立了软链接，此处的 git pull 会自动让网页端生效
# 但为了保险起见，我们再次检查并确保软链接指向正确
WEB_ADMIN_DIR="/var/www/dashboard/admin"
if [ -d "$WEB_ADMIN_DIR" ]; then
    sudo ln -sf $INSTALL_DIR/push_admin.php $WEB_ADMIN_DIR/push_admin.php
    echo "网页管理页面已同步。"
fi

# 6. 重启服务以加载新版本核心逻辑
echo "正在重启 MMDVM 推送服务..."
sudo systemctl daemon-reload
sudo systemctl restart mmdvm_push.service

# 7. 检查更新后的状态
echo "--- 更新完成 ---"
CURRENT_VER=$(python3 $INSTALL_DIR/mmdvm_push.py --version 2>/dev/null || echo "v3.0.12")
echo "当前版本: $CURRENT_VER"
sudo systemctl status mmdvm_push.service --no-pager
