#!/bin/bash
# MMDVM-Push-Notifier diagnostic tool
# Pi-Star 4.2.x / 4.3.x - MMDVMHost
# 一键诊断：权限、日志、解析、配置、网络、推送逐层检查
set -o pipefail

INSTALL_DIR="/home/pi-star/MMDVM-Push-Notifier"
CONFIG_FILE="/etc/mmdvm_push.json"
SERVICE="mmdvm_push.service"
APP_LOG="/var/log/pi-star/mmdvm_push.log"

RED=$'\033[31m'; GRN=$'\033[32m'; YLW=$'\033[33m'; NC=$'\033[0m'
ok()   { echo "${GRN}✓${NC} $*"; }
warn() { echo "${YLW}⚠${NC} $*"; }
err()  { echo "${RED}✗${NC} $*"; }
hr()   { echo "----------------------------------------"; }

echo "=========================================="
echo " MMDVM-Push-Notifier 诊断工具"
echo " 时间: $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "=========================================="

PISTAR_VER="unknown"
[ -f /etc/pistar-release ] && PISTAR_VER=$(grep -oP 'Version=\K[^ ]+' /etc/pistar-release 2>/dev/null || echo "unknown")
DEBIAN_VER=$(cat /etc/debian_version 2>/dev/null || echo "unknown")
echo "Pi-Star: $PISTAR_VER   Debian: $DEBIAN_VER"
echo "Python: $(python3 --version 2>&1)"
echo "PHP   : $(php -r 'echo PHP_VERSION;' 2>/dev/null || echo missing)"
echo "kernel: $(uname -r)   systemd: $(systemctl --version 2>/dev/null | head -1)"
echo ""

# 1
echo "[1] 服务状态"
hr
systemctl is-enabled "$SERVICE" >/dev/null 2>&1 && ok "开机自启: $(systemctl is-enabled "$SERVICE" 2>/dev/null)" || warn "未设置开机自启"
if systemctl is-active --quiet "$SERVICE"; then
    ok "运行状态: active"
    systemctl status "$SERVICE" --no-pager 2>/dev/null | sed -n '1,6p'
else
    err "运行状态: $(systemctl is-active "$SERVICE" 2>/dev/null)"
    journalctl -u "$SERVICE" -n 15 --no-pager 2>/dev/null
fi
echo ""

# 2
echo "[2] 进程与身份"
hr
ps -eo pid,user,etimes,rss,args | grep -E "mmdvm_push\.py" | grep -v grep || err "未找到 mmdvm_push.py 进程"
echo ""

# 3
echo "[3] 目录与权限（关键项）"
hr
if id -u mmdvm-push >/dev/null 2>&1; then
    ok "服务用户: mmdvm-push (组: $(id -nG mmdvm-push 2>/dev/null))"
else
    err "服务用户 mmdvm-push 不存在"
fi

if [ -d /var/log/pi-star ]; then
    ok "日志目录存在: /var/log/pi-star ($(stat -c '%U:%G %a' /var/log/pi-star 2>/dev/null))"
    if sudo -u mmdvm-push test -r /var/log/pi-star 2>/dev/null; then
        ok "服务用户可读日志目录"
    else
        err "服务用户无法读取 /var/log/pi-star —— 这是收不到推送的最常见原因"
        echo "   修复: sudo usermod -a -G pi-star mmdvm-push && sudo systemctl restart $SERVICE"
    fi
else
    err "/var/log/pi-star 不存在（MMDVMHost 未安装或未运行）"
fi

LATEST_LOG=$(ls -t /var/log/pi-star/MMDVM-*.log 2>/dev/null | head -1)
if [ -n "$LATEST_LOG" ]; then
    ok "最新 MMDVM 日志: $LATEST_LOG ($(stat -c '%U:%G %a' "$LATEST_LOG" 2>/dev/null))"
    if sudo -u mmdvm-push test -r "$LATEST_LOG" 2>/dev/null; then
        ok "服务用户可读该日志文件"
    else
        err "服务用户无法读取 $LATEST_LOG"
    fi
else
    warn "未找到 /var/log/pi-star/MMDVM-*.log"
fi
echo ""

# 4
echo "[4] 配置"
hr
if [ -f "$CONFIG_FILE" ]; then
    ok "配置文件: $CONFIG_FILE ($(stat -c '%U:%G %a' "$CONFIG_FILE" 2>/dev/null))"
    if python3 -m json.tool "$CONFIG_FILE" >/dev/null 2>&1; then
        ok "JSON 语法正确"
    else
        err "JSON 语法错误 —— 服务会退回默认配置"
    fi
    python3 - "$CONFIG_FILE" <<'PY'
import json, sys
try:
    with open(sys.argv[1], encoding="utf-8") as fh:
        c = json.load(fh)
except Exception as exc:
    print("  读取失败:", exc); raise SystemExit
enabled = []
if c.get("push_fs_enabled") and c.get("fs_webhook"): enabled.append("Feishu")
if c.get("push_wx_enabled") and c.get("wx_token"): enabled.append("PushPlus")
if c.get("push_tg_enabled") and c.get("tg_token") and c.get("tg_chat_id"): enabled.append("Telegram")
print("  已启用通道:", ", ".join(enabled) if enabled else "无（!!! 至少启用一个通道）")
print("  我的呼号:", c.get("my_callsign") or "(未设置)")
print("  最小时长:", c.get("min_duration"), "s  静音:", c.get("quiet_mode", {}).get("enabled"))
print("  log_dir :", c.get("log_dir") or "(自动探测)")
PY
else
    err "配置文件不存在: $CONFIG_FILE"
