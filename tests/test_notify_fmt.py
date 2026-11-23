import unittest

from notify_fmt import format_message, format_boot_notice, format_test_push


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

    def test_dynamic_values_are_html_escaped(self):
        """Telegram parse_mode=HTML returns 400 on raw & / < | 未转义会被 Telegram 拒绝"""
        conf = {'ui_lang': 'cn'}
        event = {
            'call': 'BA4SMQ',
            'target': 'TG <46001> & CO',
            'dur': 5.0,
            'loss': '0',
            'ber': '0.1',
            'slot': '',
            'mode': 'DMR',
            'rssi': '-45',
            'is_voice': True,
        }
        _, body = format_message(conf, event, '25.0°C',
                                 {'name': ' (SMITH & SONS)', 'loc_cn': '中国'})
        self.assertIn('&amp;', body)
        self.assertIn('&lt;46001&gt;', body)
        self.assertNotIn('<46001>', body)
        self.assertNotIn('SMITH & SONS', body)
        # our own markup must survive | 我们自己的标签不能被转义掉
        self.assertIn('<b>呼号</b>', body)

    def test_ber_zero_never_leaks_none(self):
        """A missing BER field must not render as None | 缺 BER 字段不能渲染成 None"""
        conf = {'ui_lang': 'cn'}
        event = {
            'call': 'BA4SMQ', 'target': 'TG 1', 'dur': 3.0, 'loss': '0',
            'ber': '0.0', 'slot': '', 'is_voice': True,
        }
        _, body = format_message(conf, event, 'N/A', {'name': '', 'loc_cn': '未知'})
        self.assertNotIn('None', body)

    def test_mode_and_rssi_appended(self):
        conf = {'ui_lang': 'en'}
        event = {
            'call': 'BA4SMQ', 'target': 'TG 1', 'dur': 3.0, 'loss': '0',
            'ber': '0.0', 'slot': ' (Slot 2)', 'mode': 'YSF', 'rssi': '-60',
            'is_voice': True,
        }
        title, body = format_message(conf, event, 'N/A', {'name': '', 'loc_en': 'China'})
        self.assertIn('YSF', title)
        self.assertIn('RSSI', body)
        self.assertIn('-60', body)

    def test_boot_notice_escapes_version(self):
        title, body = format_boot_notice({'ui_lang': 'en'}, 'v3.6.1<&>', '10.0.0.1',
                                         '40°C', '5.0', '30%', True)
        self.assertIn('Boot Notice', title)
        self.assertIn('&lt;&amp;&gt;', body)

    def test_test_push_bilingual(self):
        t_cn, b_cn = format_test_push({'ui_lang': 'cn'}, 'v3.6.1', '1.2.3.4', '40°C', '1.0', '20%')
        self.assertIn('测试推送', t_cn)
        self.assertIn('温度', b_cn)
        t_en, _ = format_test_push({'ui_lang': 'en'}, 'v3.6.1', '1.2.3.4', '40°C', '1.0', '20%')
        self.assertIn('Test Notification', t_en)


if __name__ == '__main__':
    unittest.main()
