#!/bin/bash
# MMDVM-Push-Notifier uninstaller (v2.1.0-pistar4.3.7) | 卸载脚本
# Pi-Star 4.3.7 Compatible

echo "--- MMDVM-Push-Notifier Uninstaller ---"
echo "WARNING: This will remove the service, configuration, and web interface."
echo "警告：这将删除服务、配置文件和 Web 管理界面。"
read -p "Are you sure? (y/n) / 确定要继续吗？(y/n): " confirm
if [[ $confirm != [yY] && $confirm != [yY][eE][sS] ]]; then
    echo "Aborted. / 操作已取消。"
    exit 1
fi

# 1) Get write permission | 获取写入权限
echo "1. Requesting disk write permission..."
sudo mount -o remount,rw / 2>/dev/null

# Try all possible rpi-rw paths | 尝试所有可能的 rpi-rw 路径
for cmd_path in /usr/local/sbin/rpi-rw /usr/local/bin/rpi-rw /usr/bin/rpi-rw; do
    if [ -x "$cmd_path" ]; then
        sudo "$cmd_path"
        break
    fi
done

# 2) Stop and disable service | 停止并禁用服务
echo "2. Stopping service..."
if systemctl is-active --quiet mmdvm_push.service; then
    sudo systemctl stop mmdvm_push.service
fi
sudo systemctl disable mmdvm_push.service 2>/dev/null
sudo rm -f /etc/systemd/system/mmdvm_push.service
sudo systemctl daemon-reload

# 3) Remove files | 删除文件
echo "3. Removing files..."
INSTALL_DIR="/home/pi-star/MMDVM-Push-Notifier"
ADMIN_LINK="/var/www/dashboard/admin/push_admin.php"
CONFIG_FILE="/etc/mmdvm_push.json"

if [ -d "$INSTALL_DIR" ]; then
    sudo rm -rf "$INSTALL_DIR"
    echo "   - Removed $INSTALL_DIR"
fi

if [ -L "$ADMIN_LINK" ] || [ -f "$ADMIN_LINK" ]; then
    sudo rm -f "$ADMIN_LINK"
    echo "   - Removed $ADMIN_LINK"
fi

# Revert nav injection (restore backups or remove inserted block) | 还原导航注入（恢复备份或移除插入块）
sudo find /var/www -type f -name "*.bak_pushnav" -delete 2>/dev/null
ADMIN_INDEX="/var/www/dashboard/admin/index.php"
if [ -f "$ADMIN_INDEX.bak_pushnav" ]; then
    sudo mv -f "$ADMIN_INDEX.bak_pushnav" "$ADMIN_INDEX"
else
    if [ -f "$ADMIN_INDEX" ]; then
        sudo sed -i '/推送设置/d' "$ADMIN_INDEX" 2>/dev/null || true
    fi
fi
sudo chown www-data:www-data "$ADMIN_INDEX" 2>/dev/null || true
sudo chmod 644 "$ADMIN_INDEX" 2>/dev/null || true

# 4) Remove config (optional) | 删除配置（可选）
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
