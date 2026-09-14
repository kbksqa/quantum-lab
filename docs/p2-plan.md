# P2 plan — multi-sensor data association as three-dimensional assignment

**Status: pre-registered on 2026-09-14, before any P2 code was written or any P2 result was seen.**
Same rule as P1: the question, the hypotheses and the success criteria are fixed first, so the results cannot reshape them.

## Why P2 exists

P1 used two-dimensional assignment on purpose. It is solvable exactly in polynomial time, which made every step checkable,
but it is not a problem that needs new methods. **Assigning measurements across three or more sensors (or scans) is a
multi-dimensional assignment problem, and it is NP-hard.** That is the problem worth benchmarking classical heuristics and
quantum methods on.

P2 also delivers what the repository roadmap promised for P2: a **reproducible benchmark** that other people can run their own
solvers against.

## Research questions

1. On synthetic multi-sensor scenes, where do classical heuristics stop reaching the exact optimum, and what makes an instance hard?
2. Does a verified QUBO formulation carry over from two to three dimensions, and do P1's penalty findings still hold there?
3. What can shallow QAOA do on the smallest three-dimensional instances — and is it worth any hardware time at all?
4. How much do P1.5's hardware numbers vary from one run, day or device to another?

No quantum advantage is expected or claimed.

## Problem

- **Scene:** T targets in a 2D region, observed at one instant by S = 3 sensors at different positions. Each sensor reports
  positions with Gaussian noise, detects each target with probability P_D, and adds Poisson clutter.
- **Hypotheses:** a tuple (i₁, i₂, i₃) says "measurement i₁ of sensor 1, i₂ of sensor 2 and i₃ of sensor 3 come from the same target",
  where index 0 means "this sensor did not see it". Every real measurement must belong to exactly one tuple; a measurement can
  also be declared a false alarm.
- **Cost:** the negative log-likelihood ratio of the tuple, with the unknown target position replaced by its weighted least-squares
  estimate from the tuple's measurements — the generalised likelihood ratio used in the S-D assignment formulation of Deb et al. (1997).
  The exact expression is written down and verified against an independent numerical computation in P2.0 before anything else uses it.
- **Gating:** tuples are kept only if their measurements pass pairwise chi-square gates, which keeps the number of variables manageable.
- **Only synthetic data**, generated from recorded seeds.

## Methods compared

