#!/bin/bash
# MMDVM-Push-Notifier auto update script (v3.1.7) | 核心全自动更新脚本
# Target platforms: Pi-Star / Debian | 适用平台：Pi-Star / Debian

echo "--- 开始执行一键更新流程 ---"

# 1) Remount root as RW (native commands first) | 切换根分区为读写（原生命令优先）
echo "正在请求磁盘写入权限..."
sudo mount -o remount,rw / 2>/dev/null
# Try Pi-Star helper scripts | 兼容 Pi-Star 自带脚本
sudo /usr/local/bin/rpi-rw 2>/dev/null || sudo /usr/bin/rpi-rw 2>/dev/null

# 2) Enter project dir and fix Git trust | 进入项目目录并修复 Git 信任
INSTALL_DIR="/home/pi-star/MMDVM-Push-Notifier"
cd $INSTALL_DIR || { echo "错误: 无法进入目录 $INSTALL_DIR"; exit 1; }

echo "正在解决 Git 信任限制..."
git config --global --add safe.directory $INSTALL_DIR

# 3) Sync latest code from GitHub | 从 GitHub 同步代码（py/php/service/sh）
echo "正在拉取远程仓库最新代码..."
sudo git fetch --all
sudo git reset --hard origin/main

# Core files integrity check | 核心文件完整性检查
REQ_FILES="mmdvm_push.py push_admin.php parser.py filters.py notify_fmt.py mmdvm_push.service"
MISSING=""
for f in $REQ_FILES; do
    [ -f "$f" ] || MISSING="$MISSING $f"
done
if [ -n "$MISSING" ]; then
    echo "错误: 缺少必要文件:$MISSING"
    exit 1
fi

# 3.5) Ensure service user and ownership | 确保服务用户存在并修复所有权
id -u mmdvm-push >/dev/null 2>&1 || sudo useradd -r -s /usr/sbin/nologin -U mmdvm-push
sudo chown -R mmdvm-push:mmdvm-push $INSTALL_DIR

# 4) Fix /run space risk and sync service unit | 解决 /run 空间不足并同步服务单元
if [ -f "mmdvm_push.service" ]; then
    echo "正在同步服务配置文件..."
    sudo cp mmdvm_push.service /etc/systemd/system/
    sudo chmod 644 /etc/systemd/system/mmdvm_push.service
    
    # Patch: expand /run tmpfs from 16MB to 32MB | 专项修复：/run 扩容 16MB→32MB
    echo "正在清理并优化系统内存盘空间..."
    sudo mount -o remount,size=32M /run 2>/dev/null
    sudo rm -rf /run/log/journal/* 2>/dev/null
    
    sudo systemctl daemon-reload
fi

# 5) Reset and harden permissions (least privilege) | 权限重置与加固（最小权限）
CONFIG_FILE="/etc/mmdvm_push.json"
if [ -f "$CONFIG_FILE" ]; then
    echo "正在修复配置文件权限 (660)..."
    sudo chown mmdvm-push:www-data $CONFIG_FILE
    sudo chmod 660 $CONFIG_FILE
fi

# 6) Ensure executable bits for scripts | 设置脚本可执行权限
sudo chmod +x install.sh update.sh

# 7) Restart service to load new code | 重启服务以加载新版本
echo "正在重启 MMDVM 推送服务..."
sudo systemctl restart mmdvm_push.service

echo "------------------------"
echo "--- 更新完成 ---"

# Ensure sudoers rule exists | 确保 sudoers 规则存在
SUDO_D="/etc/sudoers.d/mmdvm-push-web"
if [ ! -f "$SUDO_D" ]; then
cat > "$SUDO_D" <<'EOF'
www-data ALL=(ALL) NOPASSWD: /bin/systemctl start mmdvm_push.service
www-data ALL=(ALL) NOPASSWD: /bin/systemctl stop mmdvm_push.service
www-data ALL=(ALL) NOPASSWD: /bin/systemctl restart mmdvm_push.service
www-data ALL=(ALL) NOPASSWD: /bin/systemctl status mmdvm_push.service
EOF
chmod 440 "$SUDO_D"
visudo -cf "$SUDO_D" >/dev/null 2>&1 || rm -f "$SUDO_D"
fi

# Redeploy web admin symlinks (multi-path) | 重新部署 Web 管理页软链接（多路径）
INSTALL_DIR="/home/pi-star/MMDVM-Push-Notifier"
WEB_DIRS="/var/www/dashboard/admin /var/www/html/admin /var/www/admin"
for D in $WEB_DIRS; do
    if [ -d "$D" ]; then
        sudo ln -sf $INSTALL_DIR/push_admin.php "$D/push_admin.php"
    fi
done
if [ -d "/var/www/dashboard" ]; then
    sudo ln -sf $INSTALL_DIR/push_admin.php /var/www/dashboard/push_admin.php
fi
sudo chown www-data:www-data $INSTALL_DIR/push_admin.php

NAV_FILES="/var/www/dashboard/index.php /var/www/dashboard/admin/index.php /var/www/dashboard/admin/admin.php /var/www/html/index.php /var/www/admin/index.php"
for HF in $NAV_FILES; do
    if [ -f "$HF" ] && ! grep -q "push_admin.php" "$HF"; then
        sudo cp "$HF" "$HF.bak_pushnav" 2>/dev/null
        sudo sed -i 's#</body>#<div id="push-nav" style="position:fixed;top:8px;right:12px;z-index:99999;"><a href="/admin/push_admin.php" style="color:#fff;background:#444;padding:4px 8px;border-radius:3px;font-weight:bold;border:1px solid #000;text-decoration:none;">Push Settings</a></div></body>#' "$HF" 2>/dev/null || true
    fi
done

# 8) Read actual version from core script | 读取核心脚本版本
# Fallback to preset if execution fails | 执行失败则回退预设
ACTUAL_VER=$(python3 $INSTALL_DIR/mmdvm_push.py --version 2>/dev/null)
if [ -z "$ACTUAL_VER" ]; then
    echo "当前版本: v3.0.15 (无法通过脚本读取)"
else
    echo "当前版本: $ACTUAL_VER"
fi

# Show service status (brief) | 显示服务状态（精简）
sudo systemctl status mmdvm_push.service --no-pager | grep -E "Active:|Main PID:"

# Output health JSON | 输出健康状态 JSON
HEALTH=$(python3 $INSTALL_DIR/mmdvm_push.py --health 2>/dev/null)
if [ -n "$HEALTH" ]; then
    echo "健康状态: $HEALTH"
fi
