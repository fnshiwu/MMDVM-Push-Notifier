#!/bin/bash
# MMDVM-Push-Notifier 核心全自动更新脚本 (v3.1.8)
# 适用平台: Pi-Star / Debian

echo "--- 开始执行一键更新流程 ---"

# 1. 切换磁盘至读写模式 (原生指令优先)
echo "正在请求磁盘写入权限..."
sudo mount -o remount,rw / 2>/dev/null
# 尝试兼容 Pi-Star 自带脚本
sudo /usr/local/bin/rpi-rw 2>/dev/null || sudo /usr/bin/rpi-rw 2>/dev/null

# 2. 进入项目目录并修复 Git 信任问题
INSTALL_DIR="/home/pi-star/MMDVM-Push-Notifier"
cd $INSTALL_DIR || { echo "错误: 无法进入目录 $INSTALL_DIR"; exit 1; }

echo "正在解决 Git 信任限制..."
git config --global --add safe.directory $INSTALL_DIR

# 3. 从 GitHub 同步所有核心文件 (py, php, service, sh)
echo "正在拉取远程仓库最新代码..."
sudo git fetch --all
sudo git reset --hard origin/main

# 核心文件完整性检查
REQ_FILES="mmdvm_push.py push_admin.php parser.py filters.py notify_fmt.py mmdvm_push.service"
MISSING=""
for f in $REQ_FILES; do
    [ -f "$f" ] || MISSING="$MISSING $f"
done
if [ -n "$MISSING" ]; then
    echo "错误: 缺少必要文件:$MISSING"
    exit 1
fi

# 3.5 确保服务用户存在并修复目录所有权
id -u mmdvm-push >/dev/null 2>&1 || sudo useradd -r -s /usr/sbin/nologin -U mmdvm-push
sudo chown -R mmdvm-push:mmdvm-push $INSTALL_DIR

# 4. 解决 /run 空间不足隐患并同步服务配置
if [ -f "mmdvm_push.service" ]; then
    echo "正在同步服务配置文件..."
    sudo cp mmdvm_push.service /etc/systemd/system/
    sudo chmod 644 /etc/systemd/system/mmdvm_push.service
    
    # 针对 16MB 安全缓冲区不足的专项修复
    echo "正在清理并优化系统内存盘空间..."
    sudo mount -o remount,size=32M /run 2>/dev/null
    sudo rm -rf /run/log/journal/* 2>/dev/null
    
    sudo systemctl daemon-reload
fi

# 5. 权限重置与加固 (最小权限原则)
CONFIG_FILE="/etc/mmdvm_push.json"
if [ -f "$CONFIG_FILE" ]; then
    echo "正在修复配置文件权限 (660)..."
    sudo chown mmdvm-push:www-data $CONFIG_FILE
    sudo chmod 660 $CONFIG_FILE
fi

# 6. 赋予脚本自身及安装脚本执行权限
sudo chmod +x install.sh update.sh

# 7. 重启推送服务以加载新版本代码
echo "正在重启 MMDVM 推送服务..."
sudo systemctl restart mmdvm_push.service

echo "------------------------"
echo "--- 更新完成 ---"

# 确保 sudoers 规则存在
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

# 重新部署 Web 管理页面链接（多路径兼容）
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

# 8. 实时读取核心 Python 程序的版本号
# 逻辑：尝试执行脚本获取版本，失败则显示预设版本
ACTUAL_VER=$(python3 $INSTALL_DIR/mmdvm_push.py --version 2>/dev/null)
if [ -z "$ACTUAL_VER" ]; then
    echo "当前版本: v3.0.15 (无法通过脚本读取)"
else
    echo "当前版本: $ACTUAL_VER"
fi

# 显示服务状态（只显示前几行，避免刷屏）
sudo systemctl status mmdvm_push.service --no-pager | grep -E "Active:|Main PID:"

# 输出健康状态
HEALTH=$(python3 $INSTALL_DIR/mmdvm_push.py --health 2>/dev/null)
if [ -n "$HEALTH" ]; then
    echo "健康状态: $HEALTH"
fi
