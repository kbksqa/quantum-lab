# P1 plan — measurement-to-track association as a QUBO

**Status: pre-registered on 2026-09-14, before any P1 code was written or any P1 result was seen.**
Writing the plan and the success criteria down first is deliberate: the results cannot quietly reshape the question.

## Research question

When measurement-to-track association is written as a QUBO, how do an exact classical solver, a classical
heuristic, and QAOA compare — and what does it cost (penalty weights, qubits, circuit depth, hardware noise)
to make the quantum version return *valid* associations at all?

## Why P1 starts with the easy case on purpose

- **Two-dimensional assignment** (one scan: tracks × measurements) is solvable exactly in polynomial time with
  the Hungarian method. No quantum method can beat that, and P1 does not try to. Its value is that the true
  optimum is always known, so the encoding, the penalty weights and the metrics can be checked exactly.
- **Multi-dimensional assignment** (three or more scans or sensors) is NP-hard. That is the problem worth
  studying with quantum and quantum-inspired methods, and it is the target of P2 onward.
- **No quantum advantage is expected or claimed in P1.**

## Problem instances

- Synthetic scenario: T targets with constant-velocity motion in 2D, Gaussian measurement noise σ,
  detection probability P_D, clutter drawn from a Poisson process with spatial density λ, one scan.
- Chi-square gating on the innovation, and the standard negative log-likelihood cost
  c_ij = ½·d²_ij + ½·ln|2πS| − ln(P_D / λ), with a missed-detection cost c_i,miss = −ln(1 − P_D).
- Missed detections and clutter handled by padding the cost matrix with dummy rows and columns, so both
  assignment constraints become equalities.
- **Only synthetic or public data.** The generator records its seed so every instance can be rebuilt.

## QUBO encoding

Binary variable x_ij = 1 when row i is assigned to column j of the padded n × n matrix:

E(x) = Σ_ij c_ij·x_ij + A·Σ_i (Σ_j x_ij − 1)² + A·Σ_j (Σ_i x_ij − 1)²

Qubits = n²: 2 × 2 → 4, 3 × 3 → 9, 4 × 4 → 16.

## Solvers compared

1. **Hungarian** (`scipy.optimize.linear_sum_assignment`) — exact reference optimum.
2. **Brute force over the QUBO** (up to 16 variables) — confirms that the QUBO minimum is the Hungarian optimum.
3. **Simulated annealing on the QUBO** — own seeded NumPy implementation, classical heuristic baseline.
4. **QAOA on a simulator**, depth p = 1, 2, 3, with parameters optimised on the simulator.
5. **QAOA on IBM hardware** for 2 × 2 (4 qubits) and 3 × 3 (9 qubits): parameters fixed from step 4,
   sampling only, with the readout correction developed in P0.5.

## Metrics

- **P(optimal)** — probability of sampling the Hungarian-optimal assignment.
- **Feasibility rate** — share of samples that are valid assignments.
- **Approximation ratio** — cost of the best feasible sample divided by the optimal cost.
- **Association accuracy against ground truth** — reported separately, because under noise the optimum of
  the cost is not always the true association.
- **Resources** — qubits, transpiled two-qubit gates, depth, QPU seconds.

## Milestones

| ID | Milestone |
|----|-----------|
| P1.0 | Scenario generator, cost matrix, Hungarian baseline, tests |
| P1.1 | QUBO builder + brute-force check against Hungarian on random instances |
| P1.2 | Penalty study: how large A must be for feasibility, and what larger A does to the energy landscape |
| P1.3 | Simulated annealing baseline |
| P1.4 | QAOA on a simulator, p = 1..3 |
| P1.5 | QAOA on hardware (2 × 2, 3 × 3) with readout correction |
| P1.6 | Write-up, release, DOI |

## Success criteria, fixed in advance

- **P1.1 is a hard gate:** the QUBO minimum must equal the Hungarian optimum on 100% of test instances.
  Anything less means the encoding or the penalty weight is wrong, and nothing after P1.1 runs until it is fixed.
- **P1.3–P1.5:** success is a clear, reproducible comparison with honest error bars — not beating Hungarian.

## QPU budget

Parameter optimisation happens only on the simulator. Hardware jobs are fixed-parameter sampling runs, expected
to cost tens of QPU seconds in total — well inside the free Open Plan allowance.

## Out of scope for P1

- Multi-scan or multi-sensor assignment (P2)
- Large instances or claims about scaling
- Any operational data

## Related work

- A. Lucas, *Ising formulations of many NP problems*, Frontiers in Physics 2 (2014) — penalty encodings for
  constrained problems. arXiv:1302.5843
- *QANTIS: A Hardware-Validated Quantum Platform for POMDP Planning and Multi-Target Data Association* (2026) —
  QUBO-based data association with QAOA on IBM hardware; the natural candidate for the P3 reproduction study.
  arXiv:2603.00785
- Multidimensional assignment problems in multitarget and multisensor tracking — NP-hard for three or more
  dimensions, while two-dimensional assignment is polynomial.
