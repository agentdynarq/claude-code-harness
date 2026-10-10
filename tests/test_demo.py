"""Category A: the documented walkthrough runs end to end in a temporary directory."""

from __future__ import annotations

import re
import unittest

from helpers import REPO, run_script, snapshot


class Walkthrough(unittest.TestCase):
    def test_demo_meets_every_expectation_and_leaves_the_repository_alone(self):
        example = REPO / "examples" / "invoice-totals"
        before = {k: v for k, v in snapshot(example).items() if "__pycache__" not in k}
        proc = run_script(REPO / "scripts" / "demo.py", timeout=600)
        self.assertEqual(proc.returncode, 0, proc.stdout[-3000:] + proc.stderr[-2000:])
        self.assertNotIn("EXPECTATION FAILED", proc.stdout)
        match = re.search(r"All (\d+) expectations met\.", proc.stdout)
        self.assertIsNotNone(match)
        self.assertGreaterEqual(int(match.group(1)), 14)
        after = {k: v for k, v in snapshot(example).items() if "__pycache__" not in k}
        self.assertEqual(after, before, "the demo must work on a copy, never on examples/")


if __name__ == "__main__":
    unittest.main()
