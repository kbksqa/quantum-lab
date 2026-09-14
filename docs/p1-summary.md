# P1 summary — measurement-to-track association as a QUBO, from exact solver to real hardware

**Period:** 2026-09-14 · **Plan:** [`docs/p1-plan.md`](p1-plan.md) (pre-registered before any P1 code) ·
**Full record:** [`docs/research-log.md`](research-log.md) · **All data:** synthetic, in `results/`

## The question

When measurement-to-track association is written as a QUBO, how do an exact classical solver, a classical heuristic
and QAOA compare — and what does it cost (penalty weights, qubits, circuit depth, hardware noise) to make the quantum
version return valid associations at all?

P1 deliberately used **two-dimensional (single-scan) assignment**, which the Hungarian method solves exactly in polynomial
time. The point was not to beat it but to have the true optimum available at every step. No quantum advantage was expected
or claimed.

## What was done

| Step | What | Key check |
|------|------|-----------|
| P1.0 | Textbook tracking scenarios (CV Kalman prediction, P_D = 0.9, clutter, χ² gating), GNN cost matrix, Hungarian baseline | Hungarian equals direct enumeration on 240 random scenes; cost equals SciPy's Gaussian log-density |
| P1.1 | QUBO builder, one variable per allowed cell, provably safe penalty A = 2·Σ\|c\| + 1 | **Hard gate passed: 588 / 588** instances where the QUBO minimum equals the Hungarian optimum (up to 20 variables) |
| P1.2 | Exact critical penalty A_crit from enumeration; energy gap and simulated annealing across penalties | Threshold verified just above and just below A_crit |
| P1.3 | Annealing baseline, a computable penalty rule, instances beyond brute force | Rebuilt P1.2 instances match the committed file to 9 decimals |
| P1.4 | QAOA on a simulator, depth 1–3, 4 and 9 qubits | NumPy simulator matches Qiskit `Statevector` |
| P1.5 | QAOA on `ibm_kingston`, simulator parameters, no retuning | Predictions committed 17 seconds before the job was submitted |

29 automated tests, all passing at the end of P1.

## Results

**1. The encoding is right.** The QUBO minimum equalled the exact optimum on every one of 588 instances checked, and a
pruning of the augmented matrix's dummy block cut variables by about a quarter on 3-target scenes without changing any optimum.

**2. The optimum is not the truth.** Even the exact solver returned the true association in only 82% of realistic 3-target
scenes (92% with perfect detection and no clutter). Every solver in P1 was therefore scored against the *optimum*.

**3. The provably safe penalty is expensive.** It overshoots the exact threshold by a median of 47× (3 × 3) and 106× (4 × 4).
With it, annealing finds the optimum 3.6× (3 × 3) and 12× (4 × 4) less often than at the best penalty.

**4. The best penalty depends on the solver.**

| 3 × 3 instances (same 50 throughout) | annealing, per restart | QAOA p = 3, per sample (simulator) |
|--------------------------------------|------------------------|------------------------------------|
| A = 1.5 × A_crit (annealing's sweet spot) | 0.641 | 0.029 |
| A = max\|c\| (computable) | 0.355 | **0.077** |
| A = 2·Σ\|c\| + 1 (safe) | 0.190 | — |

Annealing does best near the exact threshold; QAOA does best with the larger computable rule, and at annealing's sweet spot
QAOA is almost always infeasible. A penalty recommendation for one solver cannot be reused for another.

**5. Size decides where quantum can run.** Realistic 3-target scenes need tens of binary variables. Noiseless QAOA at p = 3
finds the optimum 58% of the time on 4 qubits but 7.7% on 9 qubits, and 9-qubit p = 3 needs about 238 CZ gates.
Annealing itself struggles on dense 36-variable instances (the best of 64 restarts finds the optimum in only two thirds of them).

**6. Shallow QAOA transferred to hardware well.** On `ibm_kingston`, chosen by today's calibration data:

| circuit | CZ gates | P(optimal) simulator | hardware (readout-corrected) | kept |
|---------|----------|----------------------|------------------------------|------|
| 2 × 2, p = 1 | 11 | 0.2140 | 0.1962 | 92% |
| 2 × 2, p = 2 | 22 | 0.5445 | 0.4847 | 89% |
| 3 × 3, p = 1 | 58 | 0.0201 | 0.0180 | 90% |

p = 2 beat p = 1 on all 10 hardware instances, and the 9-qubit circuit stayed 9× above guessing.

## Corrections made during P1

Kept in the log as they happened, not rewritten:
- **P1.2 reported an anomaly that was a bug in my study code.** A fallback of 10⁻⁶ left 6 of 50 instances without any
  penalty. Found and confirmed in P1.3; the hypothesis offered in P1.2 was withdrawn.
- **P1.2's penalty advice did not transfer to QAOA** (P1.4).
- **P1.4 expected the 9-qubit hardware run to be dominated by noise.** It kept about 90% of the simulator value (P1.5).

## Limits

- Two-dimensional assignment only — the easy case, by design.
- Hardware: one job, one device, one calibration window; 10 instances (2 × 2) and 5 (3 × 3).
- QAOA optimised ⟨H⟩ with COBYLA; other objectives (e.g. CVaR) were not tried.
- Annealing results depend on the stated temperature schedule.
- Readout correction assumed independent errors between qubits on 9-qubit circuits.

## Quantum computer time

The whole project so far used **63 seconds** of the 10-minute IBM Quantum Open Plan allowance: about 9 seconds for the P0
sweep, and 54 seconds for P0.5 and P1.5 together (169,984 shots; they were not read separately).

## Where this points

The problem that actually needs new methods is **multi-dimensional assignment** — three or more scans or sensors — which is
NP-hard. That is the natural subject of P2, together with repeated hardware runs across days and devices so the results carry
error bars across runs, not only across instances.
