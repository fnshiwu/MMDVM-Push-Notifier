import os
import tempfile
import unittest

from identity import Identity

# Column layout used by nextionUsers.csv:
# 0 spare, 1 callsign, 2 first name, 3 last name, 4 city, 5 state, 6 country
CSV = (
    "U0,SV1AAA,ZHANG,SAN,Shanghai,SH,China\r\n"
    'U1,AAA111,NAME,ONE,"City,SK1ZZZ,X",ST,China\r\n'
    "U2,SK1ZZZ,REAL,USER,Oslo,OS,Norway\r\n"
    "U3,BA4SMQ,LI,SI,Hefei,AH,China\r\n"
)


class TestIdentityLookup(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(CSV)
        self.id = Identity(self.path)

    def tearDown(self):
        try:
            os.remove(self.path)
        except OSError:
            pass

    def test_basic_lookup(self):
        info = self.id.get_info("BA4SMQ")
        self.assertIn("LI SI", info["name"])
        self.assertIn("Hefei", info["loc_en"])

    def test_unknown_callsign(self):
        info = self.id.get_info("N0CALL")
        self.assertEqual(info["name"], "")
        self.assertEqual(info["loc_en"], "Unknown")

    def test_decoy_inside_another_field_is_skipped(self):
        """"City,SK1ZZZ,X" must not shadow the real SK1ZZZ line | 字段内的同串不能误命中"""
        info = self.id.get_info("SK1ZZZ")
        self.assertIn("REAL USER", info["name"])
        self.assertNotIn("NAME ONE", info["name"])

    def test_result_is_not_shared_cache_object(self):
        first = self.id.get_info("BA4SMQ")
        first["name"] = "MUTATED"
        second = self.id.get_info("BA4SMQ")
        self.assertNotEqual(second["name"], "MUTATED")


if __name__ == '__main__':
    unittest.main()
