# P5 summary — QAOA without penalties: constraint-preserving mixers for assignment

**Period:** 2026-09-15 · **Plan:** [`docs/p5-plan.md`](p5-plan.md) (pre-registered, commit `f40ecc7`, before any P5 code) ·
**Full record:** [`docs/research-log.md`](research-log.md) · **All data:** synthetic · **QPU time:** none

## The question

Every QAOA run in P1 and P2 enforced the assignment constraints with a penalty term, and most of its shots were not valid
associations. The alternative is to keep the state inside the valid answers with a constraint-preserving mixer. P5 asked:

1. Does keeping each row one-hot, or keeping whole permutations, give a higher P(optimal) than the P1 penalty formulation at
   the same depth?
2. How much of any gain comes only from searching a smaller space?
3. Does any constraint-preserving circuit for 3 × 3 fit the hardware budget used in P2 (at most 60 two-qubit gates)?

Four hypotheses (H1–H4) and a hardware go rule were fixed in advance. No quantum advantage was expected or claimed.

## What was done

| Step | What | Key check |
|------|------|-----------|
| P5.0 | Two new ansätze next to P1.4's penalty ansatz (X+pen): **R-XY** — a W state per row, XY rotations within rows, a column penalty; **PERM** — uniform over permutations, four-qubit rotations that swap the columns of two rows, no penalty | **Gates passed.** G1: 90 transpiled circuits match the simulator to 1.6 × 10⁻¹³. G2: probability outside the preserved space ≤ 1.1 × 10⁻¹⁵. G3: the P1.4 instances and angles reproduce exactly |
| P5.1 | Simulator study on the P1.4 sets (50 pure 2 × 2, 50 pure 3 × 3), depths 1–3, optimised as in P1.4; two-qubit gates on the P1.4 heavy-hex model | X+pen angles reproduced P1.4's P(optimal) to 1e-9; rotations tested against matrix exponentials |
| P5.2 | Hardware | **Skipped** — the registered go rule was not met |

115 automated tests, all passing at the end of P5.

## Hypotheses (graded on pure 3 × 3)

| | registered | result |
|---|---|---|
| H1 | R-XY gives a higher P(optimal) than X+pen at every depth, by more than 2 s.e. | **held** — +0.106, +0.092, +0.096 at p = 1, 2, 3 |
| H2 | PERM gives a higher P(optimal) than R-XY at every depth, by more than 2 s.e. | **held** — +0.41, +0.62, +0.66; higher on every instance |
| H3 | PERM does more than prepare the uniform permutation state: its lift over that state exceeds 1 by more than 2 s.e. at p = 3 | **held** — lift 5.00 ± 0.12 |
| H4 | Within 60 CZ, the best configuration is constraint-preserving | **failed** — only X+pen at p = 1 (58 CZ) fits |

## Results

**1. Constraint-preserving mixers are far better at the same depth.** Pure 3 × 3, mean over 50 instances:

| ansatz | P(optimal) p = 1 / 2 / 3 | P(feasible) at p = 1 | CZ at p = 1 |
|---|---|---|---|
| X+pen (P1.4) | 0.018 / 0.053 / 0.077 | 0.10 | 58 |
| R-XY | 0.124 / 0.145 / 0.173 | 0.70 | 105 |
| PERM | 0.536 / 0.766 / **0.833** | 1.00 | 1,217 |

On 2 × 2 the pattern is the same, but that problem is too small to separate the methods; PERM there has only two answers to
choose from.

**2. Most of the gain is the smaller search space — but not all of it.** Every instance has one optimal permutation, so
uniform guessing finds it with probability 1/512 over all strings, 1/27 over row-one-hot strings and 1/6 over permutations.
- *Lift over its own space at p = 1:* X+pen 9.0, R-XY 3.3, PERM 3.2. Measured this way, the penalty ansatz's optimisation
  contributes more than the others'. This comparison is exploratory.
- *What optimisation adds for PERM:* a registered factor of 5 at p = 3 over simply preparing the uniform permutation state.

**3. On this hardware model, the circuits are too expensive.** The breakdown below was measured after the results
(exploratory):
- *R-XY:* about 86 CZ at depth 1 even without its state preparation.
- *PERM:* one mixer layer alone needs 390 CZ, and its generic state preparation 727.

The penalty formulation remains the only one of the three that fits the 60-CZ budget, so the go rule was not met and no
hardware time was used.

## Limits

- Pure two-dimensional assignment only (P_D = 1, no clutter). The three-dimensional problem of P2 has no simple preserving
  mixer and was out of scope.
- One optimiser (COBYLA on ⟨H⟩), 50 instances per size, noiseless simulation.
- Gate counts use a generic heavy-hex model and generic state preparation. A hand-built uniform-permutation state and a native
  XY gate would lower them. The exploratory breakdown suggests that would still not bring either ansatz under 60 CZ at 3 × 3.
- No hardware run, so the effect of noise on the preserved space was not measured.

## Quantum computer time

None in P5. The project total stays at **90 seconds** of the 10-minute IBM Quantum Open Plan allowance.

## Where this points

- **P6 (roadmap):** the POMDP-planning half of QANTIS, the second pillar of the research direction.
- **Open from P5:**
  - cheaper circuits for the preserved spaces — structured permutation-state preparation, fewer swap rotations per layer, or
    devices with native XY interactions
  - a hardware run of R-XY at 2 × 2 (16–44 CZ), where it fits the budget
