#!/bin/bash
# MMDVM-Push-Notifier 强化版安装脚本 (v3.0.15) - 修复空间与路径问题

if [ "$EUID" -ne 0 ]; then 
  echo "请使用 sudo 运行此脚本: sudo ./install.sh"
  exit
fi

# 1. 准备磁盘与内存空间
mount -o remount,rw /
mount -o remount,size=32M /run 2>/dev/null 

echo "1. 正在创建并设置目录权限..."
INSTALL_DIR="/home/pi-star/MMDVM-Push-Notifier"
mkdir -p $INSTALL_DIR
chown -R pi-star:pi-star $INSTALL_DIR
chmod -R 755 $INSTALL_DIR

echo "2. 初始化配置文件并【强制开放权限】..."
CONFIG_FILE="/etc/mmdvm_push.json"
if [ ! -f "$CONFIG_FILE" ]; then
    echo '{"my_callsign":"BA4SMQ","min_duration":5.0,"ui_lang":"cn"}' > $CONFIG_FILE
fi
chown www-data:www-data $CONFIG_FILE
chmod 666 $CONFIG_FILE
echo "配置文件权限已设置为 666"

echo "3. 部署 Web 管理页面 (软链接模式)..."
WEB_DIR="/var/www/dashboard/admin"
if [ -d "$WEB_DIR" ]; then    
    ln -sf $INSTALL_DIR/push_admin.php $WEB_DIR/push_admin.php
    ln -sf $INSTALL_DIR/push_admin.php /var/www/dashboard/push_admin.php
    chown www-data:www-data $INSTALL_DIR/push_admin.php
fi

echo "4. 授权网页端【一键更新】免密权限..."
UPDATE_SCRIPT="$INSTALL_DIR/update.sh"
chmod +x $UPDATE_SCRIPT
if ! grep -q "$UPDATE_SCRIPT" /etc/sudoers; then    
    echo "www-data ALL=(ALL) NOPASSWD: $UPDATE_SCRIPT" | tee -a /etc/sudoers
    echo "Sudoers 免密授权完成"
fi

echo "5. 配置并启动系统服务..."
if [ -f "$INSTALL_DIR/mmdvm_push.service" ]; then
    cp $INSTALL_DIR/mmdvm_push.service /etc/systemd/system/
    chmod 644 /etc/systemd/system/mmdvm_push.service
else
    echo "错误: 在 $INSTALL_DIR 中找不到 mmdvm_push.service 文件！"
    exit 1
fi

# 清理内存盘缓存防止重载失败
rm -rf /run/log/journal/* 2>/dev/null

systemctl daemon-reload
systemctl enable mmdvm_push.service
systemctl restart mmdvm_push.service

echo "--------------------------------------"
echo "安装与权限加固完成！"

# --- 核心改进：读取程序版本号 ---
ACTUAL_VER=$(python3 $INSTALL_DIR/mmdvm_push.py --version 2>/dev/null)
if [ -z "$ACTUAL_VER" ]; then
    echo "当前部署版本: v3.0.15 (无法从核心程序读取)"
else
    echo "当前部署版本: $ACTUAL_VER"
fi
# --------------------------------------

systemctl status mmdvm_push.service --no-pager | grep -E "Active:|Main PID:"
