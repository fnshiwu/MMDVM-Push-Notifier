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

    def test_process_cpu_percent(self):
        stat_seq = [
            "cpu  100 0 100 800 20 0 0 0 0 0 0\n",
            "cpu  140 0 120 880 25 0 0 0 0 0 0\n",
        ]
        it_stat = iter(stat_seq)

        def fake_open(path, mode="r", *args, **kwargs):
            class F:
                def __init__(self, txt, lines=False):
                    self._txt = txt
                    self._lines = lines
                def __enter__(self): return self
                def __exit__(self, *a): pass
                def readline(self): 
                    try: 
                        return next(it_stat)
                    except StopIteration:
                        return stat_seq[-1]
                def read(self): return self._txt
            if path.endswith("/proc/stat"):
                return F("", True)
            if path.endswith("/proc/1234/stat"):
                if getattr(fake_open, "count", 0) == 0:
                    fake_open.count = 1
                    # utime=100 (index 13), stime=50 (index 14)
                    fields = ["1234","(python)","R"] + ["0"]*10 + ["100","50"] + ["0"]*30
                    return F(" ".join(fields))
                else:
                    # utime=130, stime=70
                    fields = ["1234","(python)","R"] + ["0"]*10 + ["130","70"] + ["0"]*30
                    return F(" ".join(fields))
            raise FileNotFoundError(path)

        with patch.object(builtins, "open", side_effect=fake_open):
            with patch("os.getpid", return_value=1234):
                mon = mp.MMDVMMonitor()
                val = mon._cpu_percent_process(interval=0.01)
                self.assertTrue(0.0 <= float(val) <= 100.0)


if __name__ == "__main__":
    unittest.main()
