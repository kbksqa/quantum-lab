# P5 plan — QAOA without penalties: constraint-preserving mixers for assignment

**Status: pre-registered on 2026-09-15.** Approved by the author and pushed before any P5 code was written or any P5 number was
computed. Same rules as P1–P3.

## Why P5 exists

Every QAOA run in this project so far enforced the assignment constraints with a penalty term.
- **P1.2–P1.4:** the penalty weight changed the results a lot, and the best choice depended on the solver.
- **P1.5 on hardware:** penalty QAOA on 3 × 3 kept P(feasible) near 0.1 at depth 1, and most shots were not valid associations.
- **P2.5:** the same held for three-dimensional instances.

The alternative is to keep the state inside the valid assignments, so no penalty is needed. The mixer — the operator that moves
amplitude between answers — is chosen so that it never leaves the set of valid answers (Hadfield et al. 2019). For one-hot
constraints this is the XY mixer (Wang et al. 2020). The question for this project is whether that pays off on the
assignment instances already studied, once the smaller search space and the extra gates are counted honestly.

## Research questions

1. On two-dimensional assignment, does a mixer that keeps each row one-hot, or one that keeps the whole assignment a
   permutation, give a higher P(optimal) than the P1 penalty formulation at the same depth?
2. How much of any gain comes only from searching a smaller space? A state that starts uniform over valid answers already
   finds the optimum with probability 1/n! (for one optimum), without any optimisation.
3. Does any constraint-preserving circuit for 3 × 3 fit the hardware budget used in P2 (at most 60 two-qubit gates)?

No quantum advantage is expected or claimed.

## Instances

The P1.4 sets, rebuilt from their seeds and checked against the stored optima:
- **Pure 2 × 2:** 50 instances, 4 qubits. The valid answers are 2 permutations.
- **Pure 3 × 3:** 50 instances, 9 qubits. The valid answers are 6 permutations.

The reference results are the stored P1.4 runs (X mixer, penalty A = max|c|, depths 1–3). They are re-simulated from their
stored angles first and must reproduce the stored P(optimal) to 1e-9.

Only synthetic data is used, as in P1.

## Ansätze compared

| name | starting state | mixer | phase operator | search space |
|---|---|---|---|---|
| **X+pen** (P1.4, stored) | uniform over all 2^(n²) strings | X on every qubit | cost + A · (row and column violations)² | all strings |
| **R-XY** | one W state per row (each row one-hot) | XY on every pair within a row, fixed order | cost + A · (column violations)², A = max\|c\| | row-one-hot strings, n^n |
| **PERM** | uniform over the n! permutations | for each pair of rows and pair of columns, a rotation that swaps the two assignments, fixed order | cost only | permutations, n! |

Details fixed now:
- **Mixer order.** The mixer is exactly the product of these two-qubit (R-XY) or four-qubit (PERM) rotations in lexicographic
  order, with one angle β per layer. That is the circuit that would run on hardware, so the simulator uses the same product and
  not the exponential of the summed Hamiltonian.
- **Row penalties in R-XY.** They are dropped because they are zero everywhere in its search space.
- **Scaling.** The phase operator is scaled by its largest Ising coefficient, as in P1.4.
- **Optimiser.** As in P1.4: COBYLA on ⟨H⟩, 6 random starts plus a start interpolated from the previous depth, depths 1–3, with
  a fixed seed. CVaR (P2.8) is not used here, so that only the mixer changes.
- **State preparation.** The W states and the uniform permutation state are prepared exactly in simulation. Their circuit cost
  is included in every gate count, using a generic synthesis, so the counts are upper bounds on a hand-optimised circuit.

## Metrics

- **Simulator measures:** P(optimal) and P(feasible) — for R-XY, the column constraints — from the statevector.
- **Two guessing baselines:**
  - uniform over all strings, as in P1
  - uniform over the ansatz's own search space: the share of optimal strings among the row-one-hot strings (R-XY) or among the
    permutations (PERM)
- **Lift:** P(optimal) divided by the ansatz's own-space baseline.
- **Estimated two-qubit gates:** after transpiling to the P1.4 heavy-hex CZ model (distance 3, optimisation level 3,
  seed 7), including state preparation.

## Checks before any study (hard gates)

- **G1:** for 5 instances of each size, every ansatz and depth, the transpiled Qiskit circuit's statevector equals the NumPy
  simulator to 1e-9.
- **G2:** with random angles, the probability outside the preserved space is below 1e-12 (R-XY: row-one-hot; PERM:
  permutations).
- **G3:** the P1.4 instances and stored angles reproduce P1.4's optima and P(optimal).

Nothing after a failed gate runs until it is fixed.

## Hypotheses, fixed in advance (graded on pure 3 × 3; 2 × 2 is reported, not graded)

Paired comparisons over the 50 instances.

