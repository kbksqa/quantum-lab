# Tests for P2.5. Each check uses a route that does not depend on the code being tested:
#   - the enumerated violation V(x) is compared with the QUBO energy from p1_qubo.energy: E - cost = A * V
#   - A_crit is checked by brute force just above it (minimum = optimum) and just below it (minimum below the optimum)
#   - the Ising conversion is compared with the enumerated energies
#   - the NumPy simulator is compared with Qiskit's Statevector on a three-dimensional circuit
#
# Run from the repository root:
#     python -m unittest discover -s tests -v

import dataclasses
import pathlib
import sys
import unittest

import numpy as np
from qiskit.quantum_info import Statevector

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from p1_penalty import critical_penalty  # noqa: E402
from p1_qaoa import qaoa_circuit, simulate  # noqa: E402
from p1_qubo import brute_force_minimum, energy  # noqa: E402
from p2_ilp import solve_ilp  # noqa: E402
from p2_qaoa import enumerate_strings, prepare, sparse_set  # noqa: E402
from p2_qubo import build_qubo  # noqa: E402
from p2_scene import PURE, Params, build_tuples, generate  # noqa: E402


def instances(rng, n=6):
    pure = dataclasses.replace(Params(), **PURE)
    out = []
    for _ in range(n):
        scene = generate(2, pure, rng)
        out.append((scene, build_tuples(scene, pure)))
    return out + sparse_set(n, rng)[0]


class TestStrings(unittest.TestCase):
    def test_violation_matches_qubo_energy(self):
        rng = np.random.default_rng(70)
        for scene, ts in instances(rng):
            strings = enumerate_strings(scene, ts)
            A = float(rng.uniform(0.5, 30))
            qubo = build_qubo(scene, ts, penalty=A)
            E = energy(qubo, strings["X"])
            self.assertTrue(np.allclose(E - strings["cost"], A * strings["V"], atol=1e-7 * A))

    def test_critical_penalty_by_brute_force(self):
        rng = np.random.default_rng(71)
        positive = 0
        for scene, ts in instances(rng, n=8):
            optimum = solve_ilp(scene, ts)["cost"]
            strings = enumerate_strings(scene, ts)
            a_crit = critical_penalty(strings, optimum)
            tol = 1e-6 * max(1.0, abs(optimum))
            above = a_crit * (1 + 1e-6) + 1e-6
            e_min, _ = brute_force_minimum(build_qubo(scene, ts, penalty=above), 16)
            self.assertAlmostEqual(e_min, optimum, delta=tol)
            if a_crit > 1e-6:
                positive += 1
                e_below, _ = brute_force_minimum(build_qubo(scene, ts, penalty=0.9 * a_crit), 16)
                self.assertLess(e_below, optimum - 1e-9)
        self.assertGreater(positive, 5)

    def test_ising_conversion_reproduces_energies(self):
        rng = np.random.default_rng(72)
        for scene, ts in instances(rng, n=4):
            strings = enumerate_strings(scene, ts)
            prep = prepare(scene, ts, 3.0, strings)  # raises SystemExit on mismatch
            self.assertEqual(len(prep["h"]), len(ts.tuples))


class TestSimulator(unittest.TestCase):
    def test_matches_qiskit_statevector(self):
        rng = np.random.default_rng(73)
        for scene, ts in instances(rng, n=2):
            strings = enumerate_strings(scene, ts)
            prep = prepare(scene, ts, 5.0, strings)
            gammas, betas = rng.uniform(0, np.pi, 2), rng.uniform(0, np.pi / 2, 2)
            ours = simulate(prep["diag"], len(prep["h"]), gammas, betas)
            qc = qaoa_circuit(prep["h"], prep["J"], prep["scale"], gammas, betas)
            theirs = Statevector(qc).probabilities()
            self.assertTrue(np.allclose(ours, theirs, atol=1e-9))


class TestSelection(unittest.TestCase):
    def test_sparse_set_bounds(self):
        rng = np.random.default_rng(74)
        chosen, counts = sparse_set(10, rng)
        self.assertEqual(len(chosen), 10)
        self.assertTrue(all(6 <= len(ts.tuples) <= 12 for _, ts in chosen))
        self.assertEqual(counts["generated"], 10 + counts["rejected_no_optimum"] + counts["rejected_fewer_than_6"]
                         + counts["rejected_more_than_12"])


if __name__ == "__main__":
    unittest.main()
