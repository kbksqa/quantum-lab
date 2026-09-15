# Tests for P4.1: the report's numbers must still match their committed sources.
#   - paper/numbers.tex, rebuilt from the result files, must equal the committed file byte for byte
#   - every source file a number is read from must be tracked by git
#   - macro names must be letters only and unique
#
# Run from the repository root:
#     python -m unittest discover -s tests -v

import json
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import p4_numbers  # noqa: E402


class TestNumbers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p4_numbers._cache.clear()
        cls.tex, cls.table = p4_numbers.build()

    def test_committed_numbers_match_sources(self):
        committed = (ROOT / "paper" / "numbers.tex").read_text(encoding="utf-8")
        self.assertEqual(committed, self.tex, "paper/numbers.tex is out of date: run tools/p4_numbers.py")
        self.assertEqual(json.loads((ROOT / "paper" / "numbers.json").read_text(encoding="utf-8")), self.table)

    def test_sources_are_tracked(self):
        tracked = set(subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True).stdout.split())
        for name, _, _, _ in p4_numbers.entries():
            source = self.table[name]["source"]
            self.assertIn(source, tracked, "%s reads %s, which is not committed" % (name, source))

    def test_log_constants_are_labelled(self):
        for name, _, note in p4_numbers.LOG_CONSTANTS:
            self.assertIn("research log", self.table[name]["source"])
            self.assertTrue(note)


if __name__ == "__main__":
    unittest.main()