fi
echo ""

# 5
echo "[5] 解析器自检"
hr
if [ -f "$INSTALL_DIR/parser.py" ]; then
    RES=$(python3 "$INSTALL_DIR/mmdvm_push.py" --selftest 2>/dev/null)
    echo "  $RES"
    echo "  真实日志最后一条通联行:"
    if [ -n "$LATEST_LOG" ]; then
        LAST=$(grep -a "end of" "$LATEST_LOG" 2>/dev/null | tail -1)
        if [ -n "$LAST" ]; then
            echo "    $LAST"
            if python3 "$INSTALL_DIR/mmdvm_push.py" --parse "$LAST" >/dev/null 2>&1; then
                ok "    该行可被解析"
            else
                err "    该行无法解析 —— 请把这一行反馈给作者以适配新日志格式"
            fi
        else
            warn "    日志中暂无通联结束行"
        fi
    fi
else
    err "未找到 $INSTALL_DIR/parser.py"
fi
echo ""

# 6
echo "[6] 网络"
hr
echo "本机 IP: $(hostname -I 2>/dev/null | awk '{print $1}')"
if ping -c 2 -W 2 223.5.5.5 >/dev/null 2>&1; then ok "ICMP 连通"; else warn "ICMP 不通（部分网络禁 ping，忽略）"; fi
for url in https://www.pushplus.plus https://api.telegram.org https://open.feishu.cn; do
    if curl -sS -m 6 -o /dev/null "$url" 2>/dev/null; then ok "可达 $url"; else warn "不可达 $url"; fi
done
echo ""

# 7
echo "[7] 推送测试"
hr
if [ -f "$INSTALL_DIR/mmdvm_push.py" ]; then
    # Run as the service user: root would succeed even when the daemon's own
    # permissions/network are broken. 以服务用户运行，root 成功不代表守护进程能成功。
    sudo -u mmdvm-push python3 "$INSTALL_DIR/mmdvm_push.py" --test 2>&1 | tail -5
else
    err "未找到 mmdvm_push.py"
fi
echo ""

# 8
echo "[8] 健康状态 (JSON)"
hr
sudo -u mmdvm-push python3 "$INSTALL_DIR/mmdvm_push.py" --health 2>&1 | tail -3
if [ -f "$APP_LOG" ]; then
    # grep -c prints 0 and exits 1 when nothing matches; `|| echo 0` would
    # append a second 0 and break the numeric test below.
    FAILS=$(grep -ac "PUSH_FAILED" "$APP_LOG" 2>/dev/null)
    FAILS=${FAILS:-0}
    if [ "$FAILS" -gt 0 ]; then
        warn "日志中已有 $FAILS 次推送失败（grep PUSH_FAILED $APP_LOG）"
        grep -a "PUSH_FAILED" "$APP_LOG" 2>/dev/null | tail -3
    else
        ok "日志中未发现推送失败"
    fi
fi
echo ""

# 9
echo "[9] 运行日志（最后 15 行）"
hr
if [ -f "$APP_LOG" ]; then
    tail -15 "$APP_LOG"
else
    warn "无 $APP_LOG，尝试 journalctl"
    journalctl -u "$SERVICE" -n 15 --no-pager 2>/dev/null
fi
echo ""

# 10
echo "[10] sudoers"
hr
for f in /etc/sudoers.d/mmdvm-push-web /etc/sudoers.d/pistar-dashboard; do
    if [ -f "$f" ]; then
        visudo -cf "$f" >/dev/null 2>&1 && ok "$f 语法有效" || err "$f 语法错误"
    else
        warn "$f 不存在"
    fi
done

# The web panel collects health data as mmdvm-push; without this rule it silently
# falls back to the www-data perspective and shows false alarms.
# 面板以 mmdvm-push 身份取健康数据；缺这条规则会静默退回 www-data 视角并显示假告警。
# Do NOT nest sudo here: the sudoers policy grants www-data the python3 rule,
# not permission to invoke /usr/bin/sudo itself. The nested check would fail
# even when the panel works. Inspect the effective rule file instead.
# 不要嵌套 sudo：sudoers 只授权 www-data 运行 python3，并未授权运行 sudo 本身，
# 嵌套检查会对着正确配置误报失败。直接检查生效的规则文件。
if grep -qF "(mmdvm-push) NOPASSWD: /usr/bin/python3 $INSTALL_DIR/mmdvm_push.py --health" \
        /etc/sudoers.d/mmdvm-push-web /etc/sudoers 2>/dev/null; then
    ok "Web 面板可以服务用户身份采集健康数据"
else
    warn "Web 面板无法以 mmdvm-push 运行 --health（将退回 www-data 视角，建议重跑 update.sh）"
fi

echo ""
echo "=========================================="
echo " 诊断完成"
echo " 如需反馈问题，请附上本输出（注意隐去 Token）"
echo "=========================================="
