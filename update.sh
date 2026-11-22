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

echo "--- MMDVM-Push-Notifier 更新流程开始 ---"

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

# Restore read-only root on EVERY exit path (including early failures such as
# a failed git sync or syntax check), not only on the success path at the end.
# 任何退出路径（含中途失败）都恢复只读根分区，避免把 Pi-Star 留在 rw 状态。
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
mkdir -p "$BACKUP_DIR"
cp -f ./*.py ./*.sh ./*.php ./*.service "$BACKUP_DIR"/ 2>/dev/null
ok "旧版本已备份到 $BACKUP_DIR"

# =========================
# 3) Git sync | 同步代码
# =========================
if [ -d .git ]; then
    git config --global --add safe.directory "$INSTALL_DIR" 2>/dev/null
    echo "正在拉取 origin/$BRANCH ..."
    if git fetch --all --prune 2>/dev/null && git reset --hard "origin/$BRANCH" 2>/dev/null; then
        ok "已同步到 $(git rev-parse --short HEAD)"
    else
        err "git 同步失败（请检查网络 / DNS / 代理），旧代码保持不动"
        exit 1
    fi
else
    warn "当前目录不是 git 仓库，跳过代码同步（仅刷新权限与服务）"
fi

# =========================
# 4) Integrity + syntax | 完整性与语法检查
# =========================
REQ_FILES="mmdvm_push.py parser.py filters.py notify_fmt.py identity.py hardware.py notifier.py config.py alerts.py push_admin.php mmdvm_push.service"
MISSING=""
for f in $REQ_FILES; do
    [ -f "$f" ] || MISSING="$MISSING $f"
done
if [ -n "$MISSING" ]; then
    err "缺少必要文件:$MISSING（将回滚）"
    cp -f "$BACKUP_DIR"/*.py "$BACKUP_DIR"/*.sh "$BACKUP_DIR"/*.php "$INSTALL_DIR"/ 2>/dev/null
    exit 1
fi

for f in ./*.py; do
    if ! python3 -m py_compile "$f" 2>/tmp/mmdvm_compile.err; then
        err "$f 语法错误，回滚旧版本:"
        cat /tmp/mmdvm_compile.err
        cp -f "$BACKUP_DIR"/*.py "$INSTALL_DIR"/ 2>/dev/null
        systemctl restart mmdvm_push.service
        exit 1
    fi
done
rm -rf "$INSTALL_DIR/__pycache__"
ok "代码完整且语法正常"

# =========================
# 5) User / groups / ownership | 用户、组、属主
# =========================
id -u mmdvm-push >/dev/null 2>&1 || useradd -r -s /usr/sbin/nologin -U mmdvm-push
for grp in www-data pi-star adm; do
    getent group "$grp" >/dev/null 2>&1 && usermod -a -G "$grp" mmdvm-push
done
chown -R mmdvm-push:mmdvm-push "$INSTALL_DIR"

# =========================
# 6) Service unit | 服务单元
# =========================
install -m 644 "$INSTALL_DIR/mmdvm_push.service" /etc/systemd/system/mmdvm_push.service
mount -o remount,size=32M /run 2>/dev/null
systemctl daemon-reload
ok "systemd 单元已刷新"

# =========================
# 7) Config permissions | 配置权限
# =========================
CONFIG_FILE="/etc/mmdvm_push.json"
if [ -f "$CONFIG_FILE" ]; then
    chown mmdvm-push:www-data "$CONFIG_FILE" 2>/dev/null || chown mmdvm-push:mmdvm-push "$CONFIG_FILE"
    chmod 664 "$CONFIG_FILE"
    ok "配置权限已修正 (664)"
else
    warn "配置文件不存在，将由服务自动使用默认值"
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
fi

# =========================
# 8) sudoers refresh | 刷新 sudoers
# =========================
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
visudo -cf "$SUDO_D" >/dev/null 2>&1 && ok "sudoers 校验通过" || { warn "sudoers 校验失败，移除"; rm -f "$SUDO_D"; }

chmod +x "$INSTALL_DIR"/*.sh 2>/dev/null

# =========================
# 9) Restart + status | 重启并检查
# =========================
echo "正在重启服务..."
systemctl restart mmdvm_push.service
sleep 2

ACTUAL_VER=$(python3 "$INSTALL_DIR/mmdvm_push.py" --version 2>/dev/null || echo "unknown")
if systemctl is-active --quiet mmdvm_push.service; then
    ok "服务运行中 ($ACTUAL_VER)"
else
    err "服务未运行，最近 20 行日志："
    journalctl -u mmdvm_push.service -n 20 --no-pager 2>/dev/null
    [ -f /var/log/pi-star/mmdvm_push.log ] && tail -20 /var/log/pi-star/mmdvm_push.log
fi

# =========================
# 10) Health | 健康状态
# =========================
HEALTH=$(python3 "$INSTALL_DIR/mmdvm_push.py" --health 2>/dev/null)
[ -n "$HEALTH" ] && echo "健康状态: $HEALTH"
echo "--- 更新完成 ($ACTUAL_VER) ---"

# Root filesystem is restored to read-only by the EXIT trap above | 由 EXIT trap 统一恢复只读
exit 0
