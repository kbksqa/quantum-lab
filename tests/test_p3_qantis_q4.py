# Tests for P3.3. The 19-variable instance is checked against quantities computed without the energy table:
#   - variable and coupling counts follow from the constraint structure: 3 rows of 5 and 4 columns of 4 variables
#   - the brute-force optimum over all 2^19 strings equals the best valid association found by direct enumeration
#   - the Hungarian-as-coded value is never below that optimum
#
# Run from the repository root:
#     python -m unittest discover -s tests -v

import math
import pathlib
import sys
import unittest

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from p3_qantis_instance import association_vector, associations, energy, hungarian_as_coded  # noqa: E402
from p3_qantis_qaoa import make_problem  # noqa: E402


class TestNineteenVariables(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pr = make_problem(1.5, 3, 4)

    def test_counts(self):
        Q = self.pr["qubo"]["Q"]
        self.assertEqual(self.pr["n"], 3 * 4 + 3 + 4)
        self.assertEqual(int(np.count_nonzero(np.triu(Q, 1))), 3 * math.comb(5, 2) + 4 * math.comb(4, 2))
        self.assertEqual(len(self.pr["E"]), 1 << 19)

    def test_optimum_equals_best_valid_association(self):
        qubo = self.pr["qubo"]
        best = min(float(energy(qubo, association_vector(a, 3, 4))[0]) for a in associations(3, 4))
        self.assertAlmostEqual(self.pr["E_opt"], best, places=8)
        self.assertEqual(int(self.pr["feasible"].sum()), sum(1 for _ in associations(3, 4)))

    def test_hungarian_not_below_optimum(self):
        self.assertGreaterEqual(hungarian_as_coded(self.pr["qubo"])["objective"], self.pr["E_opt"] - 1e-9)


if __name__ == "__main__":
    unittest.main()
