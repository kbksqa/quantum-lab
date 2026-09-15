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

### Amendment 2 — 2026-09-15, after P4, decided by the author

- **Change:** a new milestone **P2.8** closes the four items that `docs/p2-summary.md` left open. Each item gets a hypothesis
  below, written before any of its code exists and before any of its numbers have been computed.
- **Trigger:** the author asked for P2 to be finished rather than left with open items.
- **Scope:**
  - Nothing registered above changes.
  - H1–H5 keep their recorded grades. H5's day half is graded separately as H5-day and does not overwrite the device half.
  - The benchmark instance file `benchmark/p2/instances.jsonl.gz` is not rebuilt or changed. New baselines are scored against
    it by a separate script and saved as new result files; the published baseline table stays as it was.
- **Only the P1.5 repeat uses QPU time**: one job of 12 circuits, about 9 s, inside the P2 budget of 3 minutes (18 s used).
  It needs the author's approval.

#### O1 — H5, day half (hardware)

- **Run:** the same 10 pure 2 × 2 instances at p = 2 as P1.5, with the same stored parameters, the same readout correction and
  2048 shots, on **`ibm_kingston`**, the P1.5 device, on a later calendar day than 2026-09-14. The device is fixed in
  advance and not chosen by that day's ranking, so that only the day changes. If `ibm_kingston` is unavailable, nothing
  is submitted and the plan is revised.
- **Order:** dry-run plan file → plan and predictions committed and pushed → author's approval → submission of exactly that
  plan.
- **H5-day:** corrected retention = hardware mean P(optimal) / simulator mean 0.5445 stays within a few points of P1.5's 0.890.
  Operationally, |retention − 0.890| ≤ 0.05 is held, ≤ 0.10 partly held, and anything larger failed.

#### O2 — generalised versus marginal likelihood as the tuple cost

- **Marginal cost:** the unknown target position is integrated out under a uniform prior over the scene window, instead of being
  replaced by its least-squares fit. For a tuple with at least one detection, the P2.0 cost becomes
  `c_marg = c_GLR + ln V − ½ ln|2π P|`. Here V is the window area and P = (Σ R_s⁻¹)⁻¹ is the covariance of the fused
  position. The Gaussian integral is taken over the whole plane; the window extends 200 m past the targets, and each
  ellipse is at most about 40 m across.
- **V:** the same window P2.0 uses for clutter, so V = clutter per sensor / clutter density. In scenes without clutter it is
  the same padded box around the targets. It is one constant per scene and does not depend on the association.
- **Kept from P2.0:** the singleton rule (cheaper of "target seen once" and "false alarm" at cost 0), the tuple set and the
  gate, so only the costs change.
- **Checks before use:**
  - the closed form matches numerical integration over the window for random tuples, to a relative 1e-6 of the likelihood
  - the ILP optimum under the new costs matches exhaustive enumeration on every tiny instance, as in P2.1
- **Instances:** all 1,620 benchmark instances, rebuilt from their seeds and checked against the stored tuples and GLR costs.
  Instances without a valid partition are counted and left out.
- **Measures:**
  - *joined clutter* — the number of clutter measurements that the optimum places in a tuple with two or more measurements
  - *optimum = truth* — whether the optimum equals the true association
- **H6 — the marginal likelihood joins less clutter and finds the truth more often.**
  - *H6a:* over instances with clutter, the per-instance joined-clutter count is lower under the marginal cost. Two-sided sign
    test on the non-zero differences: p < 0.05 in that direction is held, the right direction without significance is partly
    held, and the opposite direction is failed.
  - *H6b:* over all solvable instances, the share whose optimum equals the truth is higher under the marginal cost. The same
    grading, using an exact McNemar test on the discordant instances.
  - *Overall:* held if both parts hold, failed if both fail, partly held otherwise.
  - *Stated before the run:* the direction of H6b is uncertain. Integrating out the position penalises adding a measurement
    (a smaller P), but the ln V term counts once per target tuple, which favours fewer, larger tuples.

#### O3 — Lagrangian recovery when P_D = 1

- **Cause, found in P2.4:** recovery keeps each relaxed pair (i1, i2) and must complete it with a sensor-3 measurement, because
  (i1, i2, 0) is impossible when P_D = 1. When the gate leaves too few completions, no valid answer exists.
- **Change:** recovery may also *dissolve* a pair of two real measurements into its two singletons (i1, 0, 0) and (0, i2, 0).
  That option sits in the pair's "no sensor-3" column, which now costs the cheaper of (i1, i2, 0) and the two singletons.
  Nothing else in the method changes: the multipliers, step rule, stopping rule and 200-iteration limit stay the same.
  The original method stays in the record as registered; the new one is reported as a second method.
- **H7 — dissolving pairs removes the P_D = 1 failures without costing elsewhere.** Graded on all 1,620 benchmark instances:
  - *held* if the new method returns a valid answer on every instance that has one, is optimal on at least 8 of the 16 former
    failures, and stays optimal on every instance where the original method was optimal
  - *partly held* if it is valid everywhere but misses either of the other two conditions
  - *failed* if any instance with a valid partition still gets no valid answer

#### O4 — a QAOA objective other than ⟨H⟩

- **Objective:** CVaR_α — the mean energy of the lowest-energy α share of the output distribution — with α = 0.1, following
  Barkoutsos et al., *Improving Variational Quantum Optimization using CVaR*, Quantum 4, 256 (2020). It is computed exactly
  from the statevector, including the fractional share of the boundary energy.
- **Instances and method:** the 30 P2.5 "sparse T=2" instances, rebuilt and checked against their stored optima. Kept from
  P2.5: A = max(max|c|, 1), depths 1–3, COBYLA with 6 random starts plus an interpolated start. Only the objective changes,
  and circuits of the same depth have the same gates, so the P2.6 CZ counts still apply.
- **Comparison:** paired against the stored P2.5 ⟨H⟩ results on the same instances, by P(optimal) from the statevector.
- **H8 — CVaR raises P(optimal) on the instances where hardware already works.**
  - *held* if the mean paired difference is positive at p = 1, 2 and 3 and larger than 2 standard errors at p = 1, the depth
    that ran on hardware
  - *partly held* if it is positive at p = 1 without the rest
  - *failed* otherwise
  - No QPU time is spent on O4.

#### Order and reporting

1. **Order:** O3, O2 and O4 run on classical hardware. O1 waits for the author's approval.
2. **Reporting:** every result goes into the research log with its grade, including failures. `docs/p2-summary.md` gains an
   addendum; the original text is kept as it is.
3. **Release:** a release and DOI, which need the author's approval.
