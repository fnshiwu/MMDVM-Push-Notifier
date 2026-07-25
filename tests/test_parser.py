import os
import importlib.util
import unittest

ROOT = os.path.dirname(os.path.dirname(__file__))
PARSER_PATH = os.path.join(ROOT, "parser.py")
spec = importlib.util.spec_from_file_location("local_parser", PARSER_PATH)
parser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parser)


class TestParser(unittest.TestCase):
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
        e = parser.parse_line("random noise line")
        self.assertIsNone(e)


if __name__ == '__main__':
    unittest.main()
