# P2 summary — multi-sensor data association as NP-hard assignment, a benchmark, and 3D QAOA on hardware

**Period:** 2026-09-14 · **Plan:** [`docs/p2-plan.md`](p2-plan.md) (pre-registered before any P2 code, one amendment) ·
**Full record:** [`docs/research-log.md`](research-log.md) · **Benchmark:** [`benchmark/p2/`](../benchmark/p2/README.md) ·
**All data:** synthetic

## The question

P1 used two-dimensional assignment on purpose: it is solvable exactly in polynomial time. P2 moved to the problem that
actually needs new methods. Several sensors observe the same targets at one instant, and their measurements must be grouped
target by target. With three sensors this is **three-dimensional assignment, which is NP-hard**. P2 asked:

1. Where do classical heuristics stop reaching the exact optimum, and what makes an instance hard?
2. Does a verified QUBO carry over to three dimensions, and do P1's penalty findings still hold?
3. What can shallow QAOA do on the smallest such instances, and is hardware time worth it?
4. How repeatable are P1.5's hardware numbers on another device?

Five hypotheses (H1–H5) were fixed in advance. No quantum advantage was expected or claimed.

## What was done

| Step | What | Key check |
|------|------|-----------|
| P2.0 | Three sensors with range and bearing errors, clutter, P_D; tuple costs as a generalised likelihood ratio; pairwise gating | Cost equals a numerical likelihood maximisation to 6 decimals; the gate rejects 0.98% of true pairs (1.00% expected) |
| P2.1 | Exact ILP (HiGHS, zero MIP gap) | **Gate passed: 888 / 888** against exhaustive partition enumeration |
| — | Plan amendment 1: bearing error added to the benchmark sweep | Recorded separately; original text unchanged |
| P2.2 | QUBO for multi-dimensional assignment | **Gate passed: 517 / 517** — QUBO minimum equals the ILP optimum |
| P2.3 | Greedy, Lagrangian relaxation, simulated annealing against the optimum | Lagrangian value matches a separate integer program; duality gap measured exactly as ILP − LP |
| P2.4 | Benchmark: 1,620 instances, checker, baselines | A second build is byte-identical |
| P2.5 | QAOA on a simulator, depth 1–3, 8–12 qubits; hardware go/no-go | Simulator matches Qiskit `Statevector`; A_crit confirmed by brute force above and below |
| P2.6 | Hardware: P1.5 circuits on another device, and 3D QAOA | Plan and five numeric predictions on GitHub before submission |

73 automated tests, all passing at the end of P2.

## Hypotheses

| | registered | result |
|---|---|---|
| H1 | ILP equals brute force, and QUBO minimum equals the ILP optimum, on 100% of checkable instances | **held** (888 / 888, 517 / 517) |
| H2 | Lagrangian relaxation reaches the optimum on most low-clutter instances; the duality-gap share rises with clutter and with closer spacing | **partly held** — "most" held at 99.5%; both "rises" only in direction, intervals overlapping |
| H3 | Annealing does best near A_crit; QAOA does better with max\|c\| than with 1.5 × A_crit | **partly held** — annealing part held; QAOA part clear on pure instances, not on the typical sparse one |
| H4 | Three fused sensors make the optimum equal the truth more often than P1.0's 82% | **failed** — 27% at T = 3 |
| H5 | Re-running the P1.5 circuits on another day and device keeps retention within a few points of 0.890 | **partly held** — another device: 0.892; another day: not tested |

## Results

**1. The formulations are right.** The ILP matched exhaustive enumeration on 888 instances and the QUBO matched the ILP on 517.
Every special case — tuples cut by the gate, infeasible scenes, degenerate penalties — was counted rather than dropped.

**2. The optimum is often not the truth, and P2 found out why.** At T = 3 the exact optimum equalled the true association in only
27% of scenes, against 82% in P1. A one-factor study, labelled exploratory because it came after the result, pointed to
40 m cross-range errors. Reducing bearing error to about 10 m raised the share to 83%, and to 93% without clutter as well.
The deeper reason is structural: P1 associated measurements with tracks whose predicted positions were known, while a snapshot
has no such anchor. The hypothesis compared two situations that were not comparable.

**3. Lagrangian relaxation is the classical baseline to beat.** Over the 1,620 benchmark instances:

| method | optimal | valid |
|---|---|---|
| Lagrangian relaxation | **0.987** | 0.990 |
| simulated annealing (64 × 100 sweeps) | 0.633 | 1.000 |
| greedy | 0.527 | 0.987 |
| greedy, per-measurement normalised | 0.415 | 0.987 |

Even on the 43 instances with a nonzero duality gap, Lagrangian relaxation found the optimum 88% of the time. Its failures are
concentrated where recovery cannot complete pairs (P_D = 1 with clutter). Annealing falls from 0.96 at T = 2 to 0.35 at T = 6.

**4. Penalty choice is solver-dependent — again, with a caveat.** Annealing did best at 1.1–1.5 × A_crit in both instance sets.
QAOA preferred the larger max|c| clearly on pure 8-qubit instances (p = 3: 0.069 against 0.030, better on 97% of instances).
On sparse instances the mean favoured max|c|, but three instances carried it and the median went the other way.
A = max|c| also needs a positive floor: it vanishes when every tuple costs 0.

**5. Three-dimensional QAOA fits hardware only when it is small and sparse.** The registered go rule — at least 5× guessing with
at most 60 CZ — was met only by sparse instances at depth 1. Pure 8-qubit instances need 85 CZ even at p = 1.

**6. On hardware, shallow circuits kept essentially all of their simulator signal.**

