import unittest

from config import ConfigManager


class TestConfig(unittest.TestCase):
    def test_temp_interval_minutes_to_seconds(self):
        conf = ConfigManager._validate_config({"temp_interval": 30})
        self.assertEqual(conf["temp_interval"], 1800)

    def test_temp_interval_minimum(self):
        conf = ConfigManager._validate_config({"temp_interval": 0})
        self.assertEqual(conf["temp_interval"], 60)

    def test_callsign_normalised(self):
        conf = ConfigManager._validate_config({"my_callsign": " ba4smq-1 "})
        self.assertEqual(conf["my_callsign"], "BA4SMQ-1")

    def test_log_dir_must_be_absolute(self):
        self.assertEqual(ConfigManager._validate_config({"log_dir": "/var/log/pi-star"})["log_dir"],
                         "/var/log/pi-star")
        self.assertEqual(ConfigManager._validate_config({"log_dir": "relative/path"})["log_dir"], "")

    def test_bad_url_rejected(self):
        self.assertEqual(ConfigManager._validate_config({"fs_webhook": "ftp://x/y"})["fs_webhook"], "")
        self.assertEqual(
            ConfigManager._validate_config({"fs_webhook": "https://open.feishu.cn/x"})["fs_webhook"],
            "https://open.feishu.cn/x")

    def test_language_whitelist(self):
        self.assertEqual(ConfigManager._validate_config({"ui_lang": "EN"})["ui_lang"], "en")
        self.assertEqual(ConfigManager._validate_config({"ui_lang": "xx"})["ui_lang"], "cn")

    def test_defaults_when_empty(self):
        conf = ConfigManager._validate_config({})
        self.assertEqual(conf["min_duration"], 4.0)
        self.assertEqual(conf["temp_interval"], 1800)
        self.assertFalse(conf["quiet_mode"]["enabled"])


if __name__ == '__main__':
    unittest.main()
