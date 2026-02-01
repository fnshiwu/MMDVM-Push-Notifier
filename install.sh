#!/bin/bash
# MMDVM-Push-Notifier 适配脚本 (横向导航栏 + 动态地址提示版)

if [ "$EUID" -ne 0 ]; then 
  echo "请使用 sudo 运行此脚本: sudo ./install.sh"
  exit
fi

# 1. 获取权限
echo "1. 正在获取磁盘写入权限..."
mount -o remount,rw / 2>/dev/null
[ -f /usr/local/bin/rpi-rw ] && /usr/local/bin/rpi-rw

# 2. 设置路径
INSTALL_DIR="/home/pi-star/MMDVM-Push-Notifier"
WEB_ROOT="/var/www/dashboard"
ADMIN_INDEX="$WEB_ROOT/admin/index.php"

# 3. 建立文件链接
echo "2. 部署 Web 文件链接..."
ln -sf $INSTALL_DIR/push_admin.php "$WEB_ROOT/admin/push_admin.php"
chown www-data:www-data "$WEB_ROOT/admin/push_admin.php"

# 4. 修改导航栏
echo "3. 正在修改导航栏按钮..."
if [ -f "$ADMIN_INDEX" ]; then
    if ! grep -q "push_admin.php" "$ADMIN_INDEX"; then        
        sed -i 's|update.php">更新</a>|update.php">更新</a> \| <a href="push_admin.php" style="color: #ffffff;">推送设置</a>|g' "$ADMIN_INDEX"
        sed -i 's|update.php">Update</a>|update.php">Update</a> \| <a href="push_admin.php" style="color: #ffffff;">推送设置</a>|g' "$ADMIN_INDEX"
        echo "✅ 导航栏按钮注入成功！"
    else
        echo "ℹ️  按钮已存在，跳过注入。"
    fi
fi

# 5. 启动服务
if [ -f "$INSTALL_DIR/mmdvm_push.service" ]; then
    cp $INSTALL_DIR/mmdvm_push.service /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable mmdvm_push.service
    systemctl restart mmdvm_push.service
fi

# 6. 获取通用地址
LOCAL_IP=$(hostname -I | awk '{print $1}')
HOST_NAME=$(hostname)

# --- 安装完成提示 ---
echo "--------------------------------------------------------"
echo "✅ MMDVM-Push-Notifier 安装成功！"
echo "--------------------------------------------------------"
echo "🌐 您可以通过以下任意地址访问管理页面："
echo "   http://${HOST_NAME}.local/admin/push_admin.php"
echo "   http://${LOCAL_IP}/admin/push_admin.php"
echo ""
echo "💡 提示：您也可以直接点击顶部导航栏新增的【推送设置】按钮。"
echo "--------------------------------------------------------"