| method | role |
|--------|------|
| Brute force | ground truth for tiny instances; checks everything else |
| Integer linear programming (`scipy.optimize.milp`, HiGHS) | exact optimum for every benchmark instance |
| Greedy (cheapest tuple first) | simplest classical baseline |
| Lagrangian relaxation (relax one sensor's constraints, solve 2D assignment, subgradient updates) | the standard method for S-D assignment; gives a lower bound and a feasible solution, so a duality gap |
| Simulated annealing on the QUBO | reuses the P1 routine and schedule |
| QAOA on a simulator | smallest instances only |
| QAOA on IBM hardware | only if the go/no-go rule below is met |

## Hypotheses, fixed in advance

- **H1 — hard gates.** The ILP optimum equals brute force on 100% of tiny instances, and the QUBO minimum equals the ILP optimum on
  100% of instances up to the brute-force limit. Nothing after a failed gate runs until it is fixed.
- **H2 — where heuristics fail.** Lagrangian relaxation reaches the exact optimum on most low-clutter instances, and the share of
  instances with a nonzero duality gap **rises with clutter density and with target density** (closer spacing). Instances with a gap
  form the benchmark's "hard" subset.
- **H3 — penalties are solver-dependent, again.** On three-dimensional instances small enough to enumerate, annealing does best near
  the exact critical penalty, while QAOA does better with A = max|c| than with 1.5 × A_crit — the P1 result replicates.
- **H4 — more sensors, higher ceiling.** With three sensors fusing each target, the exact optimum equals the true association in a
  **larger** share of scenes than P1.0's single-scan 82%, at comparable noise, P_D and clutter.
- **H5 — hardware repeatability.** Re-running the P1.5 2 × 2, p = 2 circuits on another day and another device gives a
  simulator-retention within a few points of P1.5's 0.890 on the best device. **Numeric predictions for any hardware run are committed
  immediately before submission,** exactly as in P1.5.

Each hypothesis is reported as held, partly held or failed.

## Milestones

| ID | Milestone |
|----|-----------|
| P2.0 | Multi-sensor scene generator, tuple cost, gating — cost verified against an independent computation |
| P2.1 | Exact ILP baseline — **gate:** equals brute force on every tiny instance |
| P2.2 | QUBO for three-dimensional assignment — **gate:** QUBO minimum equals ILP optimum up to the brute-force limit |
| P2.3 | Greedy, Lagrangian relaxation with duality gap, simulated annealing |
| P2.4 | Difficulty sweep and the benchmark package: instance files, a checker, a baseline table — release and DOI |
| P2.5 | QAOA on a simulator for the smallest instances; tests H3; decides the go/no-go for hardware |
| P2.6 | Hardware: P1.5 repeat (H5), and three-dimensional QAOA only if P2.5 passes the go rule |
| P2.7 | Summary, release, DOI |

## The benchmark (P2.4)

- **Sweep:** targets T = 2…6; clutter per sensor 0, 0.5, 1, 2; P_D 0.8, 0.9, 1.0; target spacing 25, 50, 100 m.
- **Each instance file:** seed and parameters, sensor positions, measurements, true association, allowed tuples with costs,
  exact optimum and its solution.
- **Checker:** takes any proposed association and reports validity, cost, gap to the optimum and accuracy against the truth,
  so any solver — classical or quantum — can be scored the same way.
- **Baseline table:** every classical method on every instance, plus QAOA where instances are small enough.

## Hardware rules

- **Budget:** at most 3 minutes of QPU time for all of P2, out of the 8 m 57 s remaining on 2026-09-14 (unless the allowance renews).
- **Go/no-go for three-dimensional QAOA on hardware:** on the simulator, P(optimal) must be at least 5 × guessing with an estimated
  two-qubit gate count of at most 60. Below that, no QPU time is spent on it.
- Device chosen from that day's calibration data; readout corrected as in P1.5; one job per experiment where possible.

## Carried over from P1

- Tests check results against a route that does not depend on the code being tested.
- **Every special case is counted and reported** — the lesson of the P1.2 bug, where a silent fallback removed the penalty from 6 instances.
- The research log is append-only; corrections are new entries.
- Predictions go into git before any hardware submission.

## Out of scope

- Real sensor data or operational parameters of any kind
- Tracking over time (track initiation, maintenance, termination)
- Claims about scaling or advantage

## Related work

- S. Deb, M. Yeddanapudi, K. R. Pattipati, Y. Bar-Shalom, *A generalized S-D assignment algorithm for multisensor-multitarget state
  estimation*, IEEE Transactions on Aerospace and Electronic Systems 33(2), 523–538 (1997) — S-D assignment by successive Lagrangian relaxation.
- *QANTIS: A Hardware-Validated Quantum Platform for POMDP Planning and Multi-Target Data Association* (2026), arXiv:2603.00785 —
  QUBO data association with QAOA on IBM Heron; credits Stollenwerk et al. with the first QUBO formulation of the problem for annealing.
- *Implementation of a Multiple Target Tracking Filter on an Adiabatic Quantum Computer*, arXiv:2110.08346.
- *Enhancing multiple object tracking accuracy via quantum annealing*, Scientific Reports (2025) — multi-dimensional assignment with
  dynamically adjusted penalty weights, directly relevant to H3.
- A. Lucas, *Ising formulations of many NP problems*, Frontiers in Physics 2 (2014).

## Amendments

Changes made after the plan was registered. Each one records when it was made, what triggered it, and who decided.
Everything above this section stays as originally registered.

### Amendment 1 — 2026-09-14, after P2.1, decided by the author

- **Change:** the P2.4 sweep also varies **bearing error σ_θ = 0.005, 0.01, 0.02 rad**. Range error stays at 10 m.
- **Trigger:** H4 failed in P2.1. An exploratory one-factor study then showed that bearing error was the factor with the largest
  effect on whether the optimum equals the truth (0.303 at 0.02 rad, 0.833 at 0.005 rad, T = 3).
- **Scope:** this adds a sweep dimension only. Hypotheses H1–H5, the cost function, the other sweep values, the hardware budget and
  the go/no-go rule are unchanged. H4 stays recorded as failed, and the new dimension is not used to re-test it as if it had been
  planned.
