#!/bin/bash
# MMDVM-Push-Notifier 完整功能安装脚本 (v3.0.12)
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
mkdir -p $INSTALL_DIR

# 确保 pi-star 拥有目录，同时 www-data 组有访问权
chown -R pi-star:pi-star $INSTALL_DIR
chmod -R 755 $INSTALL_DIR
usermod -a -G pi-star www-data

echo "2. 正在初始化配置文件并修复权限..."
CONFIG_FILE="/etc/mmdvm_push.json"
if [ ! -f "$CONFIG_FILE" ]; then
    # 显式初始化，增加 ui_lang 字段防止报错
    echo '{"my_callsign":"BA4SMQ","min_duration":5.0,"ui_lang":"cn","ignore_list":"","focus_list":""}' | sudo tee $CONFIG_FILE > /dev/null
fi
# 【重要修改】：设置 666 权限，确保网页端 php (www-data) 能够实时保存修改
sudo chown www-data:www-data $CONFIG_FILE
sudo chmod 666 $CONFIG_FILE

echo "3. 部署 Web 管理页面 (软链接模式)..."
WEB_DIR="/var/www/dashboard/admin"
if [ -d "$WEB_DIR" ]; then
    # 使用软链接，这样 git pull 更新后网页自动生效，无需重复拷贝
    sudo ln -sf $INSTALL_DIR/push_admin.php $WEB_DIR/push_admin.php
    sudo ln -sf $INSTALL_DIR/push_admin.php /var/www/dashboard/push_admin.php
    sudo chown www-data:www-data $INSTALL_DIR/push_admin.php
    echo "Web 页面已部署至: $WEB_DIR/push_admin.php"
else
    echo "警告: 找不到 Web 目录 $WEB_DIR"
fi

echo "4. 授权网页端一键更新 (Sudoers)..."
# 允许网页端的 PHP 进程免密执行 update.sh，这是“网页更新”按钮生效的核心
UPDATE_SCRIPT="$INSTALL_DIR/update.sh"
chmod +x $UPDATE_SCRIPT
if ! sudo grep -q "$UPDATE_SCRIPT" /etc/sudoers; then
    echo "www-data ALL=(ALL) NOPASSWD: $UPDATE_SCRIPT" | sudo tee -a /etc/sudoers > /dev/null
fi

echo "5. 配置系统服务 (保留资源限制策略)..."
SERVICE_FILE="/etc/systemd/system/mmdvm_push.service"
cat <<EOF > $SERVICE_FILE
[Unit]
Description=MMDVM Log Push Notifier (v3.0.12)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=$INSTALL_DIR
ExecStartPre=/bin/sleep 10
# 使用 -u 模式确保 Python 日志实时输出
ExecStart=/usr/bin/python3 -u $INSTALL_DIR/mmdvm_push.py
Restart=always
RestartSec=5

# 严格的资源限制，确保树莓派稳定
NoNewPrivileges=true
LimitNOFILE=1024
CPUQuota=30%
MemoryMax=150M
TasksMax=50

[Install]
WantedBy=multi-user.target
EOF

echo "6. 正在启动服务..."
sudo systemctl daemon-reload
sudo systemctl enable mmdvm_push.service
sudo systemctl restart mmdvm_push.service

echo "-----------------------------------------------"
echo "安装完成！"
echo "配合度自检：系统服务、资源限制、网页更新权限均已就绪。"
echo "-----------------------------------------------"
