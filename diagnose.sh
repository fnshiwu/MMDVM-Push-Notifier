#!/bin/bash
# MMDVM 推送诊断脚本 (v2.1.0-pistar4.3.7)
# Pi-Star 4.3.7 Compatible

echo "=========================================="
echo "MMDVM-Push-Notifier 诊断工具"
echo "=========================================="
echo ""

# Pi-Star Version Detection | Pi-Star 版本检测
PISTAR_VER="unknown"
if [ -f /etc/pistar-release ]; then
    PISTAR_VER=$(grep -oP 'Version=\K[^ ]+' /etc/pistar-release 2>/dev/null || echo "unknown")
fi
DEBIAN_VER=$(cat /etc/debian_version 2>/dev/null || echo "unknown")
echo "系统信息: Pi-Star $PISTAR_VER / Debian $DEBIAN_VER"
if [ -f /usr/lib/python3.11/EXTERNALLY-MANAGED ] || [ -f /usr/lib/python3.*/EXTERNALLY-MANAGED ] 2>/dev/null; then
    echo "Python 环境: Externally Managed (Bookworm)"
fi
echo ""

# 1. 检查服务状态
echo "[1] 服务状态检查"
echo "----------------------------------------"
sudo systemctl status mmdvm_push | head -15
echo ""

# 2. 检查进程
echo "[2] 进程检查"
echo "----------------------------------------"
ps aux | grep mmdvm_push | grep -v grep
echo ""

# 3. 检查最新日志
echo "[3] 最新日志 (最后20行)"
echo "----------------------------------------"
LOG_FOUND=false
for log_path in /var/log/pi-star/mmdvm_push.log /tmp/mmdvm_push.log; do
    if [ -f "$log_path" ]; then
        echo "日志位置: $log_path"
        tail -20 "$log_path"
        LOG_FOUND=true
        break
    fi
done
if [ "$LOG_FOUND" = false ]; then
    echo "❌ 未找到日志文件"
fi
echo ""

# 4. 检查配置文件
echo "[4] 配置文件检查"
echo "----------------------------------------"
if [ -f /etc/mmdvm_push.json ]; then
    echo "✓ 配置文件存在: /etc/mmdvm_push.json"
    echo "配置内容:"
    cat /etc/mmdvm_push.json | python3 -m json.tool 2>/dev/null || cat /etc/mmdvm_push.json
else
    echo "❌ 配置文件不存在: /etc/mmdvm_push.json"
fi
echo ""

# 5. 检查 MMDVM 日志
echo "[5] MMDVM 日志检查 (最后10行)"
echo "----------------------------------------"
LATEST_LOG=$(ls -t /var/log/pi-star/MMDVM-*.log 2>/dev/null | head -1)
if [ -n "$LATEST_LOG" ]; then
    echo "日志文件: $LATEST_LOG"
    tail -10 "$LATEST_LOG"
else
    echo "❌ 未找到 MMDVM 日志"
fi
echo ""

# 6. 检查网络连接
echo "[6] 网络连接检查"
echo "----------------------------------------"
echo "本机 IP: $(hostname -I 2>/dev/null || echo 'Unknown')"
echo "测试网络连通性..."
if ping -c 2 www.baidu.com >/dev/null 2>&1; then
    echo "✓ 网络连通"
else
    echo "❌ 网络不通"
fi
echo ""

# 7. 测试推送
echo "[7] 测试推送"
echo "----------------------------------------"
cd /home/pi-star/MMDVM-Push-Notifier
echo "运行测试推送..."
sudo python3 mmdvm_push.py --test
echo ""

# 8. 健康检查
echo "[8] 健康检查"
echo "----------------------------------------"
sudo python3 /home/pi-star/MMDVM-Push-Notifier/mmdvm_push.py --health 2>&1
echo ""

# 9. 系统环境检查 (Bookworm 特有)
echo "[9] 系统环境检查"
echo "----------------------------------------"
echo "Python 版本: $(python3 --version 2>&1)"
echo "PHP 版本: $(php -v 2>/dev/null | head -1 || echo 'Not installed')"
echo "systemd 版本: $(systemctl --version 2>/dev/null | head -1 || echo 'Unknown')"

# Check sudoers compatibility
echo ""
echo "Sudoers 检查:"
if [ -f /etc/sudoers.d/pistar-dashboard ]; then
    echo "  ✓ Pi-Star 4.3.5+ dashboard sudoers 存在"
fi
if [ -f /etc/sudoers.d/mmdvm-push-web ]; then
    echo "  ✓ MMDVM-Push sudoers 存在"
    visudo -cf /etc/sudoers.d/mmdvm-push-web >/dev/null 2>&1 && echo "  ✓ Sudoers 语法有效" || echo "  ❌ Sudoers 语法错误"
else
    echo "  ❌ MMDVM-Push sudoers 不存在"
fi

echo ""
echo "=========================================="
echo "诊断完成"
echo "=========================================="
