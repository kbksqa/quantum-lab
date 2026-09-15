# Tests for P5.0. Each check uses a route that does not depend on the code being tested:
#   - a mixer rotation is compared with the matrix exponential of its Hamiltonian, built from Pauli operators with Kronecker
#     products, and the perm circuit gadget is compared with the same exponential through Qiskit's Operator
#   - the preserved spaces are counted against n^n and n!, and the energies against direct evaluation of the formula
#   - one circuit per ansatz is compared with the simulator (the full G1 runs in `python src/p5_mixers.py gates`)
#
# Run from the repository root:
#     python -m unittest discover -s tests -v

import itertools
import math
import pathlib
import sys
import unittest

import numpy as np
from qiskit import QuantumCircuit
from qiskit.quantum_info import Operator
from scipy.linalg import expm

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from p5_mixers import (  # noqa: E402
    baselines,
    circuit,
    circuit_statevector,
    energies,
    evolve,
    grade_difference,
    grade_lift,
    initial_state,
    perm_quads,
    perm_rotation,
    phase_aligned_difference,
    prepare,
    rotate,
    rxy_pairs,
    spaces,
)

I2 = np.eye(2)
SIGMA_PLUS = np.array([[0, 0], [1, 0]], dtype=complex)    # |1><0| in Qiskit's |0>, |1> basis
SIGMA_MINUS = SIGMA_PLUS.T.copy()                          # |0><1|


def on_qubits(m, ops):
    """Kronecker product with ops[q] on qubit q (Qiskit order: qubit 0 is the rightmost factor)."""
    out = np.array([[1.0 + 0j]])
    for q in reversed(range(m)):
        out = np.kron(out, ops.get(q, I2))
    return out


class TestRotations(unittest.TestCase):
    def test_xy_pair_matches_exponential(self):
        m, beta = 4, 0.37
        k, l = 1, 3
        H = on_qubits(m, {k: SIGMA_PLUS, l: SIGMA_MINUS}) + on_qubits(m, {k: SIGMA_MINUS, l: SIGMA_PLUS})
        U = expm(-1j * beta * H)
        rng = np.random.default_rng(90)
        psi = rng.normal(size=16) + 1j * rng.normal(size=16)
        ours = psi.copy()
        rotate(ours, (k,), (l,), beta)
        self.assertTrue(np.allclose(ours, U @ psi, atol=1e-12))

    def test_perm_rotation_and_gadget_match_exponential(self):
        m, beta = 4, 0.61
        a, b, c, d = 0, 3, 1, 2
        raise_ab = {a: SIGMA_PLUS, b: SIGMA_PLUS, c: SIGMA_MINUS, d: SIGMA_MINUS}
        lower_ab = {a: SIGMA_MINUS, b: SIGMA_MINUS, c: SIGMA_PLUS, d: SIGMA_PLUS}
        U = expm(-1j * beta * (on_qubits(m, raise_ab) + on_qubits(m, lower_ab)))
        rng = np.random.default_rng(91)
        psi = rng.normal(size=16) + 1j * rng.normal(size=16)
        ours = psi.copy()
        rotate(ours, (a, b), (c, d), beta)
        self.assertTrue(np.allclose(ours, U @ psi, atol=1e-12))
        qc = QuantumCircuit(m)
        perm_rotation(qc, (a, b, c, d), beta)
        self.assertTrue(Operator(qc).equiv(Operator(U)))
        self.assertTrue(np.allclose(Operator(qc).data, U, atol=1e-10))


