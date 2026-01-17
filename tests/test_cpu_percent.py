import unittest
import builtins
from unittest.mock import patch, mock_open
import importlib.util
import importlib
import sys
import os

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)
_p_spec = importlib.util.spec_from_file_location("parser", os.path.join(ROOT, "parser.py"))
_p_mod = importlib.util.module_from_spec(_p_spec)
_p_spec.loader.exec_module(_p_mod)
sys.modules["parser"] = _p_mod
mp = importlib.import_module("mmdvm_push")


class TestCPUPercent(unittest.TestCase):
    def test_initial_double_sample(self):
        seq = [
            "cpu  100 0 100 800 20 0 0 0 0 0 0\n",
            "cpu  120 0 110 840 25 0 0 0 0 0 0\n",
            "cpu  120 0 110 840 25 0 0 0 0 0 0\n",
        ]
        it = iter(seq)

        def fake_readline():
            try:
                return next(it)
            except StopIteration:
                return seq[-1]

        m = mock_open()
        m.return_value.readline.side_effect = fake_readline
        with patch.object(builtins, "open", m):
            mon = mp.MMDVMMonitor()
            val = mon._cpu_percent_proc()
            self.assertTrue(float(val) > 0.0)
            v2 = mon._cpu_percent_proc()
            self.assertTrue(float(v2) >= 0.0)


if __name__ == "__main__":
    unittest.main()
