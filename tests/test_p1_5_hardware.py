# Tests for P1.5 - everything that can be checked without a quantum computer.
#   - the rebuilt instances and stored P1.4 parameters must reproduce P1.4 exactly (same check the script runs)
#   - tensored readout correction must exactly undo an independent per-qubit readout model
#   - for independent errors it must agree with the full assignment-matrix correction used in P0.5
#   - per-qubit error estimates must be read from the right bit of each bitstring
#
# Run from the repository root:
#     python -m unittest discover -s tests -v

import json
import pathlib
import sys
import unittest

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from p0_5_readout import correct as full_matrix_correct  # noqa: E402
from p1_5_hardware import (  # noqa: E402
    P1_4_FILE,
    counts_to_probs,
    per_qubit_errors,
    planned_items,
    rebuild_p1_4_instances,
    tensored_correct,
)


def apply_independent_readout(probs, measured, errors):
    """Forward model: each measured qubit flips independently with its own p10 / p01."""
    m = len(measured)
    out = np.zeros_like(probs)
    for true_state in range(1 << m):
        for read_state in range(1 << m):
            weight = 1.0
            for k, q in enumerate(measured):
                p10, p01 = errors[q]
                t, r = (true_state >> k) & 1, (read_state >> k) & 1
                if t == 0:
                    weight *= p10 if r == 1 else 1 - p10
                else:
                    weight *= p01 if r == 0 else 1 - p01
            out[read_state] += weight * probs[true_state]
    return out


class TestFingerprint(unittest.TestCase):
    def test_planned_items_reproduce_p1_4(self):
        stored = json.loads(P1_4_FILE.read_text(encoding="utf-8"))
        items = planned_items(stored, rebuild_p1_4_instances())
        self.assertEqual(len(items), 10 * 2 + 5)
        self.assertEqual({it["qubits"] for it in items if it["size"] == "pure 2x2"}, {4})
        self.assertEqual({it["qubits"] for it in items if it["size"] == "pure 3x3"}, {9})


class TestReadoutCorrection(unittest.TestCase):
    def test_tensored_correction_undoes_independent_readout(self):
        rng = np.random.default_rng(51)
        measured = [11, 4, 7]
        errors = {11: (0.02, 0.05), 4: (0.01, 0.03), 7: (0.04, 0.02)}
        truth = rng.dirichlet(np.ones(8))
        observed = apply_independent_readout(truth, measured, errors)
        self.assertTrue(np.allclose(tensored_correct(observed, measured, errors), truth, atol=1e-12))

    def test_agrees_with_full_matrix_method_for_independent_errors(self):
        rng = np.random.default_rng(52)
        measured = [0, 1, 2]
        errors = {0: (0.03, 0.06), 1: (0.02, 0.01), 2: (0.05, 0.04)}
        A = np.column_stack([apply_independent_readout(np.eye(8)[s], measured, errors) for s in range(8)])
        observed = apply_independent_readout(rng.dirichlet(np.ones(8)), measured, errors)
        self.assertTrue(np.allclose(tensored_correct(observed, measured, errors),
                                    full_matrix_correct(A, observed), atol=1e-12))

    def test_per_qubit_errors_read_the_right_bit(self):
        union = [30, 31]
        counts_all0 = {"00": 90, "01": 10}   # bit 0 (rightmost) -> qubit 30 reads 1 in 10%
        counts_all1 = {"11": 80, "01": 20}   # bit 1 -> qubit 31 reads 0 in 20%
        errors = per_qubit_errors(counts_all0, counts_all1, union)
        self.assertAlmostEqual(errors[30][0], 0.10)
        self.assertAlmostEqual(errors[31][0], 0.00)
        self.assertAlmostEqual(errors[30][1], 0.00)
        self.assertAlmostEqual(errors[31][1], 0.20)

    def test_counts_to_probs_bit_order(self):
        probs = counts_to_probs({"001": 3, "100": 1}, 3)
        self.assertAlmostEqual(probs[1], 0.75)
        self.assertAlmostEqual(probs[4], 0.25)


if __name__ == "__main__":
    unittest.main()
