import unittest

from alerts import AlertManager


class FakeHardware:
    def __init__(self, temp=60.0):
        self.temp = temp

    def get_current_temp(self, conf):
        return f"{self.temp:.1f}°C", self.temp


class TestTemperatureHysteresis(unittest.TestCase):
    def setUp(self):
        self.hw = FakeHardware()
        self.alert = AlertManager(self.hw)
        self.conf = {"temp_alert_enabled": True, "temp_threshold": 65.0,
                     "temp_hysteresis": 3.0}

    def test_fires_once_per_excursion(self):
        self.hw.temp = 70.0
        self.assertIsNotNone(self.alert.check_temp_alert(self.conf))
        # still hot on the next scheduled check: must stay silent
        self.hw.temp = 71.5
        self.assertIsNone(self.alert.check_temp_alert(self.conf))
        self.assertFalse(self.alert.armed)

    def test_rearms_only_after_cooldown(self):
        self.hw.temp = 70.0
        self.assertIsNotNone(self.alert.check_temp_alert(self.conf))

        # 64.0 is below the threshold but above threshold - hysteresis (62.0)
        self.hw.temp = 64.0
        self.assertIsNone(self.alert.check_temp_alert(self.conf))
        self.assertFalse(self.alert.armed, "must not re-arm on a shallow dip")

        # 61.0 < 62.0 -> re-arm, but no alert for the cooldown reading
        self.hw.temp = 61.0
        self.assertIsNone(self.alert.check_temp_alert(self.conf))
        self.assertTrue(self.alert.armed)

        # next excursion fires again
        self.hw.temp = 70.0
        self.assertIsNotNone(self.alert.check_temp_alert(self.conf))

    def test_disabled_returns_none(self):
        self.hw.temp = 90.0
        conf = dict(self.conf, temp_alert_enabled=False)
        self.assertIsNone(self.alert.check_temp_alert(conf))

    def test_sensor_error_keeps_state(self):
        self.hw.temp = 70.0
        self.assertIsNotNone(self.alert.check_temp_alert(self.conf))
        self.hw.temp = -2.0  # ERROR sentinel
        self.assertIsNone(self.alert.check_temp_alert(self.conf))
        self.assertFalse(self.alert.armed, "sensor error must not silently re-arm")


if __name__ == '__main__':
    unittest.main()
