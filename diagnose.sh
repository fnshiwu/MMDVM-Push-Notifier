#!/bin/bash
# MMDVM 推送诊断脚本

echo "=========================================="
echo "MMDVM-Push-Notifier 诊断工具"
echo "=========================================="
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
if [ -f /tmp/mmdvm_push.log ]; then
    echo "日志位置: /tmp/mmdvm_push.log"
    tail -20 /tmp/mmdvm_push.log
elif [ -f /var/log/pi-star/mmdvm_push.log ]; then
    echo "日志位置: /var/log/pi-star/mmdvm_push.log"
    tail -20 /var/log/pi-star/mmdvm_push.log
else
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
echo "本机 IP: $(hostname -I)"
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

echo "=========================================="
echo "诊断完成"
echo "=========================================="
