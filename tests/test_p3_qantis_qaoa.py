# Tests for P3.2. Each check uses a route that does not depend on the code being tested:
#   - the NumPy simulator, fed unscaled QUBO energies, is compared with Qiskit's QAOAAnsatz + Statevector on the QANTIS instance,
#     with parameters bound by name
#   - the "as bound by the script" angles are compared with Qiskit when the ansatz is bound exactly as the public script does,
#     dict(zip(ansatz.parameters, interleaved_vector)) - this also checks audit finding 2.1 in the installed Qiskit
#   - the quality metric is checked on distributions whose answer is known
#
# Run from the repository root:
#     python -m unittest discover -s tests -v

import math
import pathlib
import sys
import unittest

import numpy as np
from qiskit import transpile
from qiskit.circuit.library import QAOAAnsatz
from qiskit.quantum_info import SparsePauliOp, Statevector

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from p1_qaoa import ising  # noqa: E402
from p3_qantis_qaoa import (  # noqa: E402
    GAMMA0,
    BETA0,
    bind_like_script,
    interleaved_initial,
    make_problem,
    metrics,
    probabilities,
    schedule,
    top10_quality,
)


def cost_operator(qubo):
    h, J, _ = ising(qubo)
    n = len(h)
    terms = []
    for k, value in enumerate(h):
        if value != 0:
            label = ["I"] * n
            label[n - 1 - k] = "Z"
            terms.append(("".join(label), value))
    for (k, l), value in J.items():
        label = ["I"] * n
        label[n - 1 - k] = label[n - 1 - l] = "Z"
        terms.append(("".join(label), value))
    return SparsePauliOp.from_list(terms)


def statevector_probabilities(circuit):
    # Statevector on an unsynthesised PauliEvolutionGate is extremely slow at 11 qubits; decompose to basic gates first.
    basic = transpile(circuit, basis_gates=["h", "rz", "rx", "rzz", "cx", "sx", "x"], optimization_level=0)
    return Statevector(basic).probabilities()


def by_name(ansatz, gammas, betas):
    values = {}
    for parameter in ansatz.parameters:
        name, index = parameter.name.split("[")
        values[parameter] = (gammas if name == "γ" else betas)[int(index[:-1])]
    return values


class TestSchedule(unittest.TestCase):
    def test_initial_schedule(self):
        for p in (1, 2, 3, 4):
            self.assertTrue(np.allclose(schedule(GAMMA0, p), math.pi * (np.arange(p) + 0.5) / p))
            self.assertTrue(np.allclose(schedule(BETA0, p), math.pi / 4))

    def test_interleaving(self):
        v = interleaved_initial(3)
        self.assertTrue(np.allclose(v[0::2], schedule(GAMMA0, 3)))
        self.assertTrue(np.allclose(v[1::2], schedule(BETA0, 3)))


class TestAgainstQiskit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pr = make_problem()
        cls.op = cost_operator(cls.pr["qubo"])

    def test_simulator_matches_statevector(self):
        rng = np.random.default_rng(90)
        for p in (1, 2):
            gammas, betas = rng.uniform(-0.2, 0.2, p), rng.uniform(0, math.pi / 2, p)
            ansatz = QAOAAnsatz(self.op, reps=p)
            theirs = statevector_probabilities(ansatz.assign_parameters(by_name(ansatz, gammas, betas)))
            self.assertTrue(np.allclose(probabilities(self.pr, gammas, betas), theirs, atol=1e-9))

    def test_script_binding_is_reproduced(self):
        for p in (2, 3):
            ansatz = QAOAAnsatz(self.op, reps=p)
            script_bound = ansatz.assign_parameters(dict(zip(ansatz.parameters, interleaved_initial(p))))
            theirs = statevector_probabilities(script_bound)
            gammas, betas = bind_like_script(interleaved_initial(p), p)
            self.assertTrue(np.allclose(probabilities(self.pr, gammas, betas), theirs, atol=1e-9))
            correct = statevector_probabilities(ansatz.assign_parameters(by_name(ansatz, schedule(GAMMA0, p), schedule(BETA0, p))))
            self.assertFalse(np.allclose(correct, theirs, atol=1e-6))


class TestMetric(unittest.TestCase):
    def setUp(self):
        self.pr = make_problem()

    def test_delta_on_optimum_scores_one(self):
        probs = np.zeros(len(self.pr["E"]))
        probs[self.pr["argmin"]] = 1.0
        m = metrics(self.pr, probs, np.random.default_rng(0), reps=5)
        self.assertAlmostEqual(m["quality_top10_mean"], 1.0)
        self.assertAlmostEqual(m["p_optimal"], 1.0)

    def test_delta_on_other_state_scores_its_ratio(self):
        k = int(np.argsort(self.pr["E"])[5])
        probs = np.zeros(len(self.pr["E"]))
        probs[k] = 1.0
        m = metrics(self.pr, probs, np.random.default_rng(0), reps=5)
        self.assertAlmostEqual(m["quality_top10_mean"], self.pr["E"][k] / self.pr["E_opt"])
        self.assertAlmostEqual(m["quality_top10_reversed_mean"], self.pr["E"][self.pr["rev"][k]] / self.pr["E_opt"])

    def test_top10_ignores_unsampled_states(self):
        counts = np.zeros(len(self.pr["E"]), dtype=int)
        counts[self.pr["argmin"]] = 3
        self.assertAlmostEqual(top10_quality(counts, self.pr["E"], self.pr["E_opt"], np.random.default_rng(1)), 1.0)

    def test_reversal_is_an_involution(self):
        rev = self.pr["rev"]
        self.assertTrue(np.array_equal(rev[rev], np.arange(len(rev))))
        self.assertEqual(int(rev[1]), 1 << (self.pr["n"] - 1))


if __name__ == "__main__":
    unittest.main()
