#!/bin/bash
# MMDVM-Push-Notifier 强化版安装脚本 (v3.1.7) - 修复空间与路径问题

if [ "$EUID" -ne 0 ]; then 
  echo "请使用 sudo 运行此脚本: sudo ./install.sh"
  exit
fi

# 1. 准备磁盘与内存空间
echo "1. 正在获取磁盘写入权限..."
mount -o remount,rw / 2>/dev/null
# 尝试兼容 Pi-Star 自带脚本
if command -v rpi-rw >/dev/null 2>&1; then
    rpi-rw
elif [ -f /usr/local/bin/rpi-rw ]; then
    /usr/local/bin/rpi-rw
elif [ -f /usr/bin/rpi-rw ]; then
    /usr/bin/rpi-rw
fi

mount -o remount,size=32M /run 2>/dev/null 

echo "1. 正在创建并设置目录权限..."
INSTALL_DIR="/home/pi-star/MMDVM-Push-Notifier"
mkdir -p $INSTALL_DIR
id -u mmdvm-push >/dev/null 2>&1 || useradd -r -s /usr/sbin/nologin -U mmdvm-push
chown -R mmdvm-push:mmdvm-push $INSTALL_DIR
chmod -R 755 $INSTALL_DIR

echo "2. 初始化配置文件并设置最小权限..."
CONFIG_FILE="/etc/mmdvm_push.json"
if [ ! -f "$CONFIG_FILE" ]; then
    echo '{"my_callsign":"BA4SMQ","min_duration":5.0,"ui_lang":"cn"}' > $CONFIG_FILE
fi
chown mmdvm-push:www-data $CONFIG_FILE
chmod 660 $CONFIG_FILE
echo "配置文件权限已设置为 660 (owner: mmdvm-push, group: www-data)"

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
SUDO_D="/etc/sudoers.d/mmdvm-push-web"
cat > "$SUDO_D" <<'EOF'
www-data ALL=(ALL) NOPASSWD: /bin/systemctl start mmdvm_push.service
www-data ALL=(ALL) NOPASSWD: /bin/systemctl stop mmdvm_push.service
www-data ALL=(ALL) NOPASSWD: /bin/systemctl restart mmdvm_push.service
www-data ALL=(ALL) NOPASSWD: /bin/systemctl status mmdvm_push.service
EOF
chmod 440 "$SUDO_D"

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

# --- 7. Post-Install Summary / 安装后检查 ---
echo "--------------------------------------------------------"
echo "✅ MMDVM-Push-Notifier Installed Successfully! (v3.1.7)"
echo "--------------------------------------------------------"
echo "🌐 Web Admin: http://pi-star.local/admin/push_admin.php"
echo "   (Or via IP: http://$(hostname -I | awk '{print $1}')/admin/push_admin.php)"
echo ""
echo "⚙️  Config File: $CONFIG_FILE"
echo "📂 Log Path:    /var/log/pi-star/mmdvm_push.log"
echo "--------------------------------------------------------"
echo "💡 Usage Tip:"
echo "   Visit the Web Admin to set your API keys and callsign."
echo "   Then click 'Send Test' to verify."
echo "--------------------------------------------------------"
