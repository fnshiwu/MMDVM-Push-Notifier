#!/bin/bash
# MMDVM-Push-Notifier 增强型安装脚本 (v3.0.9 启动强化版)
# 开发者: BA4SMQ

# 确保以 root 权限运行
if [ "$EUID" -ne 0 ]; then 
  echo "请使用 sudo 运行此脚本: sudo ./install.sh"
  exit
fi

# 切换为读写模式
rpi-rw

echo "1. 正在创建并设置目录权限..."
INSTALL_DIR="/home/pi-star/MMDVM-Push-Notifier"
# 如果目录不存在则创建
mkdir -p $INSTALL_DIR

# 核心修复：必须允许 Web 用户 (www-data) 访问此目录，否则 PHP 会报 404 或权限错误
chown -R pi-star:pi-star $INSTALL_DIR
chmod -R 755 $INSTALL_DIR
# 给 www-data 组读取权限，解决 PHP 访问问题
usermod -a -G pi-star www-data

echo "2. 正在初始化配置文件..."
CONFIG_FILE="/etc/mmdvm_push.json"
if [ ! -f "$CONFIG_FILE" ]; then
    echo '{"my_callsign":"NOCALL","min_duration":1.0,"ui_lang":"cn","ignore_list":[],"focus_list":[]}' | tee $CONFIG_FILE > /dev/null
fi
# 设置权限，允许 PHP (www-data) 读写配置文件
chown www-data:www-data $CONFIG_FILE
chmod 664 $CONFIG_FILE

echo "3. 部署 Web 管理页面 (解决 404)..."
# Pi-Star 标准后台路径
WEB_DIR="/var/www/dashboard/admin"

if [ -d "$WEB_DIR" ]; then
    # 强制创建软链接
    ln -sf $INSTALL_DIR/push_admin.php $WEB_DIR/push_admin.php
    # 额外在根目录建立链接，防止部分版本 Dashboard 路径偏移
    ln -sf $INSTALL_DIR/push_admin.php /var/www/dashboard/push_admin.php
    
    # 确保 PHP 能够执行该脚本（用于测试和重启服务）
    chown www-data:www-data $INSTALL_DIR/push_admin.php
    echo "Web 页面已部署至: $WEB_DIR/push_admin.php"
else
    echo "警告: 找不到 Web 目录 $WEB_DIR，请检查您的 Pi-Star 版本。"
fi

echo "4. 配置系统服务 (系统占用优化版)..."
SERVICE_FILE="/etc/systemd/system/mmdvm_push.service"

# 现场生成 service 文件，整合严格的资源限制
cat <<EOF > $SERVICE_FILE
[Unit]
Description=MMDVM Log Push Notifier (v3.0.9)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=$INSTALL_DIR
ExecStartPre=/bin/sleep 10
ExecStart=/usr/bin/python3 $INSTALL_DIR/mmdvm_push.py
Restart=always
RestartSec=5

# 资源限制策略
NoNewPrivileges=true
LimitNOFILE=1024
CPUQuota=30%
MemoryMax=150M
TasksMax=50

[Install]
WantedBy=multi-user.target
EOF

echo "5. 正在启动服务..."
systemctl daemon-reload
systemctl enable mmdvm_push.service
systemctl restart mmdvm_push.service

echo "-----------------------------------------------"
echo "安装完成！"
echo "管理面板地址: http://$(hostname -I | awk '{print $1}')/admin/push_admin.php"
echo "如果上述地址 404，请尝试: http://$(hostname -I | awk '{print $1}')/push_admin.php"
echo "-----------------------------------------------"
