#!/bin/bash
# MMDVM-Push-Notifier Uninstaller
# MMDVM-Push-Notifier 卸载脚本

echo "--- MMDVM-Push-Notifier Uninstaller ---"
echo "WARNING: This will remove the service, configuration, and web interface."
echo "警告：这将删除服务、配置文件和 Web 管理界面。"
read -p "Are you sure? (y/n) / 确定要继续吗？(y/n): " confirm
if [[ $confirm != [yY] && $confirm != [yY][eE][sS] ]]; then
    echo "Aborted. / 操作已取消。"
    exit 1
fi

# 1. Get write permission
echo "1. Requesting disk write permission..."
sudo mount -o remount,rw / 2>/dev/null
sudo /usr/local/bin/rpi-rw 2>/dev/null || sudo /usr/bin/rpi-rw 2>/dev/null

# 2. Stop and disable service
echo "2. Stopping service..."
if systemctl is-active --quiet mmdvm_push.service; then
    sudo systemctl stop mmdvm_push.service
fi
sudo systemctl disable mmdvm_push.service 2>/dev/null
sudo rm -f /etc/systemd/system/mmdvm_push.service
sudo systemctl daemon-reload

# 3. Remove files
echo "3. Removing files..."
INSTALL_DIR="/home/pi-star/MMDVM-Push-Notifier"
WEB_DIRS="/var/www/dashboard/admin /var/www/html/admin /var/www/admin"
DASH_LINK="/var/www/dashboard/push_admin.php"
CONFIG_FILE="/etc/mmdvm_push.json"

if [ -d "$INSTALL_DIR" ]; then
    sudo rm -rf "$INSTALL_DIR"
    echo "   - Removed $INSTALL_DIR"
fi

for D in $WEB_DIRS; do
    if [ -L "$D/push_admin.php" ] || [ -f "$D/push_admin.php" ]; then
        sudo rm -f "$D/push_admin.php"
        echo "   - Removed $D/push_admin.php"
    fi
done
if [ -L "$DASH_LINK" ] || [ -f "$DASH_LINK" ]; then
    sudo rm -f "$DASH_LINK"
    echo "   - Removed $DASH_LINK"
fi

# 4. Remove config (Optional)
read -p "Remove configuration file? (y/n) / 删除配置文件吗？(y/n): " del_conf
if [[ $del_conf == [yY] || $del_conf == [yY][eE][sS] ]]; then
    if [ -f "$CONFIG_FILE" ]; then
        sudo rm -f "$CONFIG_FILE"
        echo "   - Removed $CONFIG_FILE"
    fi
else
    echo "   - Configuration file kept at $CONFIG_FILE"
fi

SUDO_D="/etc/sudoers.d/mmdvm-push-web"
if [ -f "$SUDO_D" ]; then
    sudo rm -f "$SUDO_D"
    echo "   - Removed $SUDO_D"
fi

read -p "Remove service user mmdvm-push? (y/n) / 删除服务用户 mmdvm-push？(y/n): " del_user
if [[ $del_user == [yY] || $del_user == [yY][eE][sS] ]]; then
    id -u mmdvm-push >/dev/null 2>&1 && sudo userdel -r mmdvm-push
    echo "   - Removed user mmdvm-push"
fi

LOG_FILE="/var/log/pi-star/mmdvm_push.log"
if [ -f "$LOG_FILE" ]; then
    sudo rm -f "$LOG_FILE"
    echo "   - Removed $LOG_FILE"
fi

echo "--- Uninstall Complete / 卸载完成 ---"
