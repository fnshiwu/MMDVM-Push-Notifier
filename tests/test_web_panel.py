import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "push_admin.php"


class TestWebPanelSudoUsage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = PANEL.read_text(encoding="utf-8")

    def test_sudo_helper_is_non_interactive(self):
        self.assertIn("return 'sudo -n ' . $args;", self.source)

    def test_no_bare_sudo_commands(self):
        # Every sudo invocation must go through sudo_cmd(); a plain `sudo`
        # wait for a password on a TTY that PHP will never have.
        bare = re.findall(
            r"(?:shell_exec|exec)\(\s*['\"]sudo\s",
            self.source,
        )
        self.assertEqual(bare, [], "found sudo call without -n")

    def test_test_action_runs_as_service_user(self):
        self.assertIn(
            "sudo_cmd('-u ' . escapeshellarg($serviceUser)",
            self.source,
        )
        self.assertIn("$sudoProblem", self.source)

    def test_test_action_does_not_fall_back_to_www_data(self):
        # A fallback would report a result that does not reflect the daemon.
        block = self.source[self.source.index("} elseif ($action === 'test')"):]
        block = block[:block.index("\n    }", 10)]
        self.assertNotIn("/usr/bin/python3 ' . escapeshellarg($scriptPath)", block)

    def test_mount_uses_absolute_path(self):
        # On usrmerged Bookworm `mount` resolves to /usr/bin/mount; a relative
        # command would not match the /bin/mount sudoers rule.
        self.assertIn('sudo_cmd("/bin/mount -o remount,', self.source)

    def test_sudoers_covers_both_mount_paths(self):
        for script in ("install.sh", "update.sh"):
            body = (ROOT / script).read_text(encoding="utf-8")
            self.assertIn("/bin/mount -o remount\\,rw /", body)
            self.assertIn("/usr/bin/mount -o remount\\,rw /", body)

    def test_sudoers_commas_are_escaped(self):
        # sudoers uses commas as command separators; `remount,rw` must be
        # written as `remount\\,rw` or the whole file fails to parse and sudo
        # refuses every command with a caret error.
        for script in ("install.sh", "update.sh"):
            body = (ROOT / script).read_text(encoding="utf-8")
            for line in body.splitlines():
                if "NOPASSWD:" in line and "mount" in line:
                    self.assertNotIn("remount,rw", line)
                    self.assertNotIn("remount,ro", line)
                    self.assertIn("remount\\,rw", line)
                    self.assertIn("remount\\,ro", line)

    def test_diagnose_does_not_nest_sudo(self):
        # sudoers grants www-data the python3 rule only, not the right to
        # invoke /usr/bin/sudo; a nested check always reports a false failure.
        body = (ROOT / "diagnose.sh").read_text(encoding="utf-8")
        self.assertNotIn("sudo -u www-data sudo", body)
        self.assertIn("grep -qF \"(mmdvm-push) NOPASSWD: /usr/bin/python3", body)

    def test_diagnose_failure_count_is_a_single_integer(self):
        body = (ROOT / "diagnose.sh").read_text(encoding="utf-8")
        self.assertNotIn('grep -ac "PUSH_FAILED" "$APP_LOG" 2>/dev/null || echo 0', body)

    def test_installer_injects_into_real_dashboard_index(self):
        body = (ROOT / "install.sh").read_text(encoding="utf-8")
        self.assertIn("/var/www/dashboard/index.php", body)
        self.assertNotIn('ADMIN_INDEX="/var/www/dashboard/admin/index.php"', body)
        self.assertIn("/admin/(?:update|power|configure)\\.php", body)
        self.assertIn("in_php_comment", body)


