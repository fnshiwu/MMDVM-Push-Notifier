import os
import importlib.util
import unittest

ROOT = os.path.dirname(os.path.dirname(__file__))
PARSER_PATH = os.path.join(ROOT, "parser.py")
spec = importlib.util.spec_from_file_location("local_parser", PARSER_PATH)
parser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parser)


class TestParserLegacy(unittest.TestCase):
    """Formats produced by older MMDVMHost builds | 旧版 MMDVMHost 格式"""

    def test_valid_voice_line(self):
        line = "end of voice transmission from BA4SMQ to TG 46004, 3.2 seconds, 0% packet loss, BER: 0.1%"
        e = parser.parse_line(line)
        self.assertIsNotNone(e)
        self.assertEqual(e['call'], "BA4SMQ")
        self.assertTrue(e['is_voice'])
        self.assertAlmostEqual(e['dur'], 3.2, places=1)

    def test_valid_data_line(self):
        line = "end of data transmission from N0CALL to PRIVATE 1234, 1.0 seconds, BER: 2.0%"
        e = parser.parse_line(line)
        self.assertIsNotNone(e)
        self.assertFalse(e['is_voice'])
        self.assertEqual(e['ber'], "2.0")

    def test_invalid_line(self):
        self.assertIsNone(parser.parse_line("random noise line"))


class TestParserPiStar43(unittest.TestCase):
    """Formats produced by MMDVMHost on Pi-Star 4.3.x | Pi-Star 4.3.x 上的新格式"""

    def test_dmr_rf_voice_with_rssi(self):
        line = ("M: 2026-05-01 12:00:10.000 DMR Slot 2, received RF end of voice transmission "
                "from BA4SMQ to TG 46001, 3.4 seconds, 0% packet loss, BER: 0.1%, RSSI: -45 dBm")
        e = parser.parse_line(line)
        self.assertIsNotNone(e)
        self.assertEqual(e['call'], "BA4SMQ")
        self.assertEqual(e['target'], "TG 46001")
        self.assertEqual(e['mode'], "DMR")
        self.assertEqual(e['slot'], " (Slot 2)")
        self.assertEqual(e['rssi'], "-45")
        self.assertEqual(e['ber'], "0.1")
        self.assertTrue(e['is_voice'])

    def test_dmr_network_voice(self):
        line = ("DMR Slot 1, received network end of voice transmission from N0CALL to TG 91, "
                "10.0 seconds, 2% packet loss, BER: 0.0%")
        e = parser.parse_line(line)
        self.assertIsNotNone(e)
        self.assertEqual(e['mode'], "DMR")
        self.assertEqual(e['slot'], " (Slot 1)")
        self.assertEqual(e['loss'], "2")

    def test_dstar_line(self):
        line = ("D-Star, received RF end of voice transmission from BA4SMQ to CQCQCQ, "
                "4.0 seconds, BER: 0.0%")
        e = parser.parse_line(line)
        self.assertIsNotNone(e)
        self.assertEqual(e['mode'], "D-Star")
        self.assertEqual(e['target'], "CQCQCQ")
        self.assertEqual(e['slot'], "")

    def test_ysf_line(self):
        line = "YSF, received RF end of voice transmission from BG5XXX to ALL, 2.5 seconds, BER: 1.5%"
        e = parser.parse_line(line)
        self.assertIsNotNone(e)
        self.assertEqual(e['mode'], "YSF")

    def test_p25_line(self):
        line = "P25, received RF end of voice transmission from N0CALL to 10100, 2.0 seconds, BER: 0.0%"
        e = parser.parse_line(line)
        self.assertIsNotNone(e)
        self.assertEqual(e['mode'], "P25")
        self.assertEqual(e['ber'], "0.0")

    def test_nxdn_line(self):
        line = "NXDN, received RF end of voice transmission from JA1XXX to 65000, 1.2 seconds, BER: 0.0%"
        e = parser.parse_line(line)
        self.assertIsNotNone(e)
        self.assertEqual(e['mode'], "NXDN")

    def test_no_duration_is_ignored(self):
        self.assertIsNone(parser.parse_line("DMR Slot 2, received RF voice header from BA4SMQ to TG 1"))

    def test_out_of_range_duration(self):
        line = "end of voice transmission from BA4SMQ to TG 1, 99999.0 seconds"
        self.assertIsNone(parser.parse_line(line))


if __name__ == '__main__':
    unittest.main()
