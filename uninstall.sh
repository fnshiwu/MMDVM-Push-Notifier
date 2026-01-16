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
WEB_LINK="/var/www/dashboard/admin/push_admin.php"
WEB_LINK_2="/var/www/dashboard/push_admin.php"
CONFIG_FILE="/etc/mmdvm_push.json"

if [ -d "$INSTALL_DIR" ]; then
    sudo rm -rf "$INSTALL_DIR"
    echo "   - Removed $INSTALL_DIR"
fi

if [ -L "$WEB_LINK" ] || [ -f "$WEB_LINK" ]; then
    sudo rm -f "$WEB_LINK"
    echo "   - Removed $WEB_LINK"
fi

if [ -L "$WEB_LINK_2" ] || [ -f "$WEB_LINK_2" ]; then
    sudo rm -f "$WEB_LINK_2"
    echo "   - Removed $WEB_LINK_2"
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

# 5. Clean up sudoers (Optional but good)
# Removing the specific line for update.sh if it exists
SUDO_FILE="/etc/sudoers"
# It's risky to edit sudoers with sed script, maybe just leave it or warn.
# The install script added: echo "www-data ALL=(ALL) NOPASSWD: $UPDATE_SCRIPT"
# We can try to remove it safely if we are sure.
# For safety, I will skip editing sudoers automatically to avoid breaking the system.
echo "Note: The sudoers entry for update.sh was left untouched for safety."

echo "--- Uninstall Complete / 卸载完成 ---"
