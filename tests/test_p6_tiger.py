# Tests for P6.1. Each check uses a route that does not depend on the code being tested:
#   - Bayes posteriors by hand for the textbook Tiger numbers
#   - the belief oracle's circuit against its amplitude vector, and A S0 A^dagger against I - 2|psi><psi| through Qiskit's Operator
#   - the Grover probability against sin^2(3 theta) for random priors
#   - the Hellinger / total-variation bounds on random distributions
#
# Run from the repository root:
#     python -m unittest discover -s tests -v

import math
import pathlib
import sys
import unittest

import numpy as np
from qiskit import QuantumCircuit
from qiskit.quantum_info import Operator

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from p6_tiger import (  # noqa: E402
    OPEN_LEFT,
    P_OBS0_2,
    P_OBS0_4,
    bayes,
    four_state_circuit,
    grover1_circuit,
    hellinger,
    oracle_amplitudes,
    oracle_circuit,
    phase_aligned_difference,
    post_select,
    statevector,
    tiger_circuit,
    total_variation,
)


class TestReferences(unittest.TestCase):
    def test_bayes_by_hand(self):
        posterior, evidence = bayes([0.5, 0.5], P_OBS0_2, 0)
        self.assertTrue(np.allclose(posterior, [0.85, 0.15]))
        self.assertAlmostEqual(evidence, 0.5)
        posterior, evidence = bayes([0.97, 0.03], P_OBS0_2, 1)
        self.assertAlmostEqual(evidence, 0.97 * 0.15 + 0.03 * 0.85)
        self.assertAlmostEqual(posterior[0], 0.97 * 0.15 / evidence)
        self.assertTrue(np.allclose(bayes([0.9, 0.1], P_OBS0_2, 1, OPEN_LEFT)[0], [0.5, 0.5]))

    def test_distance_bounds(self):
        rng = np.random.default_rng(100)
        for _ in range(500):
            k = int(rng.integers(2, 6))
            p, q = rng.dirichlet(np.ones(k)), rng.dirichlet(np.ones(k))
            H, tv = hellinger(p, q), total_variation(p, q)
            self.assertLessEqual(H * H, tv + 1e-12)
            self.assertLessEqual(tv, H * math.sqrt(2 - H * H) + 1e-12)


class TestCircuits(unittest.TestCase):
    def test_oracle_and_four_state_circuits_match_amplitudes(self):
        rng = np.random.default_rng(101)
        for _ in range(10):
            prior2 = rng.dirichlet([1, 1])
            self.assertLess(phase_aligned_difference(oracle_amplitudes(prior2, P_OBS0_2),
                                                     statevector(oracle_circuit(prior2))), 1e-9)
            prior4 = rng.dirichlet(np.ones(4))
            state = statevector(four_state_circuit(prior4))
            self.assertLess(phase_aligned_difference(oracle_amplitudes(prior4, P_OBS0_4), state), 1e-9)
            for obs in (0, 1):
                self.assertLess(hellinger(post_select(np.abs(state) ** 2, 4, obs)[0], bayes(prior4, P_OBS0_4, obs)[0]), 1e-9)

    def test_reflection_identity(self):
        prior = [0.8, 0.2]
        A = oracle_circuit(prior)
        middle = QuantumCircuit(2)
        middle.compose(A.inverse(), inplace=True)
        middle.x([0, 1])
        middle.cz(0, 1)
        middle.x([0, 1])
        middle.compose(A, inplace=True)
        psi = oracle_amplitudes(prior, P_OBS0_2)
        self.assertTrue(np.allclose(Operator(middle).data, np.eye(4) - 2 * np.outer(psi, psi.conj()), atol=1e-10))

    def test_grover_probability_is_sin2_3theta(self):
        rng = np.random.default_rng(102)
        for _ in range(10):
            prior = rng.dirichlet([1, 1])
            for target in (0, 1):
                _, evidence = bayes(prior, P_OBS0_2, target)
                state = statevector(grover1_circuit(prior, target))
                p = float(np.sum(np.abs(state.reshape(2, 2)[target]) ** 2))
                self.assertAlmostEqual(p, math.sin(3 * math.asin(math.sqrt(evidence))) ** 2, places=10)
                self.assertLess(hellinger(post_select(np.abs(state) ** 2, 2, target)[0], bayes(prior, P_OBS0_2, target)[0]),
                                1e-9)

    def test_open_door_circuit_is_uniform(self):
        state = statevector(tiger_circuit([0.9, 0.1], OPEN_LEFT))
        self.assertTrue(np.allclose(np.abs(state) ** 2, 0.25))


if __name__ == "__main__":
    unittest.main()
