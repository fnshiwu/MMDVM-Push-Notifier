#!/bin/bash
# MMDVM-Push-Notifier installer
# Target: Pi-Star 4.2.x (Bullseye) / 4.3.x (Bookworm) - MMDVMHost
# 安装脚本：自动识别 Pi-Star / Debian 版本，配置最小权限、systemd、Web 管理页
set -o pipefail

if [ "$EUID" -ne 0 ]; then
    echo "请使用 sudo 运行此脚本: sudo bash install.sh"
    exit 1
fi

RED=$'\033[31m'; GRN=$'\033[32m'; YLW=$'\033[33m'; NC=$'\033[0m'
ok()   { echo "${GRN}✓${NC} $*"; }
warn() { echo "${YLW}⚠${NC} $*"; }
err()  { echo "${RED}✗${NC} $*"; }

# =========================
# Version detection | 版本检测
# =========================
PISTAR_VER="unknown"
if [ -f /etc/pistar-release ]; then
    PISTAR_VER=$(grep -oP 'Version=\K[^ ]+' /etc/pistar-release 2>/dev/null || echo "unknown")
fi
DEBIAN_VER=$(cat /etc/debian_version 2>/dev/null || echo "unknown")
PY_VER=$(python3 --version 2>&1 || echo "python3 missing")
PHP_VER=$(php -r 'echo PHP_VERSION;' 2>/dev/null || echo "php missing")

echo "=========================================="
echo " MMDVM-Push-Notifier Installer"
echo " Pi-Star : $PISTAR_VER"
echo " Debian  : $DEBIAN_VER"
echo " Python  : $PY_VER"
echo " PHP     : $PHP_VER"
echo "=========================================="

# =========================
# 1) Read-write root | 切换根分区读写
# =========================
echo "1. 申请磁盘写入权限..."
mount -o remount,rw / 2>/dev/null
for cmd_path in /usr/local/sbin/rpi-rw /usr/local/bin/rpi-rw /usr/bin/rpi-rw; do
    [ -x "$cmd_path" ] && { "$cmd_path"; break; }
done
mount -o remount,size=32M /run 2>/dev/null

# =========================
# 2) Directories, user, groups | 目录、服务用户、权限组
# =========================
echo "2. 创建目录与服务用户..."
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
INSTALL_DIR="/home/pi-star/MMDVM-Push-Notifier"

