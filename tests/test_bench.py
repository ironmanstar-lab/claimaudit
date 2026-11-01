"""黄金集也不回归：CI 里跟单测一起跑。"""
from __future__ import annotations

import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


class GoldenSetTests(unittest.TestCase):
    def test_golden_set_all_pass(self):
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "bench", "run.py"), "--json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(proc.returncode, 0, "黄金集有样本不符预期：\n%s" % proc.stdout)
        self.assertIn('"result": "PASS"', proc.stdout)


if __name__ == "__main__":
    unittest.main()
