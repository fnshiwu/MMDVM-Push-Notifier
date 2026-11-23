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
ROOT_RW_BY_US=0
if mount -o remount,rw / 2>/dev/null; then
    ROOT_RW_BY_US=1
fi
for cmd_path in /usr/local/sbin/rpi-rw /usr/local/bin/rpi-rw /usr/bin/rpi-rw; do
    [ -x "$cmd_path" ] && { "$cmd_path"; break; }
done
mount -o remount,size=32M /run 2>/dev/null

# Restore read-only root on EVERY exit path (including early failures such as
# a missing file or a Python syntax error), not only on the success path.
# 任何退出路径都恢复只读根分区（含中途失败），避免把 Pi-Star 留在 rw 状态。
restore_root_ro() {
    trap - EXIT
    for cmd_path in /usr/local/sbin/rpi-ro /usr/local/bin/rpi-ro /usr/bin/rpi-ro; do
        if [ -x "$cmd_path" ]; then
            "$cmd_path"
            return 0
        fi
    done
    if [ "$ROOT_RW_BY_US" -eq 1 ]; then
        mount -o remount,ro / 2>/dev/null || \
            warn "无法恢复根分区只读，请手动执行: mount -o remount,ro /"
    fi
}
trap restore_root_ro EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

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
# www-data is deliberately NOT added: the daemon never needs the web server's group,
# and granting it would contradict the "least privilege" claim of this script.
# 故意不加 www-data：守护进程不需要 Web 服务器的组，加了与“最小权限”自相矛盾。
for grp in pi-star adm; do
    if getent group "$grp" >/dev/null 2>&1; then
        if usermod -a -G "$grp" mmdvm-push; then
            ok "服务用户已加入 $grp 组"
        else
            warn "加入 $grp 组失败（可能导致读不到日志）"
        fi
    fi
done

chown -R mmdvm-push:mmdvm-push "$INSTALL_DIR" || warn "安装目录属主修正失败"
chmod -R 755 "$INSTALL_DIR" || warn "安装目录权限修正失败"

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
# Pi-Star 4.3.x: admin/index.php may be a 12-byte `../index.php` stub, while the
# real menu lives in the dashboard root index.php. Different builds put the menu
# in different files, so handle every candidate. Never insert an `echo` into a
# PHP comment block: a docblock line mentioning configure.php looks like a valid
# anchor but the generated link would never be rendered.
# Pi-Star 4.3.x：真正的菜单可能在任一候选文件中；必须跳过 PHP 注释里的伪锚点，
# 否则注入的 echo 永远不执行，页面上依然看不到按钮。
ADMIN_INDEXES=""
for candidate in /var/www/dashboard/index.php /var/www/html/index.php /var/www/index.php /var/www/dashboard/admin/index.php; do
    [ -f "$candidate" ] && ADMIN_INDEXES="$ADMIN_INDEXES $candidate"
done
if [ -n "$ADMIN_INDEXES" ]; then
    for idx in $ADMIN_INDEXES; do
        cp "$idx" "$idx.bak_pushnav" 2>/dev/null
    done
    python3 - $ADMIN_INDEXES <<'PY'
import io, re, sys

LINK = '<a href="/admin/push_admin.php" style="color: #ffffff;">\u63a8\u9001\u8bbe\u7f6e</a> | '
ANCHOR = re.compile(r'<a\s+href=["\']/admin/(?:update|power|configure)\.php["\']')


def in_php_comment(text, pos):
    """Whether pos is inside a //, # or /* */ comment (not string-aware)."""
    state, i, size = 0, 0, len(text)
    while i < pos:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < size else ''
        if state == 0:
            if ch == '/' and nxt == '*':
                state, i = 2, i + 1
            elif ch == '/' and nxt == '/':
                state, i = 1, i + 1
            elif ch == '#':
                state = 1
        elif state == 1:
            if ch == '\n':
                state = 0
        elif state == 2:
            if ch == '*' and nxt == '/':
                state, i = 0, i + 1
        i += 1
    return state != 0


