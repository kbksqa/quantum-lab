# Tests for P4.1: the report's numbers must still match their committed sources.
#   - paper/numbers.tex, rebuilt from the result files, must equal the committed file byte for byte
#   - every source file a number is read from must be tracked by git
#   - macro names must be letters only and unique
#
# Run from the repository root:
#     python -m unittest discover -s tests -v

import json
import pathlib
import re
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
        for name, _, note in p4_numbers.QUOTED_CONSTANTS:
            self.assertIn("quoted from", self.table[name]["source"])

    def test_manuscript_has_no_hand_typed_result_decimals(self):
        # Design parameters stated in the text are allowed; anything else that looks like a result must come from a macro.
        allowed = {"0.9", "9.21", "1.5"}
        text = (ROOT / "paper" / "main.tex").read_text(encoding="utf-8")
        text = text.split("\\begin{document}", 1)[1]                    # layout settings in the preamble are not results
        text = re.sub(r"(?<!\\)%.*", "", text)                          # comments
        text = re.sub(r"\\href\{[^}]*\}\{[^}]*\}", "", text)            # links, including their visible text
        text = re.sub(r"\\(url|cite|ref|label|includegraphics|input|bibliography\w*)(\[[^\]]*\])?\{[^}]*\}", "", text)
        text = re.sub(r"\d+\.\d+\.\d+", "", text)                        # version numbers
        found = set(re.findall(r"(?<![\\\w])\d+\.\d+", text))
        self.assertEqual(found - allowed, set(), "hand-typed decimals in main.tex; use a macro from numbers.tex")

    def test_every_macro_used_is_defined(self):
        text = (ROOT / "paper" / "main.tex").read_text(encoding="utf-8")
        used = set(re.findall(r"\\(P(?:zero|one|two|three|five|six)[A-Za-z]+|QPU[A-Za-z]+)", text))
        self.assertEqual(used - set(self.table), set())


if __name__ == "__main__":
    unittest.main()
