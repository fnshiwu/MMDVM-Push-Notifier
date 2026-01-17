import unittest
import time
from datetime import datetime, timedelta

from filters import quiet_time, should_push


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
        event = {'call': 'FOO', 'dur': 6}
        last_msg = {}
        self.assertTrue(should_push(conf, event, last_msg))

    def test_should_push_ignore_and_self(self):
        conf = {'focus_list': '', 'ignore_list': 'BAR', 'my_callsign': 'MYCALL', 'min_duration': 1}
        event1 = {'call': 'BAR', 'dur': 10}
        event2 = {'call': 'MYCALL', 'dur': 10}
        self.assertFalse(should_push(conf, event1, {}))
        self.assertFalse(should_push(conf, event2, {}))

    def test_should_push_min_duration_and_duplicate(self):
        conf = {'focus_list': '', 'ignore_list': '', 'my_callsign': 'MYCALL', 'min_duration': 5}
        event = {'call': 'BA4SMQ', 'dur': 3}
        self.assertFalse(should_push(conf, event, {}))
        last = {'call': 'BA4SMQ', 'ts': time.time()}
        event2 = {'call': 'BA4SMQ', 'dur': 8}
        self.assertFalse(should_push(conf, event2, last))


if __name__ == '__main__':
    unittest.main()
