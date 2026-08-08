#!/bin/bash
# MMDVM-Push-Notifier enhanced installer (v3.5.1-pistar4.3) | 强化版安装脚本
# Pi-Star 4.3.x (Debian 12 Bookworm) Compatible | 兼容 Pi-Star 4.3.x

if [ "$EUID" -ne 0 ]; then 
  echo "请使用 sudo 运行此脚本: sudo ./install.sh"
  exit 1
fi

# =========================
# Pi-Star Version Detection | Pi-Star 版本检测
# =========================
PISTAR_VER="unknown"
PISTAR_MAJOR=0
PISTAR_MINOR=0
PISTAR_PATCH=0

if [ -f /etc/pistar-release ]; then
    PISTAR_VER=$(grep -oP 'Version=\K[^ ]+' /etc/pistar-release 2>/dev/null || echo "unknown")
    if [[ "$PISTAR_VER" =~ ^([0-9]+)\.([0-9]+)\.([0-9]+) ]]; then
        PISTAR_MAJOR="${BASH_REMATCH[1]}"
        PISTAR_MINOR="${BASH_REMATCH[2]}"
        PISTAR_PATCH="${BASH_REMATCH[3]}"
    fi
fi

echo "=========================================="
echo "MMDVM-Push-Notifier Installer"
echo "Detected Pi-Star Version: $PISTAR_VER"
echo "=========================================="

# =========================
# Debian 12 Bookworm Detection | Debian 12 检测
# =========================
IS_BOOKWORM=false
DEBIAN_VER=$(cat /etc/debian_version 2>/dev/null || echo "unknown")

if [ -f /usr/lib/python3.11/EXTERNALLY-MANAGED ] || \
   [ -f /usr/lib/python3.*/EXTERNALLY-MANAGED ] 2>/dev/null || \
   [[ "$DEBIAN_VER" == 12* ]]; then
    IS_BOOKWORM=true
    echo "ℹ️  Detected Debian 12 Bookworm (Python externally managed)"
fi

# =========================
# 1) Prepare disk and tmpfs space | 准备磁盘与内存盘空间
# =========================
echo "1. 正在获取磁盘写入权限..."
mount -o remount,rw / 2>/dev/null

for cmd_path in /usr/local/sbin/rpi-rw /usr/local/bin/rpi-rw /usr/bin/rpi-rw; do
    if [ -x "$cmd_path" ]; then
        "$cmd_path"
        break
    fi
done

mount -o remount,size=32M /run 2>/dev/null 

echo "1. Creating and setting directory permissions... | 正在创建并设置目录权限..."
INSTALL_DIR="/home/pi-star/MMDVM-Push-Notifier"
mkdir -p $INSTALL_DIR

# Create service user | 创建服务用户
id -u mmdvm-push >/dev/null 2>&1 || useradd -r -s /usr/sbin/nologin -U mmdvm-push
usermod -a -G www-data mmdvm-push
chown -R mmdvm-push:mmdvm-push $INSTALL_DIR
chmod -R 755 $INSTALL_DIR
cd $INSTALL_DIR || { echo "错误: 无法进入目录 $INSTALL_DIR"; exit 1; }

# Check required files | 检查必要文件
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
chmod 664 $CONFIG_FILE
echo "Config file permission set to 664 (owner: mmdvm-push, group: www-data) | 配置文件权限已设置为 664（owner: mmdvm-push, group: www-data）"

echo "3. Deploy Web admin (symlink) | 部署 Web 管理页面（软链接）..."
WEB_ADMIN_DIR="/var/www/dashboard/admin"
mkdir -p "$WEB_ADMIN_DIR" 2>/dev/null

ln -sf "$INSTALL_DIR/push_admin.php" "$WEB_ADMIN_DIR/push_admin.php"
ln -sf "$INSTALL_DIR/push_admin.php" "/var/www/dashboard/push_admin.php" 2>/dev/null
ln -sf "$INSTALL_DIR/push_admin.php" "/var/www/html/push_admin.php" 2>/dev/null

chown www-data:www-data "$INSTALL_DIR/push_admin.php"
chmod 644 "$INSTALL_DIR/push_admin.php"

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
www-data ALL=(ALL) NOPASSWD: /usr/bin/systemctl start mmdvm_push.service
www-data ALL=(ALL) NOPASSWD: /usr/bin/systemctl stop mmdvm_push.service
www-data ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart mmdvm_push.service
www-data ALL=(ALL) NOPASSWD: /usr/bin/systemctl status mmdvm_push.service
www-data ALL=(ALL) NOPASSWD: /bin/systemctl start mmdvm_push.service
www-data ALL=(ALL) NOPASSWD: /bin/systemctl stop mmdvm_push.service
www-data ALL=(ALL) NOPASSWD: /bin/systemctl restart mmdvm_push.service
www-data ALL=(ALL) NOPASSWD: /bin/systemctl status mmdvm_push.service
www-data ALL=(ALL) NOPASSWD: /usr/local/sbin/rpi-rw
www-data ALL=(ALL) NOPASSWD: /usr/local/sbin/rpi-ro
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
visudo -cf "$SUDO_D" >/dev/null 2>&1 || { 
    echo "⚠️  Sudoers validation failed, removing custom file"
    rm -f "$SUDO_D"
}

echo "5. Install and start systemd service | 配置并启动 systemd 服务..."
if [ -f "$INSTALL_DIR/mmdvm_push.service" ]; then
    cp $INSTALL_DIR/mmdvm_push.service /etc/systemd/system/
    chmod 644 /etc/systemd/system/mmdvm_push.service
else
    echo "错误: 在 $INSTALL_DIR 中找不到 mmdvm_push.service 文件！"
    exit 1
fi

rm -rf /run/log/journal/* 2>/dev/null

systemctl daemon-reload
systemctl enable mmdvm_push.service
systemctl restart mmdvm_push.service

# --- Post-Install Summary / 安装后检查 ---
ACTUAL_VER=$(python3 $INSTALL_DIR/mmdvm_push.py --version 2>/dev/null)
if [ -z "$ACTUAL_VER" ]; then ACTUAL_VER="unknown"; fi
echo "--------------------------------------------------------"
echo "✅ MMDVM-Push-Notifier Installed Successfully! ($ACTUAL_VER)"
echo "Pi-Star Version: $PISTAR_VER"
echo "Debian Version: $DEBIAN_VER"
echo "Bookworm Mode: $IS_BOOKWORM"
echo "--------------------------------------------------------"
echo "🌐 Web Admin: http://pi-star.local/admin/push_admin.php"
echo "   (Or via IP: http://$(hostname -I | awk '{print $1}')/admin/push_admin.php)"
echo ""
echo "⚙️  Config File: $CONFIG_FILE"
echo "📂 Log Path:    /var/log/pi-star/mmdvm_push.log"
echo "--------------------------------------------------------"
HEALTH=$(python3 $INSTALL_DIR/mmdvm_push.py --health 2>/dev/null)
if [ -n "$HEALTH" ]; then
    echo "健康状态: $HEALTH"
fi
