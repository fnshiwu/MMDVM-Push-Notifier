import json
import os
import tempfile
import threading
import time
import unittest

import mmdvm_push as m
from config import ConfigManager
from notifier import PushService


def voice_line(call, target="TG 1", dur="3.4"):
    return ("M: 2026-05-01 12:00:10.000 DMR Slot 2, received RF end of voice transmission "
            f"from {call} to {target}, {dur} seconds, 0% packet loss, BER: 0.1%, RSSI: -45 dBm\n")


class FakeFuture:
    def __init__(self, value):
        self._value = value

    def result(self):
        return self._value


class TestTailAndDedup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.log = os.path.join(self.tmp, "MMDVM-2026-05-01.log")
        with open(self.log, "w", encoding="utf-8") as fh:
            fh.write("M: boot\n")

        cfg = os.path.join(self.tmp, "cfg.json")
        with open(cfg, "w", encoding="utf-8") as fh:
            json.dump({
                "my_callsign": "N0CALL",
                "min_duration": 0.1,
                "dedup_window": 0,
                "boot_push_enabled": False,
                "temp_alert_enabled": False,
                "temp_interval": 60,
            }, fh)

        self._orig = {
            "cfg": m.CONFIG_FILE,
            "running": m.RUNNING,
            "interval": m.LOG_CHECK_INTERVAL,
            "env": os.environ.get("MMDVM_LOG_DIR"),
            "send": PushService.__dict__["send"],
        }
        m.CONFIG_FILE = cfg
        m.RUNNING = True
        m.LOG_CHECK_INTERVAL = 0.05
        os.environ["MMDVM_LOG_DIR"] = self.tmp
        ConfigManager._config = {}
        ConfigManager._last_mtime = 0.0
        ConfigManager._last_check_time = 0.0

        self.sent = []
        PushService.send = staticmethod(lambda *a, **k: self.sent.append(a[1]))
        self.monitor = m.MMDVMMonitor()

    def tearDown(self):
        m.RUNNING = False
        time.sleep(0.05)
        m.CONFIG_FILE = self._orig["cfg"]
        m.RUNNING = self._orig["running"]
        m.LOG_CHECK_INTERVAL = self._orig["interval"]
        if self._orig["env"] is None:
            os.environ.pop("MMDVM_LOG_DIR", None)
        else:
            os.environ["MMDVM_LOG_DIR"] = self._orig["env"]
        PushService.send = self._orig["send"]

    def _tail_in_background(self):
        # Mirror run(): when _tail_log returns (rotation/truncation), the main
        # loop reopens the log and tails again from its end.
        def loop():
            while m.RUNNING:
                self.monitor._tail_log(self.log)
                time.sleep(0.05)
        thread = threading.Thread(target=loop, daemon=True)
        thread.start()
        time.sleep(0.25)
        return thread

    def test_appended_line_is_pushed(self):
        self._tail_in_background()
        with open(self.log, "a", encoding="utf-8") as fh:
            fh.write(voice_line("BG5ABC"))
        deadline = time.time() + 3
        while time.time() < deadline and not self.sent:
            time.sleep(0.05)
        self.assertEqual(len(self.sent), 1)
        self.assertIn("语音通联", self.sent[0])

    def test_truncation_is_detected_and_reread(self):
        """copytruncate: reopen from end, don't replay history, keep tailing new lines"""
        self._tail_in_background()
        with open(self.log, "a", encoding="utf-8") as fh:
            fh.write(voice_line("BG5ABC"))
        deadline = time.time() + 3
        while time.time() < deadline and len(self.sent) < 1:
            time.sleep(0.05)
        self.assertEqual(len(self.sent), 1)

        # Rewrite from zero with shorter content: size decreases (copytruncate).
        # The reopen-from-end path must not replay the old QSO as a new event.
        with open(self.log, "w", encoding="utf-8") as fh:
            fh.write(voice_line("JA1XYZ"))
        time.sleep(0.4)
        self.assertEqual(len(self.sent), 1, "truncated history must not be replayed")

        # Lines written AFTER the truncation must still be tailed.
        with open(self.log, "a", encoding="utf-8") as fh:
            fh.write(voice_line("BA4SMQ"))

        deadline = time.time() + 3
        while time.time() < deadline and len(self.sent) < 2:
            time.sleep(0.05)
        self.assertEqual(len(self.sent), 2, "line written after truncation must be pushed")

    def test_failed_push_releases_dedup_entry(self):
        event = {"call": "BG5ABC", "target": "TG 1", "dur": 3.0, "is_voice": True}
        key = ("BG5ABC", "TG 1")
        self.monitor._seen[key] = time.time()
        self.monitor.last_msg = {"call": "BG5ABC", "target": "TG 1", "ts": time.time()}

        self.monitor._on_push_done(FakeFuture(False), event)
        self.assertNotIn(key, self.monitor._seen)
        self.assertEqual(self.monitor.last_msg["call"], "")

    def test_successful_push_keeps_dedup_entry(self):
        event = {"call": "BG5ABC", "target": "TG 1", "dur": 3.0, "is_voice": True}
        key = ("BG5ABC", "TG 1")
        self.monitor._seen[key] = time.time()
        self.monitor._on_push_done(FakeFuture(True), event)
        self.assertIn(key, self.monitor._seen)

    def test_seen_accesses_share_the_dedup_lock(self):
        # _seen is mutated by the tail thread (should_push) and by push
        # workers (_on_push_done). Every site must hold _dedup_lock or pruning
        # can iterate a dict that another thread is popping.
        import inspect
        for method_name in ("process_line", "_on_push_done"):
            source = inspect.getsource(getattr(m.MMDVMMonitor, method_name))
            self.assertIn("with self._dedup_lock:", source, method_name)
            self.assertLess(
                source.index("with self._dedup_lock:"),
                source.index("forget_pushed" if method_name == "_on_push_done"
                             else "should_push("),
                method_name,
            )
        process = inspect.getsource(m.MMDVMMonitor.process_line)
        self.assertEqual(process.count("with self._dedup_lock:"), 3)