for path in sys.argv[1:]:
    try:
        src = io.open(path, encoding='utf-8', errors='ignore').read()
    except OSError:
        continue
    original = src
    # Undo an older injection that landed inside a docblock as a bare `echo`.
    src = ''.join(line for line in src.splitlines(True)
                  if not (line.lstrip().startswith('echo ') and 'push_admin.php' in line))
    src = src.replace(LINK, '')
    pos = next((m.start() for m in ANCHOR.finditer(src)
                if not in_php_comment(src, m.start())), None)
    if pos is None:
        continue
    line_start = src.rfind('\n', 0, pos) + 1
    line_end = src.find('\n', pos)
    anchor_line = src[line_start: line_end if line_end >= 0 else len(src)]
    if re.match(r'\s*(echo|print)\b', anchor_line):
        indent = re.match(r'\s*', anchor_line).group(0)
        insert = indent + 'echo \' <a href="/admin/push_admin.php" style="color: #ffffff;">\u63a8\u9001\u8bbe\u7f6e</a> |\'."\\n";\n'
    else:
        insert = LINK
    src = src[:pos] + insert + src[pos:]
    if src == original:
        continue
    try:
        io.open(path, 'w', encoding='utf-8').write(src)
        print('  (导航链接已注入 %s)' % path)
    except OSError as exc:
        print('  (写入失败 %s: %s)' % (path, exc))
PY
    for idx in $ADMIN_INDEXES; do
        chown www-data:www-data "$idx" 2>/dev/null
        chmod 664 "$idx" 2>/dev/null
    done
else
    warn "未找到可注入导航的 index.php，请手动添加链接"
fi

# =========================
# 8) sudoers | Web 端免密控制
# =========================
echo "8. 配置 Web 端 sudoers..."
SUDO_D="/etc/sudoers.d/mmdvm-push-web"
# The python3 rules are scoped to (mmdvm-push) + an explicit argument: the panel can
# ask the service account for its own view, without a blanket "run as root" right.
# python3 规则限定为以服务用户身份、且必须带明确参数，避免 Web 端拿到 root 执行权。
cat > "$SUDO_D" <<EOF
# MMDVM-Push-Notifier - web admin privileges (Pi-Star 4.2.x - 4.3.x)
www-data ALL=(root) NOPASSWD: /bin/systemctl start mmdvm_push.service, /bin/systemctl stop mmdvm_push.service, /bin/systemctl restart mmdvm_push.service, /bin/systemctl status mmdvm_push.service, /bin/systemctl is-active mmdvm_push.service, /bin/systemctl is-enabled mmdvm_push.service
www-data ALL=(root) NOPASSWD: /usr/bin/systemctl start mmdvm_push.service, /usr/bin/systemctl stop mmdvm_push.service, /usr/bin/systemctl restart mmdvm_push.service, /usr/bin/systemctl status mmdvm_push.service, /usr/bin/systemctl is-active mmdvm_push.service, /usr/bin/systemctl is-enabled mmdvm_push.service
www-data ALL=(root) NOPASSWD: /usr/local/sbin/rpi-rw, /usr/local/sbin/rpi-ro, /usr/local/bin/rpi-rw, /usr/local/bin/rpi-ro, /usr/bin/rpi-rw, /usr/bin/rpi-ro
www-data ALL=(root) NOPASSWD: /bin/mount -o remount\,rw /, /bin/mount -o remount\,ro /, /usr/bin/mount -o remount\,rw /, /usr/bin/mount -o remount\,ro /
www-data ALL=(mmdvm-push) NOPASSWD: /usr/bin/python3 $INSTALL_DIR/mmdvm_push.py --health
www-data ALL=(mmdvm-push) NOPASSWD: /usr/bin/python3 $INSTALL_DIR/mmdvm_push.py --test
www-data ALL=(root) NOPASSWD: $INSTALL_DIR/update.sh
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
if ! install -m 644 "$INSTALL_DIR/mmdvm_push.service" /etc/systemd/system/mmdvm_push.service; then
    err "systemd 单元安装失败"
    exit 1
fi
systemctl daemon-reload || warn "daemon-reload 失败"
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

# Root filesystem is restored to read-only by the EXIT trap above | 由 EXIT trap 统一恢复只读
exit 0
