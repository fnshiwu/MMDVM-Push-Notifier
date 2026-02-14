#!/bin/bash
# MMDVM-Push-Notifier enhanced installer (v3.1.7) | 强化版安装脚本
# Fixes space and path issues | 修复空间与路径问题

if [ "$EUID" -ne 0 ]; then 
  echo "请使用 sudo 运行此脚本: sudo ./install.sh"
  exit
fi

# 1) Prepare disk and tmpfs space | 准备磁盘与内存盘空间
echo "1. 正在获取磁盘写入权限..."
mount -o remount,rw / 2>/dev/null
# Try Pi-Star helper scripts | 兼容 Pi-Star 自带脚本
if command -v rpi-rw >/dev/null 2>&1; then
    rpi-rw
elif [ -f /usr/local/bin/rpi-rw ]; then
    /usr/local/bin/rpi-rw
elif [ -f /usr/bin/rpi-rw ]; then
    /usr/bin/rpi-rw
fi

mount -o remount,size=32M /run 2>/dev/null 

echo "1. Creating and setting directory permissions... | 正在创建并设置目录权限..."
INSTALL_DIR="/home/pi-star/MMDVM-Push-Notifier"
mkdir -p $INSTALL_DIR
id -u mmdvm-push >/dev/null 2>&1 || useradd -r -s /usr/sbin/nologin -U mmdvm-push
# Ensure mmdvm-push is in www-data group to read config if owned by www-data | 确保用户在 www-data 组以读取配置
usermod -a -G www-data mmdvm-push
chown -R mmdvm-push:mmdvm-push $INSTALL_DIR
chmod -R 755 $INSTALL_DIR
cd $INSTALL_DIR || { echo "错误: 无法进入目录 $INSTALL_DIR"; exit 1; }
REQ_FILES="mmdvm_push.py push_admin.php parser.py filters.py notify_fmt.py identity.py hardware.py notifier.py config.py alerts.py mmdvm_push.service"
MISSING=""
for f in $REQ_FILES; do
    [ -f "$f" ] || MISSING="$MISSING $f"
done
if [ -n "$MISSING" ]; then
    echo "错误: 缺少必要文件:$MISSING"
    exit 1
fi

echo "2. Initialize config and set least permissions... | 初始化配置并设置最小权限..."
CONFIG_FILE="/etc/mmdvm_push.json"
if [ ! -f "$CONFIG_FILE" ]; then
    echo '{"my_callsign":"BA4SMQ","min_duration":5.0,"ui_lang":"cn"}' > $CONFIG_FILE
fi
chown mmdvm-push:www-data $CONFIG_FILE
chmod 660 $CONFIG_FILE
echo "Config file permission set to 660 (owner: mmdvm-push, group: www-data) | 配置文件权限已设置为 660（owner: mmdvm-push, group: www-data）"

echo "3. Deploy Web admin (symlink) | 部署 Web 管理页面（软链接）..."
if [ -d "/var/www/dashboard/admin" ]; then
    ln -sf $INSTALL_DIR/push_admin.php "/var/www/dashboard/admin/push_admin.php"
fi
chown www-data:www-data $INSTALL_DIR/push_admin.php
ADMIN_INDEX="/var/www/dashboard/admin/index.php"
if [ -f "$ADMIN_INDEX" ]; then
    cp "$ADMIN_INDEX" "$ADMIN_INDEX.bak_pushnav" 2>/dev/null
    if ! grep -q 'href="/admin/push_admin.php"' "$ADMIN_INDEX"; then
        sed -i '/update.php/a \ echo " <a href=\\"/admin/push_admin.php\\" style=\\"color: #ffffff;\\">推送设置</a> |"."\\n";' "$ADMIN_INDEX"
    fi
    chown www-data:www-data "$ADMIN_INDEX"
    chmod 664 "$ADMIN_INDEX"
fi

echo "4. Grant web 'update' sudoers permissions | 授权网页端【一键更新】免密权限..."
UPDATE_SCRIPT="$INSTALL_DIR/update.sh"
chmod +x $UPDATE_SCRIPT
SUDO_D="/etc/sudoers.d/mmdvm-push-web"
cat > "$SUDO_D" <<'EOF'
www-data ALL=(ALL) NOPASSWD: /bin/systemctl start mmdvm_push.service
www-data ALL=(ALL) NOPASSWD: /bin/systemctl stop mmdvm_push.service
www-data ALL=(ALL) NOPASSWD: /bin/systemctl restart mmdvm_push.service
www-data ALL=(ALL) NOPASSWD: /bin/systemctl status mmdvm_push.service
www-data ALL=(ALL) NOPASSWD: /usr/local/bin/rpi-rw
www-data ALL=(ALL) NOPASSWD: /usr/local/bin/rpi-ro
www-data ALL=(ALL) NOPASSWD: /usr/bin/rpi-rw
www-data ALL=(ALL) NOPASSWD: /usr/bin/rpi-ro
www-data ALL=(ALL) NOPASSWD: /bin/mount -o remount,rw /
www-data ALL=(ALL) NOPASSWD: /bin/mount -o remount,ro /
www-data ALL=(ALL) NOPASSWD: /usr/bin/python3 /home/pi-star/MMDVM-Push-Notifier/mmdvm_push.py *
www-data ALL=(ALL) NOPASSWD: /home/pi-star/MMDVM-Push-Notifier/update.sh
EOF
chmod 440 "$SUDO_D"
visudo -cf "$SUDO_D" >/dev/null 2>&1 || rm -f "$SUDO_D"

echo "5. Install and start systemd service | 配置并启动 systemd 服务..."
if [ -f "$INSTALL_DIR/mmdvm_push.service" ]; then
    cp $INSTALL_DIR/mmdvm_push.service /etc/systemd/system/
    chmod 644 /etc/systemd/system/mmdvm_push.service
else
    echo "错误: 在 $INSTALL_DIR 中找不到 mmdvm_push.service 文件！"
    exit 1
fi

# Clear tmpfs journal to avoid reload failure | 清理内存盘日志缓存避免重载失败
rm -rf /run/log/journal/* 2>/dev/null

systemctl daemon-reload
systemctl enable mmdvm_push.service
systemctl restart mmdvm_push.service

# --- 7. Post-Install Summary / 安装后检查 ---
ACTUAL_VER=$(python3 $INSTALL_DIR/mmdvm_push.py --version 2>/dev/null)
if [ -z "$ACTUAL_VER" ]; then ACTUAL_VER="unknown"; fi
echo "--------------------------------------------------------"
echo "✅ MMDVM-Push-Notifier Installed Successfully! ($ACTUAL_VER)"
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
HEALTH=$(python3 $INSTALL_DIR/mmdvm_push.py --health 2>/dev/null)
if [ -n "$HEALTH" ]; then
    echo "健康状态: $HEALTH"
fi