class TestSpaces(unittest.TestCase):
    def test_sizes_and_quads(self):
        for n in (2, 3):
            s = spaces(n)
            self.assertEqual(int(s["rxy"].sum()), n ** n)
            self.assertEqual(int(s["perm"].sum()), math.factorial(n))
            self.assertEqual(len(rxy_pairs(n)), n * n * (n - 1) // 2)
            self.assertEqual(len(perm_quads(n)), math.comb(n, 2) ** 2)
            for ansatz in ("rxy", "perm"):
                psi = initial_state(n, ansatz)
                self.assertAlmostEqual(float(np.sum(np.abs(psi) ** 2)), 1.0, places=12)
                self.assertEqual(float(np.sum(np.abs(psi[~s[ansatz]]))), 0.0)

    def test_perm_quads_keep_permutations_and_connect_them(self):
        n = 3
        perms = {sum(1 << (i * n + sigma[i]) for i in range(n)) for sigma in itertools.permutations(range(n))}
        reached = set()
        for x in perms:
            for a, b, c, d in perm_quads(n):
                pattern = tuple((x >> q) & 1 for q in (a, b, c, d))
                if pattern in ((1, 1, 0, 0), (0, 0, 1, 1)):   # the rotation acts in both directions
                    y = x ^ ((1 << a) | (1 << b) | (1 << c) | (1 << d))
                    self.assertIn(y, perms)
                    reached.add(y)
        self.assertEqual(reached, perms)


class TestEnergies(unittest.TestCase):
    def test_energies_by_formula(self):
        rng = np.random.default_rng(92)
        n = 3
        C = rng.normal(size=(n, n)) * 5
        A = float(np.abs(C).max())
        E = {ansatz: energies(C, ansatz, A) for ansatz in ("xpen", "rxy", "perm")}
        for index in rng.integers(0, 1 << 9, 40):
            x = np.array([(index >> k) & 1 for k in range(9)]).reshape(n, n)
            cost = float((x * C).sum())
            rows = float(((x.sum(axis=1) - 1) ** 2).sum())
            cols = float(((x.sum(axis=0) - 1) ** 2).sum())
            self.assertAlmostEqual(E["xpen"][index], cost + A * (rows + cols), places=9)
            self.assertAlmostEqual(E["rxy"][index], cost + A * cols, places=9)
            self.assertAlmostEqual(E["perm"][index], cost, places=9)
        for ansatz in ("xpen", "rxy", "perm"):
            prep = prepare(C, ansatz, A)  # raises if the Ising form does not reproduce the energies
            self.assertAlmostEqual(float(np.abs([*prep["h"], *prep["J"].values()]).max()), prep["scale"])


class TestCircuits(unittest.TestCase):
    def test_one_circuit_per_ansatz_matches_simulator(self):
        rng = np.random.default_rng(93)
        n = 2
        C = rng.normal(size=(n, n)) * 5
        A = float(np.abs(C).max())
        for ansatz in ("xpen", "rxy", "perm"):
            prep = prepare(C, ansatz, A)
            gammas, betas = rng.uniform(0, math.pi, 2), rng.uniform(0, math.pi, 2)
            psi = evolve(prep["diag"], n, ansatz, gammas, betas)
            self.assertLess(phase_aligned_difference(psi, circuit_statevector(circuit(n, ansatz, prep, gammas, betas))), 1e-9)


class TestStudyRules(unittest.TestCase):
    def test_baselines_count_optima_by_hand(self):
        C = np.array([[1.0, 2.0, 3.0], [2.0, 4.0, 6.0], [3.0, 6.0, 9.0]])   # c_ij = (i+1)(j+1): anti-diagonal is optimal
        optimum = min(sum(C[i, s[i]] for i in range(3)) for s in itertools.permutations(range(3)))
        base = baselines(C, optimum)
        n_opt = sum(1 for s in itertools.permutations(range(3)) if abs(sum(C[i, s[i]] for i in range(3)) - optimum) < 1e-9)
        self.assertAlmostEqual(base["perm"], n_opt / 6)
        self.assertAlmostEqual(base["rxy"], n_opt / 27)
        self.assertAlmostEqual(base["all_strings"], n_opt / 512)

    def test_grading_rules(self):
        d = lambda mean, sem: {"mean": mean, "sem": sem}  # noqa: E731
        self.assertEqual(grade_difference({"p1": d(0.3, 0.1), "p2": d(0.3, 0.1), "p3": d(0.3, 0.1)}), "held")
        self.assertEqual(grade_difference({"p1": d(0.1, 0.1), "p2": d(0.3, 0.1), "p3": d(0.3, 0.1)}), "partly held")
        self.assertEqual(grade_difference({"p1": d(-0.1, 0.1), "p2": d(0.3, 0.1), "p3": d(0.3, 0.1)}), "failed")
        self.assertEqual(grade_lift(np.array([2.0, 2.2, 1.8, 2.1]))["grade"], "held")
        self.assertEqual(grade_lift(np.array([0.5, 1.8, 0.9, 1.4]))["grade"], "partly held")
        self.assertEqual(grade_lift(np.array([0.9, 1.0, 0.8, 1.05]))["grade"], "failed")


if __name__ == "__main__":
    unittest.main()
