# Tests for P2.6 that need no IBM account: the instances and parameters sent to hardware must be exactly the simulator's.
#   - the rebuilt P2.5 sparse set reproduces every stored optimum, variable count and P(optimal) (the script checks to 1e-9)
#   - the rebuilt P1.4 2x2 p = 2 items reproduce the simulator values that P1.5 recorded
#   - submitting without a registered plan is refused
#
# Run from the repository root:
#     python -m unittest discover -s tests -v

import json
import pathlib
import subprocess
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from p2_6_hardware import P1_5_FILE, h5_items, items_3d  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]


class TestRebuild(unittest.TestCase):
    def test_sparse_items_reproduce_p2_5(self):
        items = items_3d()  # raises SystemExit on any mismatch
        self.assertEqual(len(items), 30)
        self.assertTrue(all(6 <= it["qubits"] <= 12 for it in items))
        self.assertEqual(items[0]["circuit"].num_qubits, items[0]["qubits"])

    def test_h5_items_match_p1_5_simulator_values(self):
        items = h5_items()
        self.assertEqual([it["index"] for it in items], list(range(10)))
        recorded = json.loads(P1_5_FILE.read_text(encoding="utf-8"))
        p15 = {it["index"]: it for it in recorded["items"] if it["size"] == "pure 2x2" and it["p"] == 2}
        for it in items:
            self.assertAlmostEqual(it["simulator"]["p_optimal"], p15[it["index"]]["simulator"]["p_optimal"], places=9)

    def test_submit_without_plan_is_refused(self):
        run = subprocess.run([sys.executable, str(ROOT / "src" / "p2_6_hardware.py")], capture_output=True, text=True)
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("registered plan", run.stderr)


if __name__ == "__main__":
    unittest.main()