class TestMenuInjection(unittest.TestCase):
    def test_anchor_inside_php_comment_is_ignored(self):
        # A docblock line that merely mentions configure.php used to be picked
        # as the anchor, so the generated echo was commented out and no button
        # ever appeared. Run the exact heredoc from install.sh to prove it skips
        # comment lines and repairs a stale injection.
        import subprocess
        import sys
        import tempfile

        body = (ROOT / "install.sh").read_text(encoding="utf-8")
        block = body.split("python3 - $ADMIN_INDEXES <<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
        with tempfile.TemporaryDirectory() as tmp:
            page = Path(tmp) / "index.php"
            page.write_text(
                '<?php\n'
                '/*\n'
                ' * redirect to /admin/configure.php.\n'
                'echo \' <a href="/admin/push_admin.php">old</a> |\'."\\n";\n'
                '*/\n'
                '?>\n'
                '<a href="/admin/configure.php">Configuration</a>\n',
                encoding="utf-8",
            )
            proc = subprocess.run(
                [sys.executable, "-", str(page)],
                input=block,
                text=True,
                capture_output=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            patched = page.read_text(encoding="utf-8")
            self.assertIn(
                '<a href="/admin/push_admin.php" style="color: #ffffff;">推送设置</a>'
                ' | <a href="/admin/configure.php">',
                patched,
            )
            self.assertNotIn('echo \' <a href="/admin/push_admin.php">old', patched)

    def test_echo_anchor_does_not_splice_statement_into_string(self):
        # The most common menu style is a single PHP echo containing several
        # links. If the injected echo lands at the anchor COLUMN instead of the
        # line start, it is spliced inside the string literal and produces a
        # PHP parse error -> HTTP 500 for the whole dashboard.
        import subprocess
        import sys
        import tempfile

        body = (ROOT / "install.sh").read_text(encoding="utf-8")
        block = body.split("python3 - $ADMIN_INDEXES <<'PY'\n", 1)[1].split("\nPY\n", 1)[0]
        with tempfile.TemporaryDirectory() as tmp:
            page = Path(tmp) / "index.php"
            page.write_text(
                '<?php\n'
                'echo \' <a href="/admin/update.php">Update</a> | '
                '<a href="/admin/configure.php">Config</a>\'."\\n";\n',
                encoding="utf-8",
            )
            proc = subprocess.run(
                [sys.executable, "-", str(page)],
                input=block, text=True, capture_output=True,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            patched = page.read_text(encoding="utf-8")
            # Our echo must be a standalone line, not embedded mid-string.
            self.assertIn(
                'echo \' <a href="/admin/push_admin.php" style="color: #ffffff;">推送设置</a> |\'."\\n";',
                patched,
            )
            self.assertIn('<a href="/admin/configure.php">Config</a>\'."\\n";', patched)
            self.assertNotIn('echo \' echo \'', patched)


class TestUninstallCleanup(unittest.TestCase):
    def test_backup_restored_before_deletion(self):
        body = (ROOT / "uninstall.sh").read_text(encoding="utf-8")
        restore = body.index('sudo cp -f "$idx.bak_pushnav" "$idx"')
        delete = body.index('sudo find /var/www -type f -name "*.bak_pushnav" -delete')
        self.assertLess(restore, delete, "backups deleted before they are restored")

    def test_uninstall_cleans_all_index_candidates(self):
        body = (ROOT / "uninstall.sh").read_text(encoding="utf-8")
        for path in ("/var/www/dashboard/index.php", "/var/www/dashboard/admin/index.php"):
            self.assertIn(path, body)


class TestTimeSyncSetup(unittest.TestCase):
    def test_install_enables_ntp(self):
        body = (ROOT / "install.sh").read_text(encoding="utf-8")
        self.assertIn("timedatectl set-ntp true", body)
        self.assertIn("systemctl enable --now systemd-timesyncd.service", body)

    def test_update_enables_ntp(self):
        body = (ROOT / "update.sh").read_text(encoding="utf-8")
        self.assertIn("timedatectl set-ntp true", body)
        self.assertIn("systemctl enable --now systemd-timesyncd.service", body)

    def test_service_waits_for_time_sync(self):
        unit = (ROOT / "mmdvm_push.service").read_text(encoding="utf-8")
        self.assertIn("After=network-online.target time-sync.target", unit)
        self.assertIn("Wants=network-online.target time-sync.target", unit)


if __name__ == "__main__":
    unittest.main()
