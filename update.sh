#!/bin/bash
# MMDVM-Push-Notifier 一键更新部署脚本 (v3.0.11)

echo "--- 开始更新 MMDVM-Push-Notifier ---"

# 1. 切换到读写模式
sudo rpi-rw

# 2. 从 GitHub 拉取最新代码
echo "正在从 GitHub 获取最新版本..."
git fetch --all
git reset --hard origin/main

# 3. 设置配置文件权限 (修复无法保存的问题)
if [ -f "/etc/mmdvm_push.json" ]; then
    echo "正在修复配置文件权限..."
    sudo chmod 666 /etc/mmdvm_push.json
fi

# 4. 部署 PHP 管理页面到 Web 目录
echo "正在部署 PHP 管理页面..."
# 自动定位 Pi-Star 的管理员目录
WEB_ADMIN_DIR="/var/www/dashboard/admin"
if [ -d "$WEB_ADMIN_DIR" ]; then
    sudo cp /home/pi-star/MMDVM-Push-Notifier/push_admin.php "$WEB_ADMIN_DIR/"
    sudo chmod 644 "$WEB_ADMIN_DIR/push_admin.php"
    echo "PHP 页面已部署至 $WEB_ADMIN_DIR/push_admin.php"
else
    echo "错误: 未找到 Web 管理目录，请手动检查路径。"
fi

# 5. 重启 Systemd 服务
echo "正在重启推送服务..."
sudo systemctl daemon-reload
sudo systemctl restart mmdvm_push.service

# 6. 检查服务状态
echo "--- 更新完成 ---"
sudo systemctl status mmdvm_push.service --no-pager
