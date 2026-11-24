#!/bin/bash
# MMDVM-Push-Notifier updater
# Pulls the latest code (config is preserved), refreshes service + sudoers, restarts.
# 一键更新：拉取最新代码、保留配置、刷新服务与权限、重启并输出健康状态
set -o pipefail

RED=$'\033[31m'; GRN=$'\033[32m'; YLW=$'\033[33m'; NC=$'\033[0m'
ok()   { echo "${GRN}✓${NC} $*"; }
warn() { echo "${YLW}⚠${NC} $*"; }
err()  { echo "${RED}✗${NC} $*"; }

INSTALL_DIR="/home/pi-star/MMDVM-Push-Notifier"
BRANCH="${MMDVM_PUSH_BRANCH:-main}"
BACKUP_DIR="/home/pi-star/mmdvm-push-backup-$(date +%Y%m%d-%H%M%S)"
CONFIG_FILE="/etc/mmdvm_push.json"
SUDO_D="/etc/sudoers.d/mmdvm-push-web"
SERVICE="mmdvm_push.service"

echo "--- MMDVM-Push-Notifier 更新流程开始 ---"

if [ "$EUID" -ne 0 ]; then
    err "请使用 sudo 运行: sudo bash update.sh"
    exit 1
fi

# =========================
# 1) Read-write root | 切换读写
# =========================
ROOT_RW_BY_US=0
if mount -o remount,rw / 2>/dev/null; then
    ROOT_RW_BY_US=1
fi
for cmd_path in /usr/local/sbin/rpi-rw /usr/local/bin/rpi-rw /usr/bin/rpi-rw; do
    [ -x "$cmd_path" ] && { "$cmd_path"; break; }
done

# Restore read-only root on EVERY exit path (including a failed git sync or a
# syntax check), not only on the success path at the end.
# 任何退出路径都恢复只读根分区（含 git 同步/语法检查失败），不留 rw 状态。
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

cd "$INSTALL_DIR" || { err "无法进入 $INSTALL_DIR"; exit 1; }