- **H1 — keeping rows one-hot beats the penalty.**
  - *Test:* mean P(optimal) of R-XY minus X+pen.
  - *Held:* the difference is positive at p = 1, 2 and 3 and more than 2 standard errors at each depth.
  - *Partly held:* positive at all three depths.
  - *Failed:* otherwise.
- **H2 — keeping whole permutations beats keeping rows.**
  - *Test:* PERM minus R-XY, with the same grading as H1.
- **H3 — PERM does more than start in a smaller space.**
  - *Test:* mean lift of PERM over its own-space baseline, which is the p = 0 answer of preparing the uniform permutation state
    and measuring.
  - *Held:* the lift is above 1 by more than 2 standard errors at p = 3.
  - *Partly held:* above 1 at p = 3.
  - *Failed:* otherwise.
- **H4 — within the hardware budget, a constraint-preserving circuit is best.**
  - *Candidates:* every ansatz-and-depth pair whose median estimated CZ count over the first 5 instances is at most 60.
  - *Held:* the one with the highest mean P(optimal) is R-XY or PERM.
  - *Failed:* it is X+pen, or no constraint-preserving circuit fits the budget.
  - *Stated now:* PERM's four-qubit rotations may alone exceed 60 CZ at p = 1; that would fail H4 for PERM and is a result,
    not a reason to change the budget.

## Hardware (only if the go rule is met)

- **Go rule:** some R-XY or PERM configuration on 3 × 3 meets all three conditions:
  - a median estimated CZ count of at most 60
  - a simulator mean P(optimal) at least 2 × that of the best X+pen configuration within the same budget
  - a lift over its own-space baseline of at least 1.5

  Otherwise no QPU time is spent in P5.
- **If go:** the run follows P1.5 and P2.6:
  - the first 5 pure 3 × 3 instances, with nothing optimised on hardware
  - readout calibration circuits in the same job, 2048 shots
  - a device chosen from that day's calibration data
  - numeric predictions committed and pushed before submission
- **Reported alongside:** the share of shots that leave the preserved space, since hardware errors break the guarantee.
  A post-selected P(optimal) is reported separately and never as the headline.
- **Budget and approval:** at most 60 s of QPU time, with explicit approval from the author.

## Milestones

| ID | Milestone |
|----|-----------|
| P5.0 | Circuits and simulator for R-XY and PERM; gates G1–G3 |
| P5.1 | Simulator study on the P1.4 sets; H1–H4 and the hardware go rule |
| P5.2 | Hardware, only if the go rule is met, with predictions registered first |
| P5.3 | Summary `docs/p5-summary.md`, release and DOI |

## Out of scope

- Three-dimensional assignment with missed detections and clutter: its valid answers are not a product of one-hot or
  permutation sets, and no simple preserving mixer is planned for it.
- Warm starts, LX-mixers, Grover mixers and mixer-subset selection; CVaR objectives.
- Claims about scaling or advantage.

## Related work (checked on 2026-09-15)

- S. Hadfield, Z. Wang, B. O'Gorman, E. G. Rieffel, D. Venturelli, R. Biswas, *From the Quantum Approximate Optimization Algorithm
  to a Quantum Alternating Operator Ansatz*, Algorithms 12(2), 34 (2019) — constraint-preserving mixers, including swap mixers
  for permutations.
- Z. Wang, N. C. Rubin, J. M. Dominy, E. G. Rieffel, *XY mixers: Analytical and numerical results for the quantum alternating
  operator ansatz*, Physical Review A 101, 012320 (2020).
- F. G. Fuchs, K. O. Lye, H. M. Nilsen, A. J. Stasik, G. Sartor, *Constraint Preserving Mixers for the Quantum Approximate
  Optimization Algorithm*, Algorithms 15(6), 202 (2022).
- F. G. Fuchs, R. Pariente Bassa, *LX-mixers for QAOA: Optimal mixers restricted to subspaces and the stabilizer formalism*,
  Quantum 8, 1535 (2024).
- D. Bucher, M. Janetschek, M. Poppel, J. Stein, C. Linnhoff-Popien, S. Feld, *Constrained Quantum Optimization via Iterative
  Warm-Start XY-Mixers*, arXiv:2604.02083 (2026) — one-hot XY mixers with warm starts, Max-k-Cut and TSP, IBM hardware.
- M. Zorn et al., *Quantum Optimization Methods for the Generalized Traveling Salesman Problem*, arXiv:2604.25531 (2026) —
  XY-mixer QAOA against classical solvers.
- Y.-Z. Lei, Y. Gong, X. T. Yang, N. Attoh-Okine, *Improving Feasibility in QAOA for Vehicle Routing via Constraint-Aware
  Initialization and Hybrid XY-X Mixing*, arXiv:2604.07218 (2026) — simulation only.

**Search notes:**
- Searches on 2026-09-15 found no application of constraint-preserving mixers to measurement-to-track assignment.
- One search summary described a penalty-versus-XY comparison on `ibm_kingston`, but its source could not be identified.
  It is not cited and nothing in this plan relies on it.
