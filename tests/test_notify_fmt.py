import unittest

from notify_fmt import format_message


class TestNotifyFmt(unittest.TestCase):
    def test_format_en_voice(self):
        conf = {'ui_lang': 'en'}
        event = {
            'call': 'BA4SMQ',
            'target': 'TG9999',
            'dur': 5.0,
            'loss': '0',
            'ber': '0.0',
            'slot': ' Slot 1',
            'is_voice': True
        }
        t, b = format_message(conf, event, '25.0°C', {'name': '', 'loc_en': 'China', 'loc_cn': '中国'})
        self.assertIn('Voice QSO', t)
        self.assertIn('Callsign', b)
        self.assertIn('Location', b)
        self.assertIn('China', b)
        self.assertIn('Temp', b)
        self.assertIn('TG9999', b)

    def test_format_cn_data(self):
        conf = {'ui_lang': 'cn'}
        event = {
            'call': 'BA4SMQ',
            'target': 'TG9999',
            'dur': 5.0,
            'loss': '0',
            'ber': '0.0',
            'slot': ' Slot 2',
            'is_voice': False
        }
        t, b = format_message(conf, event, '25.0°C', {'name': '', 'loc_cn': '中国', 'loc_en': 'China'})
        self.assertIn('数据模式', t)
        self.assertIn('呼号', b)
        self.assertIn('地区', b)
        self.assertIn('中国', b)
        self.assertIn('温度', b)
        self.assertIn('TG9999', b)


if __name__ == '__main__':
    unittest.main()