class TestHealthHelpers(unittest.TestCase):
    def test_recent_push_failures_counts_marker(self):
        tmp = tempfile.mkdtemp()
        original = m.APP_LOG_DIR
        m.APP_LOG_DIR = tmp
        try:
            with open(os.path.join(tmp, "mmdvm_push.log"), "w", encoding="utf-8") as fh:
                fh.write("[2026-05-01] [INFO] Push queued\n")
                fh.write("[2026-05-01] [ERROR] PUSH_FAILED channel=telegram title=语音通联\n")
                fh.write("[2026-05-01] [ERROR] PUSH_FAILED channel=feishu title=语音通联\n")
            result = m._recent_push_failures()
            self.assertEqual(result["count"], 2)
            self.assertIn("PUSH_FAILED", result["last"])
        finally:
            m.APP_LOG_DIR = original

    def test_recent_push_failures_missing_file(self):
        original = m.APP_LOG_DIR
        m.APP_LOG_DIR = os.path.join(tempfile.mkdtemp(), "nope")
        try:
            self.assertEqual(m._recent_push_failures(), {"count": 0, "last": ""})
        finally:
            m.APP_LOG_DIR = original

    def test_health_exposes_log_and_failure_fields(self):
        status = m.MMDVMMonitor().health()
        self.assertIn("app_log_file", status)
        self.assertIn("app_log_writable", status)
        self.assertIn("push_failures_recent", status)
        self.assertIn("service_user", status)
        self.assertTrue(status["parser_selftest"])


class TestClockSync(unittest.TestCase):
    """Cold boot / no RTC: wait for NTP but never block the monitor forever."""

    def test_clock_sync_wait_is_bounded_and_configurable(self):
        self.assertGreater(m.CLOCK_SYNC_WAIT, 0)
        monitor = m.MMDVMMonitor()
        original = monitor._system_clock_synced
        try:
            monitor._system_clock_synced = staticmethod(lambda: True)
            monitor._wait_for_clock_sync({})  # synced: returns immediately
            monitor._system_clock_synced = staticmethod(lambda: False)
            start = time.monotonic()
            monitor._wait_for_clock_sync({m.CLOCK_SYNC_WAIT_KEY: 0.3})
            self.assertLess(time.monotonic() - start, 2.0)
        finally:
            monitor._system_clock_synced = original

    def test_disable_clock_wait_with_zero(self):
        monitor = m.MMDVMMonitor()
        original = monitor._system_clock_synced
        try:
            calls = []
            monitor._system_clock_synced = staticmethod(lambda: calls.append(1) or False)
            monitor._wait_for_clock_sync({m.CLOCK_SYNC_WAIT_KEY: 0})
            self.assertEqual(calls, [], "zero must skip clock checks entirely")
        finally:
            monitor._system_clock_synced = original

    def test_negative_wait_is_clamped(self):
        monitor = m.MMDVMMonitor()
        original = monitor._system_clock_synced
        try:
            monitor._system_clock_synced = staticmethod(lambda: False)
            start = time.monotonic()
            monitor._wait_for_clock_sync({m.CLOCK_SYNC_WAIT_KEY: -5})
            self.assertLess(time.monotonic() - start, 1.0)
        finally:
            monitor._system_clock_synced = original


if __name__ == '__main__':
    unittest.main()
