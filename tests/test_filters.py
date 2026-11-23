import unittest
import time
from datetime import datetime, timedelta

from filters import quiet_time, should_push, forget_pushed


def hhmm(dt):
    return dt.strftime("%H:%M")


class TestFilters(unittest.TestCase):
    def test_quiet_time_active_non_wrap(self):
        now = datetime.now()
        start = hhmm(now - timedelta(minutes=5))
        end = hhmm(now + timedelta(minutes=5))
        conf = {'quiet_mode': {'enabled': True, 'start': start, 'end': end}}
        self.assertTrue(quiet_time(conf))

    def test_quiet_time_active_wrap(self):
        conf = {'quiet_mode': {'enabled': True, 'start': '23:00', 'end': '07:00'}}
        now = datetime.now()
        in_wrap = now.hour >= 23 or now.hour < 7
        self.assertEqual(quiet_time(conf), in_wrap)

    def test_should_push_focus_and_min_duration(self):
        conf = {'focus_list': 'FOO', 'ignore_list': '', 'my_callsign': 'MYCALL', 'min_duration': 5}
        event = {'call': 'FOO', 'dur': 6, 'target': 'TG1'}
        last_msg = {}
        self.assertTrue(should_push(conf, event, last_msg))

    def test_should_push_ignore_and_self(self):
        conf = {'focus_list': '', 'ignore_list': 'BAR', 'my_callsign': 'MYCALL', 'min_duration': 1}
        event1 = {'call': 'BAR', 'dur': 10, 'target': 'TG1'}
        event2 = {'call': 'MYCALL', 'dur': 10, 'target': 'TG1'}
        self.assertFalse(should_push(conf, event1, {}))
        self.assertFalse(should_push(conf, event2, {}))

    def test_should_push_min_duration_and_duplicate(self):
        conf = {'focus_list': '', 'ignore_list': '', 'my_callsign': 'MYCALL', 'min_duration': 5}
        event = {'call': 'BA4SMQ', 'target': 'TG 46004', 'dur': 3}
        self.assertFalse(should_push(conf, event, {}))
        last = {'call': 'BA4SMQ', 'target': 'TG 46004', 'ts': time.time()}
        event2 = {'call': 'BA4SMQ', 'target': 'TG 46004', 'dur': 8}
        self.assertFalse(should_push(conf, event2, last))

    def test_should_push_different_target(self):
        conf = {'focus_list': '', 'ignore_list': '', 'my_callsign': 'MYCALL', 'min_duration': 1}
        event1 = {'call': 'BA4SMQ', 'target': 'TG 46004', 'dur': 5}
        event2 = {'call': 'BA4SMQ', 'target': 'TG 46005', 'dur': 5}
        last = {'call': 'BA4SMQ', 'target': 'TG 46004', 'ts': time.time()}
        self.assertFalse(should_push(conf, event1, last))
        self.assertTrue(should_push(conf, event2, last))


class TestSeenDedup(unittest.TestCase):
    """Per-(call,target) dedup replaced the single-entry comparison | 去重表取代单条比较"""

    conf = {'focus_list': '', 'ignore_list': '', 'my_callsign': 'MYCALL',
            'min_duration': 1, 'dedup_window': 30}

    def test_alternating_calls_are_deduped(self):
        seen = {}
        a = {'call': 'BA4SMQ', 'target': 'TG 1', 'dur': 5}
        b = {'call': 'BG5ABC', 'target': 'TG 1', 'dur': 5}
        self.assertTrue(should_push(self.conf, a, {}, seen))
        self.assertTrue(should_push(self.conf, b, {}, seen))
        # A-B-A: the third one must be suppressed even though last was B
        self.assertFalse(should_push(self.conf, a, {}, seen))

    def test_window_expiry_allows_repush(self):
        seen = {('BA4SMQ', 'TG 1'): time.time() - 120}
        event = {'call': 'BA4SMQ', 'target': 'TG 1', 'dur': 5}
        self.assertTrue(should_push(self.conf, event, {}, seen))

    def test_forget_pushed_allows_retry(self):
        seen = {}
        event = {'call': 'BA4SMQ', 'target': 'TG 1', 'dur': 5}
        self.assertTrue(should_push(self.conf, event, {}, seen))
        self.assertFalse(should_push(self.conf, event, {}, seen))
        forget_pushed(seen, event)
        self.assertTrue(should_push(self.conf, event, {}, seen))

    def test_store_stays_bounded(self):
        seen = {}
        for i in range(600):
            seen[('CALL%03d' % i, 'TG 1')] = time.time() - 600
        event = {'call': 'BA4SMQ', 'target': 'TG 1', 'dur': 5}
        should_push(self.conf, event, {}, seen)
        self.assertLess(len(seen), 600)


if __name__ == '__main__':
    unittest.main()