# =========================
# 2) Backup current code | 备份当前代码
# =========================
mkdir -p "$BACKUP_DIR" || { err "无法创建备份目录 $BACKUP_DIR"; exit 1; }
if cp -f ./*.py ./*.sh ./*.php ./*.service "$BACKUP_DIR"/ 2>/dev/null; then
    ok "旧版本已备份到 $BACKUP_DIR"
else
    warn "部分文件备份失败，继续（git 回滚仍可用）"
fi

# =========================
# 3) Git sync | 同步代码
# =========================
PREV_SHA=""
IS_GIT=0
if [ -d .git ]; then
    IS_GIT=1
    git config --global --add safe.directory "$INSTALL_DIR" 2>/dev/null
    PREV_SHA=$(git rev-parse HEAD 2>/dev/null)
    if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
        warn "工作区有本地改动，将被 git reset 丢弃（备份在 $BACKUP_DIR）"
    fi
    echo "正在拉取 origin/$BRANCH ..."
    if git fetch --all --prune 2>/dev/null && git reset --hard "origin/$BRANCH" 2>/dev/null; then
        ok "已同步到 $(git rev-parse --short HEAD)（原版本 ${PREV_SHA:0:7}）"
    else
        err "git 同步失败（请检查网络 / DNS / 代理），旧代码保持不动"
        exit 1
    fi
else
    warn "当前目录不是 git 仓库，跳过代码同步（仅刷新权限与服务）"
fi

# =========================
# Rollback helpers | 回滚
# =========================
ROLLED_BACK=0
restore_from_backup() {
    cp -f "$BACKUP_DIR"/*.py "$INSTALL_DIR"/ 2>/dev/null
    cp -f "$BACKUP_DIR"/*.sh "$INSTALL_DIR"/ 2>/dev/null
    cp -f "$BACKUP_DIR"/*.php "$INSTALL_DIR"/ 2>/dev/null
    cp -f "$BACKUP_DIR"/*.service "$INSTALL_DIR"/ 2>/dev/null
    warn "已从 $BACKUP_DIR 恢复文件"
}

# Roll back the whole tree, not just the *.py files: a half-new/half-old checkout
# is worse than the old version. git reset also keeps .git consistent so the next
# update does not silently restore the broken commit.
# 整体回滚而不是只回滚 *.py：半新半旧比旧版更糟，git reset 还能让下次更新不再次被带回坏版本。
rollback() {
    [ "$ROLLED_BACK" -eq 1 ] && return
    ROLLED_BACK=1
    err "$1"
    if [ "$IS_GIT" -eq 1 ] && [ -n "$PREV_SHA" ]; then
        if git reset --hard "$PREV_SHA" >/dev/null 2>&1; then
            ok "已回滚到 ${PREV_SHA:0:7}（git reset --hard）"
        else
            warn "git 回滚失败，改用备份文件"
            restore_from_backup
        fi
    else
        restore_from_backup
    fi
    systemctl restart "$SERVICE" >/dev/null 2>&1
}

# =========================
# 4) Integrity + syntax | 完整性与语法检查
# =========================
REQ_FILES="mmdvm_push.py parser.py filters.py notify_fmt.py identity.py hardware.py notifier.py config.py alerts.py push_admin.php mmdvm_push.service"
MISSING=""
for f in $REQ_FILES; do
    [ -f "$f" ] || MISSING="$MISSING $f"
done
if [ -n "$MISSING" ]; then
    rollback "缺少必要文件:$MISSING"
    exit 1
fi

for f in ./*.py; do
    if ! python3 -m py_compile "$f" 2>/tmp/mmdvm_compile.err; then
        cat /tmp/mmdvm_compile.err
        rollback "$f 语法错误"
        exit 1
    fi
done
rm -rf "$INSTALL_DIR/__pycache__"
ok "代码完整且语法正常"

# =========================
# 5) User / groups / ownership | 用户、组、属主
# =========================
if ! id -u mmdvm-push >/dev/null 2>&1; then
    if useradd -r -s /usr/sbin/nologin -U mmdvm-push; then
        ok "已创建服务用户 mmdvm-push"
    else
        err "创建服务用户失败"
        exit 1
    fi
fi

# Only the groups needed to read the MMDVM logs; www-data is NOT required and
# would widen the service account for no reason.
# 仅加入读取 MMDVM 日志所需的组；不需要 www-data，加了只是无谓扩权。
for grp in pi-star adm; do
    if getent group "$grp" >/dev/null 2>&1; then
        if usermod -a -G "$grp" mmdvm-push; then
            ok "服务用户已加入 $grp 组"
        else
            warn "加入 $grp 组失败（日志可能读不到）"
        fi
    fi
done

if chown -R mmdvm-push:mmdvm-push "$INSTALL_DIR"; then
    ok "安装目录属主已修正"
else
    warn "安装目录属主修正失败"
fi

# =========================
# 6) Service unit | 服务单元
# =========================
if install -m 644 "$INSTALL_DIR/mmdvm_push.service" "/etc/systemd/system/$SERVICE"; then
    mount -o remount,size=32M /run 2>/dev/null
    systemctl daemon-reload || warn "daemon-reload 失败"
    ok "systemd 单元已刷新"
else
    rollback "systemd 单元安装失败"
    exit 1
fi

# =========================
# 7) Config permissions | 配置权限
# =========================
if [ -f "$CONFIG_FILE" ]; then
    chown mmdvm-push:www-data "$CONFIG_FILE" 2>/dev/null || chown mmdvm-push:mmdvm-push "$CONFIG_FILE"
    chmod 664 "$CONFIG_FILE"
    ok "配置权限已修正 (664)"
else
    warn "配置文件不存在，将写入默认值"
    echo '{"my_callsign":"","min_duration":5.0,"ui_lang":"cn","log_dir":""}' > "$CONFIG_FILE"
    chown mmdvm-push:www-data "$CONFIG_FILE" 2>/dev/null
    chmod 664 "$CONFIG_FILE"
fi

# =========================
# 7.5) App log ownership | 运行日志属主（目录属 root 也能写）
# =========================
if [ -d /var/log/pi-star ]; then
    touch /var/log/pi-star/mmdvm_push.log 2>/dev/null
    chown mmdvm-push:mmdvm-push /var/log/pi-star/mmdvm_push.log 2>/dev/null
    chmod 664 /var/log/pi-star/mmdvm_push.log 2>/dev/null
    if sudo -u mmdvm-push test -w /var/log/pi-star/mmdvm_push.log 2>/dev/null; then
        ok "服务用户可写运行日志"
    else
        warn "服务用户仍无法写 /var/log/pi-star/mmdvm_push.log，运行日志可能落到 /tmp"
    fi
fi

# =========================
# 8) sudoers refresh | 刷新 sudoers
# =========================
# NOTE: the python3 rules are scoped to (mmdvm-push) and to an explicit argument,
# so the web server can read the service's own view of the world without gaining
# a blanket "run this script as root" right.
# 注意：python3 规则限定为以 mmdvm-push 身份、且必须带明确参数，Web 端因此能拿到
# 服务自身的视角，却不会获得“以 root 任意运行该脚本”的权限。
cat > "$SUDO_D" <<EOF
# MMDVM-Push-Notifier - web admin privileges (Pi-Star 4.2.x - 4.3.x)
www-data ALL=(root) NOPASSWD: /bin/systemctl start $SERVICE, /bin/systemctl stop $SERVICE, /bin/systemctl restart $SERVICE, /bin/systemctl status $SERVICE, /bin/systemctl is-active $SERVICE, /bin/systemctl is-enabled $SERVICE
www-data ALL=(root) NOPASSWD: /usr/bin/systemctl start $SERVICE, /usr/bin/systemctl stop $SERVICE, /usr/bin/systemctl restart $SERVICE, /usr/bin/systemctl status $SERVICE, /usr/bin/systemctl is-active $SERVICE, /usr/bin/systemctl is-enabled $SERVICE
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
    warn "sudoers 校验失败，已移除该文件"
    rm -f "$SUDO_D"
fi

chmod +x "$INSTALL_DIR"/*.sh 2>/dev/null

# =========================
# 8.6) Time synchronisation | 系统时间同步
# =========================
# Cold boot without NTP produces a stale clock, and Feishu rejects signed
# pushes with code 19021. Enable NTP non-fatally on every update.
# 冷启动无 NTP 会导致时钟过期，飞书以 19021 拒绝签名推送。每次更新幂等启用。
if command -v timedatectl >/dev/null 2>&1; then
    timedatectl set-ntp true 2>/dev/null || true
fi
if [ -d /run/systemd/system ]; then
    systemctl enable --now systemd-timesyncd.service >/dev/null 2>&1 || true
fi
if command -v timedatectl >/dev/null 2>&1; then
    SYNC_STATE=$(timedatectl show -p SystemClockSynchronized --value 2>/dev/null || echo "unknown")
    if [ "$SYNC_STATE" = "yes" ]; then
        ok "系统时钟已同步"
    else
        warn "系统时钟尚未同步；启动推送会等待校时并用服务器时间重签"
    fi
fi

# =========================
# 9) Restart + status | 重启并检查
# =========================
echo "正在重启服务..."
systemctl restart "$SERVICE"
sleep 2

ACTUAL_VER=$(python3 "$INSTALL_DIR/mmdvm_push.py" --version 2>/dev/null || echo "unknown")
if systemctl is-active --quiet "$SERVICE"; then
    ok "服务运行中 ($ACTUAL_VER)"
else
    err "服务未运行，最近 20 行日志："
    journalctl -u "$SERVICE" -n 20 --no-pager 2>/dev/null
    [ -f /var/log/pi-star/mmdvm_push.log ] && tail -20 /var/log/pi-star/mmdvm_push.log
fi

# =========================
# 10) Health | 健康状态
# =========================
HEALTH=$(sudo -u mmdvm-push python3 "$INSTALL_DIR/mmdvm_push.py" --health 2>/dev/null)
[ -n "$HEALTH" ] && echo "健康状态: $HEALTH"
echo "--- 更新完成 ($ACTUAL_VER) ---"

# Root filesystem is restored to read-only by the EXIT trap above | 由 EXIT trap 统一恢复只读
exit 0