| experiment | device | CZ | simulator P(opt) | hardware (corrected) | retention |
|---|---|---|---|---|---|
| P1.5 circuits, 2 × 2 p = 2 | `ibm_fez` | 22 | 0.5445 | 0.4856 | 0.892 |
| same circuits in P1.5 | `ibm_kingston` | 22 | 0.5445 | 0.4847 | 0.890 |
| 3D QAOA, p = 1, 10 sparse instances | `ibm_kingston` | 8–57 | 0.0164 | 0.0173 | 1.05 — 15.7× guessing |

Of five numeric predictions, three held. A2 ("fez below kingston") failed by 0.0009, inside the shot noise. B2 missed its upper
bound by 0.0015, also inside the shot noise.

## Corrections and deviations during P2

Kept in the log as they happened, not rewritten:
- **H4's reasoning was wrong** (P2.1). The comparison with P1.0 ignored that tracks provide prior positions and a snapshot does not.
- **Plan amendment 1** added bearing error to the benchmark sweep after P2.1 showed it mattered most. H4 was not re-tested
  under it.
- **Cost convention.** Dropping ln λ without clutter leaves the optimum unchanged but made greedy pick only singletons (P2.3).
  A normalised variant was added in P2.4; it helps only without clutter.
- **Lagrangian recovery fails at P_D = 1 with clutter** — 16 benchmark instances, not seen in P2.3's P_D = 0.9 runs.
- **H5 ran on the same calendar day as P1.5,** so only its device half was tested. This was stated before submission.
- **A JSON serialisation crash in P2.3** was fixed and the run repeated. Every number reproduced.

## Limits

- Snapshot association with three sensors; no tracking over time.
- One cost model: the generalised likelihood ratio fits the target position to the very measurements it scores. Whether a
  marginal likelihood would join less clutter was not tested.
- Synthetic scenes from one generator. Sensor geometry is fixed; only noise, clutter, P_D and spacing vary.
- QAOA used ⟨H⟩ with COBYLA, 30 instances per set, with CZ counts estimated on a generic heavy-hex model before the device
  transpile.
- Hardware: one job per device, 10 instances each, one calibration window, one day. Retention is unreliable when the simulator's
  P(opt) is near guessing.

## Quantum computer time

P2 used **18 seconds** (9 s per job, as reported by the jobs), well inside its 3-minute budget. The whole project has used
**81 seconds** of the 10-minute IBM Quantum Open Plan allowance. The dashboard was not read after P2.6.

## Where this points

- **P3 (roadmap): a reproduction study.** Take a published QUBO or QAOA formulation of multi-target data association and rerun it
  on this benchmark, scored by the same checker against Lagrangian relaxation.
- **Open from P2:**
  - the day half of H5
  - generalised against marginal likelihood as the tuple cost
  - a recovery step for Lagrangian relaxation that handles P_D = 1
  - QAOA objectives other than ⟨H⟩ on the sparse instances where hardware already works

## Addendum — P2.8, 2026-09-15: the open items closed

Added after P4, at the author's request, so that P2 ends with no open items. The text above is unchanged. Hypotheses were
registered in Amendment 2 of the plan (commit `89315eb`, pushed before any P2.8 code existed); details are in the research log.

| item | hypothesis | grade | in one line |
|---|---|---|---|
| O1 — P1.5 circuits again on `ibm_kingston`, a later day | H5-day | **held** | corrected retention 0.875 against 0.890 — but raw retention was 0.625, because one qubit misread "0" as "1" in 75% of calibration shots |
| O2 — marginal likelihood instead of GLR as the tuple cost | H6 | **partly held** | joins 303 clutter measurements instead of 670, but finds the truth equally often (63 against 62 discordant instances) |
| O3 — Lagrangian recovery that may dissolve pairs | H7 | **held** | valid on every solvable instance; optimal 0.997 instead of 0.987; all 16 former failures now optimal, none lost |
| O4 — CVaR₀.₁ instead of ⟨H⟩ as the QAOA objective | H8 | **partly held** | P(optimal) at p = 1 from 0.0126 to 0.0301 (+4.7 s.e.), but lower at p = 3 (0.104 against 0.156) |

What changes in the conclusions above:
- **Result 3:** Lagrangian relaxation with dissolved recovery is now the classical baseline to beat — 0.997 optimal, never
  invalid. The benchmark files are unchanged; the new scores are in `results/p2_8-benchmark-20260915-102524.json`.
- **Limits, cost model:** the marginal likelihood was tested. It removes most clutter joins but, on this benchmark, does not
  bring the optimum closer to the truth; by setting it moved the truth share both up and down (exploratory).
- **Result 5:** at the depth that fits hardware, a CVaR objective gives more than twice the P(optimal) of ⟨H⟩ on the sparse
  instances. It was not run on hardware.
- **Result 6 and H5:**
  - *Repeat on another day:* on 2026-09-15 the same circuits on `ibm_kingston` kept 0.875 after readout correction, close to
    0.890 the day before. With P2.6's other-device run (0.892), both halves of H5 have now been tested; the grade recorded
    in P2 is not rewritten.
  - *Readout on the day:* one qubit in the chosen layout read almost always "1" during the job, although the device's
    calibration data from that morning reported a normal readout error for it. The in-job calibration caught this, and the
    raw retention (0.625) shows how much the correction mattered.
  - *Lesson:* a device's reported calibration is not a substitute for calibration circuits in the same job.

P2.8 used **9 seconds** of QPU time, bringing the project total to **90 seconds** of the 10-minute IBM Quantum Open Plan
allowance.
