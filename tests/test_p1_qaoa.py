# Tests for P1.4.
#   - the Ising form must reproduce the QUBO energy of every bit string
#   - the NumPy QAOA simulator must match Qiskit's Statevector of the circuit built from the Ising coefficients
#     (this checks the conversion, the angle conventions and the simulator together)
#   - zero angles must give the uniform distribution
#   - optimisation must be deterministic per seed and beat the uniform expectation
#
# Run from the repository root:
#     python -m unittest discover -s tests -v

import math
import pathlib
import sys
import unittest

import numpy as np
from qiskit.quantum_info import Statevector

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from p1_annealing import max_abs_rule  # noqa: E402
from p1_penalty import enumerate_strings  # noqa: E402
from p1_qaoa import ising, ising_energies, optimize, prepare, qaoa_circuit, simulate  # noqa: E402
from p1_qubo import build_qubo  # noqa: E402


class TestIsing(unittest.TestCase):
    def test_ising_reproduces_qubo_energies(self):
        rng = np.random.default_rng(41)
        for _ in range(10):
            C = rng.normal(0, 5, size=(3, 3))
            A = float(rng.uniform(1, 30))
            strings = enumerate_strings(C)
            h, J, const = ising(build_qubo(C, penalty=A))
            self.assertTrue(np.allclose(ising_energies(h, J, const, strings["X"]),
                                        strings["cost"] + A * strings["V"], atol=1e-8))


class TestSimulator(unittest.TestCase):
    def test_numpy_simulator_matches_qiskit_statevector(self):
        rng = np.random.default_rng(42)
        for n in (2, 3):
            C = rng.uniform(1, 10, size=(n, n))
            strings = enumerate_strings(C)
            prep = prepare(C, max_abs_rule(C), strings)
            gammas = rng.uniform(0, math.pi, 2)
            betas = rng.uniform(0, math.pi / 2, 2)
            ours = simulate(prep["diag"], len(prep["h"]), gammas, betas)
            circuit = qaoa_circuit(prep["h"], prep["J"], prep["scale"], gammas, betas)
            reference = Statevector(circuit).probabilities()
            self.assertTrue(np.allclose(ours, reference, atol=1e-9), "mismatch for %dx%d" % (n, n))

    def test_zero_angles_give_uniform_distribution(self):
        C = np.arange(1.0, 10.0).reshape(3, 3)
        strings = enumerate_strings(C)
        prep = prepare(C, max_abs_rule(C), strings)
        probs = simulate(prep["diag"], 9, [0.0], [0.0])
        self.assertTrue(np.allclose(probs, 1 / 512))
        self.assertAlmostEqual(float(probs[strings["V"] == 0].sum()), math.factorial(3) / 512, places=12)


class TestOptimisation(unittest.TestCase):
    def test_deterministic_and_better_than_uniform(self):
        C = np.array([[1.0, 4.0], [3.0, 2.0]])
        strings = enumerate_strings(C)
        prep = prepare(C, max_abs_rule(C), strings)
        first = optimize(prep["diag"], 4, 1, np.random.default_rng(5), starts=4)
        second = optimize(prep["diag"], 4, 1, np.random.default_rng(5), starts=4)
        self.assertTrue(np.allclose(first[0], second[0]))
        self.assertLess(first[1], float(prep["diag"].mean()))


if __name__ == "__main__":
    unittest.main()
