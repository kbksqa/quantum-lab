# Tests for P6.4 that need no IBM account:
#   - the metrics on the exact noiseless distributions reproduce the P6.1 theory values (independent: sin^2(3 theta), Bayes)
#   - the grading and prediction rules at their boundaries
#   - the QPU-time estimate rule and the go rule read from the committed P6.1 / P6.2 results
#   - submitting without a registered plan is refused
#
# Run from the repository root:
#     python -m unittest discover -s tests -v

import math
import pathlib
import subprocess
import sys
import unittest

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from p6_hardware import estimate_seconds, go_rule, grade_claim, grade_predictions, metrics  # noqa: E402
from p6_tiger import grover1_circuit, oracle_circuit, statevector  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]


class TestMetrics(unittest.TestCase):
    def test_noiseless_distributions_give_theory_values(self):
        base = np.abs(statevector(oracle_circuit([0.97, 0.03]))) ** 2
        grover = np.abs(statevector(grover1_circuit([0.97, 0.03], 1))) ** 2
        m = metrics(base, grover)
        evidence = 0.97 * 0.15 + 0.03 * 0.85
        self.assertAlmostEqual(m["p_obs1_baseline"], evidence)
        self.assertAlmostEqual(m["p_obs1_grover"], math.sin(3 * math.asin(math.sqrt(evidence))) ** 2)
        self.assertAlmostEqual(m["posterior"][0], 0.97 * 0.15 / evidence)
        self.assertLess(m["posterior_hellinger"], 1e-9)
        self.assertAlmostEqual(m["grover_over_direct_per_oracle_application"], m["amplification"] / 3)


class TestRules(unittest.TestCase):
    def test_claim_grading(self):
        good = {"p_obs1_grover": 0.907, "amplification": 5.1, "posterior_hellinger": 0.01}
        self.assertEqual(grade_claim(good)["grade"], "reproduced")
        self.assertEqual(grade_claim({**good, "posterior_hellinger": 0.06})["grade"], "partly reproduced")
        self.assertEqual(grade_claim({**good, "p_obs1_grover": 0.80, "amplification": 4.0})["grade"], "not reproduced")

    def test_predictions(self):
        mean = {"p_obs1_baseline": 0.18, "p_obs1_grover": 0.90, "amplification": 5.0, "posterior_hellinger": 0.01,
                "grover_over_direct_per_oracle_application": 1.67}
        self.assertTrue(all(grade_predictions(mean).values()))
        self.assertFalse(grade_predictions({**mean, "p_obs1_grover": 0.95})["E2"])

    def test_estimate_and_go_rule(self):
        self.assertAlmostEqual(estimate_seconds(8 * 8192), 9.0 * (65536 / 49152) * 2)
        self.assertAlmostEqual(estimate_seconds(1000), 18.0)
        rule = go_rule(8 * 8192)
        self.assertEqual(rule["C1"], "reproduced")
        self.assertEqual(rule["C3_grover"], "partly reproduced")
        self.assertTrue(rule["go"])

    def test_submit_without_plan_is_refused(self):
        run = subprocess.run([sys.executable, str(ROOT / "src" / "p6_hardware.py")], capture_output=True, text=True)
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("registered plan", run.stderr)


if __name__ == "__main__":
    unittest.main()