mkdir -p "$INSTALL_DIR"
# If installing from another checkout, copy the files over | 支持从其他目录安装
if [ "$SCRIPT_DIR" != "$INSTALL_DIR" ]; then
    cp -f "$SCRIPT_DIR"/*.py "$SCRIPT_DIR"/*.sh "$SCRIPT_DIR"/*.php "$SCRIPT_DIR"/*.service "$INSTALL_DIR"/ 2>/dev/null
    [ -d "$SCRIPT_DIR/tests" ] && cp -rf "$SCRIPT_DIR/tests" "$INSTALL_DIR"/ 2>/dev/null
fi
cd "$INSTALL_DIR" || { err "无法进入 $INSTALL_DIR"; exit 1; }

if ! id -u mmdvm-push >/dev/null 2>&1; then
    useradd -r -s /usr/sbin/nologin -U mmdvm-push || { err "创建服务用户失败"; exit 1; }
fi

# The service user MUST be able to read /var/log/pi-star | 必须能读日志目录
for grp in www-data pi-star adm; do
    if getent group "$grp" >/dev/null 2>&1; then
        usermod -a -G "$grp" mmdvm-push
        ok "服务用户已加入 $grp 组"
    fi
done

chown -R mmdvm-push:mmdvm-push "$INSTALL_DIR"
chmod -R 755 "$INSTALL_DIR"

# =========================
# 3) Required files | 必要文件检查
# =========================
echo "3. 检查必要文件..."
REQ_FILES="mmdvm_push.py parser.py filters.py notify_fmt.py identity.py hardware.py notifier.py config.py alerts.py push_admin.php mmdvm_push.service"
MISSING=""
for f in $REQ_FILES; do
    [ -f "$f" ] || MISSING="$MISSING $f"
done
if [ -n "$MISSING" ]; then
    err "缺少必要文件:$MISSING"
    exit 1
fi
ok "文件完整"

# =========================
# 4) Python syntax check | 语法检查（提前暴露问题）
# =========================
echo "4. 检查 Python 语法..."
for f in *.py; do
    if ! python3 -m py_compile "$f" 2>/tmp/mmdvm_compile.err; then
        err "$f 语法错误:"
        cat /tmp/mmdvm_compile.err
        exit 1
    fi
done
rm -rf "$INSTALL_DIR/__pycache__"
ok "Python 语法正常"

# =========================
# 5) Config | 配置文件
# =========================
echo "5. 初始化配置文件..."
CONFIG_FILE="/etc/mmdvm_push.json"
if [ ! -f "$CONFIG_FILE" ]; then
    cat > "$CONFIG_FILE" <<'EOF'
{
  "my_callsign": "",
  "min_duration": 5.0,
  "ui_lang": "cn",
  "ignore_list": "",
  "focus_list": "",
  "log_dir": ""
}
EOF
    ok "已创建默认配置"
else
    ok "保留现有配置"
fi
chown mmdvm-push:www-data "$CONFIG_FILE" 2>/dev/null || chown mmdvm-push:mmdvm-push "$CONFIG_FILE"
chmod 664 "$CONFIG_FILE"

# =========================
# 6) Log directories | 日志目录权限
# =========================
echo "6. 检查日志目录权限..."
if [ -d /var/log/pi-star ]; then
    chmod 755 /var/log/pi-star 2>/dev/null
    # Pre-create the app log with the service owner: the directory itself stays
    # root-owned (0755) on Pi-Star, but the file must be writable by mmdvm-push.
    touch /var/log/pi-star/mmdvm_push.log 2>/dev/null
    chown mmdvm-push:mmdvm-push /var/log/pi-star/mmdvm_push.log 2>/dev/null
    chmod 664 /var/log/pi-star/mmdvm_push.log 2>/dev/null
    if sudo -u mmdvm-push test -r /var/log/pi-star 2>/dev/null; then
        ok "服务用户可读 /var/log/pi-star"
    else
        warn "服务用户无法读取 /var/log/pi-star，已尝试加入 pi-star 组，如仍失败请检查目录权限"
    fi
    LATEST_LOG=$(ls -t /var/log/pi-star/MMDVM-*.log 2>/dev/null | head -1)
    if [ -n "$LATEST_LOG" ]; then
        ok "发现 MMDVM 日志: $LATEST_LOG"
    else
        warn "暂未发现 MMDVM-*.log（MMDVMHost 尚未写入或日志路径不同）"
    fi
else
    warn "/var/log/pi-star 不存在，请确认 MMDVMHost 已安装"
fi

# =========================
# 7) Web admin | 部署 Web 管理页
# =========================
echo "7. 部署 Web 管理页面..."
WEB_ROOTS=""
for root in /var/www/dashboard /var/www/html /var/www; do
    [ -d "$root" ] && WEB_ROOTS="$WEB_ROOTS $root"
done
if [ -z "$WEB_ROOTS" ]; then
    warn "未找到 Web 根目录，跳过 Web 部署"
else
    for root in $WEB_ROOTS; do
        mkdir -p "$root/admin" 2>/dev/null
        ln -sf "$INSTALL_DIR/push_admin.php" "$root/admin/push_admin.php"
        ln -sf "$INSTALL_DIR/push_admin.php" "$root/push_admin.php" 2>/dev/null
        ok "已链接 $root/admin/push_admin.php"
    done
fi
chown www-data:www-data "$INSTALL_DIR/push_admin.php" 2>/dev/null
chmod 644 "$INSTALL_DIR/push_admin.php"

# Add a menu entry without breaking the dashboard | 谨慎注入导航链接
ADMIN_INDEX="/var/www/dashboard/admin/index.php"
if [ -f "$ADMIN_INDEX" ]; then
    cp "$ADMIN_INDEX" "$ADMIN_INDEX.bak_pushnav" 2>/dev/null
    python3 - "$ADMIN_INDEX" <<'PY'
import io, re, sys
path = sys.argv[1]
try:
    with io.open(path, "r", encoding="utf-8", errors="ignore") as fh:
        lines = fh.readlines()
except OSError:
    sys.exit(0)
if any("push_admin.php" in ln for ln in lines):
    print("  (导航链接已存在，跳过)")
    sys.exit(0)
pattern = re.compile(r'^\s*(echo\s|print\s)')
anchor = None
for i, ln in enumerate(lines):
    if pattern.match(ln) and re.search(r'href=\\?["\'](update|power|config)\.php', ln):
        anchor = i
        break
if anchor is None:
    print("  (未找到可注入位置，请手动添加导航链接)")
    sys.exit(0)
lines.insert(anchor + 1, 'echo \' <a href="/admin/push_admin.php" style="color: #ffffff;">\u63a8\u9001\u8bbe\u7f6e</a> |\'."\\n";\n')
try:
    with io.open(path, "w", encoding="utf-8") as fh:
        fh.writelines(lines)
    print("  (导航链接已注入)")
except OSError as exc:
    print("  (写入失败: %s)".format(exc))
PY
    chown www-data:www-data "$ADMIN_INDEX" 2>/dev/null
    chmod 664 "$ADMIN_INDEX" 2>/dev/null
fi

# =========================
# 8) sudoers | Web 端免密控制
# =========================
echo "8. 配置 Web 端 sudoers..."
SUDO_D="/etc/sudoers.d/mmdvm-push-web"
cat > "$SUDO_D" <<EOF
# MMDVM-Push-Notifier - web admin privileges (Pi-Star 4.2.x - 4.3.x)
www-data ALL=(ALL) NOPASSWD: /bin/systemctl start mmdvm_push.service, /bin/systemctl stop mmdvm_push.service, /bin/systemctl restart mmdvm_push.service, /bin/systemctl status mmdvm_push.service, /bin/systemctl is-active mmdvm_push.service, /bin/systemctl is-enabled mmdvm_push.service
www-data ALL=(ALL) NOPASSWD: /usr/bin/systemctl start mmdvm_push.service, /usr/bin/systemctl stop mmdvm_push.service, /usr/bin/systemctl restart mmdvm_push.service, /usr/bin/systemctl status mmdvm_push.service, /usr/bin/systemctl is-active mmdvm_push.service, /usr/bin/systemctl is-enabled mmdvm_push.service
www-data ALL=(ALL) NOPASSWD: /usr/local/sbin/rpi-rw, /usr/local/sbin/rpi-ro, /usr/local/bin/rpi-rw, /usr/local/bin/rpi-ro, /usr/bin/rpi-rw, /usr/bin/rpi-ro
www-data ALL=(ALL) NOPASSWD: /bin/mount -o remount,rw /, /bin/mount -o remount,ro /
www-data ALL=(ALL) NOPASSWD: /usr/bin/python3 $INSTALL_DIR/mmdvm_push.py
www-data ALL=(ALL) NOPASSWD: $INSTALL_DIR/update.sh
EOF
chmod 440 "$SUDO_D"
if visudo -cf "$SUDO_D" >/dev/null 2>&1; then
    ok "sudoers 校验通过"
else
    err "sudoers 校验失败，已移除该文件"
    rm -f "$SUDO_D"
fi

# =========================
# 9) systemd | 服务安装
# =========================
echo "9. 安装 systemd 服务..."
install -m 644 "$INSTALL_DIR/mmdvm_push.service" /etc/systemd/system/mmdvm_push.service
systemctl daemon-reload
systemctl enable mmdvm_push.service >/dev/null 2>&1
systemctl restart mmdvm_push.service
sleep 2

if systemctl is-active --quiet mmdvm_push.service; then
    ok "服务已启动"
else
    err "服务启动失败，最近日志如下："
    journalctl -u mmdvm_push.service -n 20 --no-pager 2>/dev/null || true
    echo "也可查看: /var/log/pi-star/mmdvm_push.log"
fi

chmod +x "$INSTALL_DIR/update.sh" "$INSTALL_DIR/uninstall.sh" "$INSTALL_DIR/diagnose.sh" 2>/dev/null

# =========================
# 10) Summary | 安装汇总
# =========================
ACTUAL_VER=$(python3 "$INSTALL_DIR/mmdvm_push.py" --version 2>/dev/null || echo "unknown")
IPADDR=$(hostname -I 2>/dev/null | awk '{print $1}')

echo "--------------------------------------------------------"
echo "✅ 安装完成 ($ACTUAL_VER)"
echo "--------------------------------------------------------"
echo "🌐 Web 管理:  http://$IPADDR/admin/push_admin.php"
echo "⚙️  配置文件:  $CONFIG_FILE"
echo "📂 运行日志:  /var/log/pi-star/mmdvm_push.log"
echo "🧪 测试推送:  sudo python3 $INSTALL_DIR/mmdvm_push.py --test"
echo "🩺 健康检查:  sudo python3 $INSTALL_DIR/mmdvm_push.py --health"
echo "🔍 一键诊断:  cd $INSTALL_DIR && sudo bash diagnose.sh"
echo "--------------------------------------------------------"

HEALTH=$(python3 "$INSTALL_DIR/mmdvm_push.py" --health 2>/dev/null)
[ -n "$HEALTH" ] && echo "健康状态: $HEALTH"

# Restore read-only root if the helper exists | 恢复只读根分区
for cmd_path in /usr/local/sbin/rpi-ro /usr/local/bin/rpi-ro /usr/bin/rpi-ro; do
    [ -x "$cmd_path" ] && { "$cmd_path"; break; }
done
exit 0
