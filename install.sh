#!/bin/bash
# MMDVM-Push-Notifier 强化版安装脚本 (v3.1.7) - 原生 UI 适配版

if [ "$EUID" -ne 0 ]; then 
  echo "请使用 sudo 运行此脚本: sudo ./install.sh"
  exit
fi

# 1. 准备磁盘与内存空间
echo "1. 正在获取磁盘写入权限..."
mount -o remount,rw / 2>/dev/null
if command -v rpi-rw >/dev/null 2>&1; then
    rpi-rw
elif [ -f /usr/local/bin/rpi-rw ]; then
    /usr/local/bin/rpi-rw
fi

mount -o remount,size=32M /run 2>/dev/null 

echo "2. 正在创建并设置目录权限..."
INSTALL_DIR="/home/pi-star/MMDVM-Push-Notifier"
mkdir -p $INSTALL_DIR
id -u mmdvm-push >/dev/null 2>&1 || useradd -r -s /usr/sbin/nologin -U mmdvm-push
chown -R mmdvm-push:mmdvm-push $INSTALL_DIR
chmod -R 755 $INSTALL_DIR
cd $INSTALL_DIR || { echo "错误: 无法进入目录 $INSTALL_DIR"; exit 1; }

# 核心文件检查
REQ_FILES="mmdvm_push.py push_admin.php parser.py filters.py notify_fmt.py mmdvm_push.service"
for f in $REQ_FILES; do
    if [ ! -f "$f" ]; then echo "错误: 缺少必要文件: $f"; exit 1; fi
done

echo "3. 初始化配置并设置权限..."
CONFIG_FILE="/etc/mmdvm_push.json"
if [ ! -f "$CONFIG_FILE" ]; then
    echo '{"my_callsign":"BA4SMQ","min_duration":5.0,"ui_lang":"cn"}' > $CONFIG_FILE
fi
chown mmdvm-push:www-data $CONFIG_FILE
chmod 660 $CONFIG_FILE

echo "4. 部署 Web 管理页面软链接..."
WEB_DIRS="/var/www/dashboard/admin /var/www/html/admin /var/www/admin"
for D in $WEB_DIRS; do
    if [ -d "$D" ]; then ln -sf $INSTALL_DIR/push_admin.php "$D/push_admin.php"; fi
done
if [ -d "/var/www/dashboard" ]; then
    ln -sf $INSTALL_DIR/push_admin.php /var/www/dashboard/push_admin.php
fi
chown www-data:www-data $INSTALL_DIR/push_admin.php

echo "5. 授权网页端系统管理权限..."
SUDO_D="/etc/sudoers.d/mmdvm-push-web"
cat > "$SUDO_D" <<'EOF'
www-data ALL=(ALL) NOPASSWD: /bin/systemctl start mmdvm_push.service
www-data ALL=(ALL) NOPASSWD: /bin/systemctl stop mmdvm_push.service
www-data ALL=(ALL) NOPASSWD: /bin/systemctl restart mmdvm_push.service
www-data ALL=(ALL) NOPASSWD: /bin/systemctl status mmdvm_push.service
EOF
chmod 440 "$SUDO_D"

echo "6. 配置并启动系统服务..."
cp $INSTALL_DIR/mmdvm_push.service /etc/systemd/system/
chmod 644 /etc/systemd/system/mmdvm_push.service
systemctl daemon-reload
systemctl enable mmdvm_push.service
systemctl restart mmdvm_push.service

# --- 核心修改：原生白色字体注入 ---
echo "7. 正在注入管理菜单按钮..."
SIDEBAR_FILE="/var/www/dashboard/admin/header.php"
if [ -f "$SIDEBAR_FILE" ]; then
    # 检查是否已存在
    if ! grep -q "push_admin.php" "$SIDEBAR_FILE"; then
        # 严格遵守 Pi-Star 默认 HTML 结构，不添加任何 style 属性
        sed -i '/dash.php/a <li><a href="/admin/push_admin.php">推送设置</a></li>' "$SIDEBAR_FILE"
        echo "✅ 菜单注入成功！"
    else
        echo "ℹ️  按钮已存在，跳过注入。"
    fi
fi

echo "--------------------------------------------------------"
echo "✅ 安装成功！请刷新浏览器查看【仪表盘】下的新按钮。"
echo "--------------------------------------------------------"
