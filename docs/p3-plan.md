# P3 plan — reproduction study of QANTIS's multi-target data association result

**Status: pre-registered on 2026-09-14, before any P3 code was written or any P3 result was seen.**
Same rule as P1 and P2: the claims to test, the success criteria and the hardware rules are fixed first.

## Why this paper

The roadmap asks for a reproduction study of a published quantum tracking or planning result. Two literature searches on
2026-09-14 (recorded in the research log) looked for quantum approaches to data association in tracking:

| paper | model | why it was not chosen, or chosen |
|---|---|---|
| Eker et al., *QANTIS*, arXiv:2603.00785 (2026) | gate model, IBM Heron | **chosen** — the only gate-model tracking data-association result found; small instance (11 qubits); public repository |
| McCormick, Osborn, Angle, Streit, arXiv:2110.08346 (IEEE 2022) | D-Wave 2000Q annealing | results only as figures; no code or data; annealing-only |
| Ihara, *Sci. Rep.* 15:24294 (2025) | D-Wave Advantage2 annealing | video data no longer public; problem sizes not reported; annealing-only |
| Zaech et al., CVPR 2022, arXiv:2202.08837 | D-Wave Advantage annealing | instances far above 12 qubits; full results computed classically |
| Govaers, Stooß, Ulmke, IEEE MFI 2021 | simulated annealing | full text not read; no hardware result |

## What QANTIS reports (as read on 2026-09-14, to be re-verified in P3.0)

- **Formulation.** Binary variables x_ij (track i ↔ measurement j), plus slack variables for a missed detection (m_i) and a false
  alarm (f_j), giving n = NM + N + M. Row and column one-hot constraints are squared penalties with λ = 1.5 · max|c_ij|.
  Costs are c_ij = ½(d² + ln det 2πS), with a 9.21 gate.
- **Algorithm.** FPC-QAOA ("QAOA with a fixed number of parameters"): the angles at depth p are sampled from smooth schedules
  with k = 3 coefficients. Initial ramp γ(t) = πt, β(t) = π/4. COBYLA on a simulator; the angles are then used on hardware
  unchanged.
- **Hardware instance.** N = 2 tracks, M = 3 measurements, 11 qubits, "random-Gaussian", seed 42, stated Hungarian optimum −92.4.
- **Hardware setup.** `ibm_fez`, 4096 shots, Pauli twirling, XY4 dynamical decoupling, zero-noise extrapolation.
- **Headline claim (Table 15).** p = 3 gives a solution quality of **64.1% ± 3.3%** over three runs, with 433–435 two-qubit gates.
  Other hardware results: p = 1 35.8% (154 two-qubit gates); p = 2 with warm start 71.2%; the 19-qubit N = 3, M = 4 instance at
  p = 1, 20.4%.
- **Quality metric**, as described: the best QUBO value among the 10 most frequent bitstrings, relative to the Hungarian optimum.
  This is not P(optimal) and not an approximation ratio in the usual sense.
- **Baselines.** Hungarian (optimal) and greedy nearest-neighbour. The paper reports greedy is already optimal on the 2 × 3 instance.

## Known gaps and inconsistencies, found before starting

1. Missed-detection and false-alarm costs are not given in the paper. The public repository defaults are 5.0 and 3.0.
2. The instance data are not published. The ancillary bundle the paper cites returned 404.
3. "ISA" is defined both as two-qubit-gate depth and as two-qubit-gate count.
4. A footnote says earlier runs used a different γ schedule; which schedule produced Table 15 is unclear.
5. The paper states Apache 2.0; the repository (`neuraparse/qantis`) is MIT, is a "Community Edition", and says the hardware
   results are not included.
6. The λ = 1.5 · max|c| rule is attributed to Stollenwerk et al. The cited reference [18] is an air-traffic paper
   (arXiv:1711.04889). The rule could not be found in that paper, nor in arXiv:2110.08346, which the code cites instead.
7. The repository's bitstring evaluation may read Qiskit's little-endian bitstrings in the wrong order. Unconfirmed.

## Claims under test, and how each is graded

Each claim is graded as **reproduced**, **partly reproduced**, **not reproduced** (enough information, but a different result), or
**not reproducible** (the information needed is missing).

- **C1 — the instance.** A 2 × 3 instance rebuilt from the paper plus the public generator (seed 42, repository defaults for the
  missing costs) has an optimal association whose QUBO value is −92.4.
  - Reproduced: within ±0.05, the paper's rounding.
  - Partly: the same optimal association, a different value.
  - Not reproduced: a different optimal association.
  - Not reproducible: the generator cannot be run as described.
- **C2 — the method on a noiseless simulator.** Our FPC-QAOA, implemented from the paper, reaches a quality at p = 3 of at least
  the hardware value (≥ 64.1% − 3.3%). A noiseless simulator should not do worse than noisy hardware.
  - Reproduced: at or above that.
  - Not reproduced: below it.
  - Our implementation is also cross-checked against the repository's solver on the same instance. Any difference in the angles
    or the distribution is reported as its own finding.
- **C3 — hardware.** The p = 3 quality on IBM hardware falls within the paper's 64.1% ± 3.3% band, widened by our own run-to-run
  spread.
  - Tested only if the hardware rules below allow it; otherwise graded "not tested".
- **C4 — greedy is already optimal on the 2 × 3 instance** (a statement in the paper). Graded by direct computation.

## Questions the reproduction adds (not claims of the paper)

- **Q1 — how informative is the metric?** "Best of the 10 most frequent bitstrings" can score well without the circuit
  concentrating on good answers. We compute the same metric for uniformly random bitstrings, 1,000 simulated 4096-shot samples.
  **Decision rule, fixed now:** the headline is judged *informative* only if 64.1% exceeds the 95th percentile of that random
  baseline.
- **Q2 — standard metrics.** P(optimal), P(feasible) and the usual approximation ratio for the same distributions, so the result
  can be compared with P1 and P2.
- **Q3 — penalty rule.** λ = 1.5 · max|c| against our P1 finding for QAOA (A = max|c|), on the same instance and simulator.
- **Q4 — size.** The 19-qubit N = 3, M = 4 instance on the simulator only (C2's method, p = 1), against the paper's hardware 20.4%.

## Milestones

| ID | Milestone |
|----|-----------|
| P3.0 | Source audit: re-read the paper and the repository; pin the exact metric definition, schedule, costs and bit order; record every discrepancy with a quote or file/line reference in `docs/p3-sources.md` |
| P3.1 | Rebuild the instance (C1) and check greedy (C4); independent route: brute force over all 2^11 strings |
| P3.2 | FPC-QAOA from the paper; noiseless simulation p = 1–3; cross-check against the repository solver run in a separate environment; C2, Q1–Q3 |
| P3.3 | Q4 on the simulator |
| P3.4 | Hardware, only if the rules below are met, with predictions committed before submission (C3) |
| P3.5 | Reproduction report `docs/p3-report.md`, release and DOI |

## Hardware rules

- **Budget:** at most 3 minutes of QPU time for all of P3. The P2.6 jobs reported 81 s used in total; the dashboard figure is to
  be read before P3.4.
- **Go rule for P3.4:** C1 reproduced or partly reproduced, *and* C2 reproduced (a method that fails on a noiseless simulator is
  not worth hardware time), *and* a dry-run estimate of the QPU time within budget. Otherwise C3 is "not tested".
- **Setup:** the paper's (p = 3, 4096 shots, twirling and dynamical decoupling) as far as the documentation allows. Zero-noise
  extrapolation is included only if its cost fits the budget, and any omission is stated. Device chosen from that day's
  calibration data. Nothing is optimised on hardware.
- The author approves the QPU use explicitly, as in P1.5 and P2.6.

## Use of the authors' code

- The FPC-QAOA method and the QUBO are **re-implemented from the paper** in this repository. That is the reproduction.
- The public repository (MIT) is used only to regenerate the seed-42 instance and to cross-check our implementation. It is run
  from a separate clone outside this repository and is not copied in; any fragment that ever has to be quoted keeps its MIT notice.
- Findings that affect the paper (for example a confirmed bit-order bug or the citation error) are reported neutrally in the
  report. Contacting the authors, for example through a GitHub issue, is a public action and needs the author's approval first.

## Out of scope

- The POMDP-planning half of QANTIS.
- The 175-variable simulation results (Table 9).
- Annealing papers. Reproducing McCormick et al. on a D-Wave Leap trial is a possible later study.
- Any claim of quantum advantage.

## Sources

- Eker, Arslan, Nazlı, Demirgil, Deligöz, *QANTIS: A Hardware-Validated Quantum Platform for POMDP Planning and Multi-Target
  Data Association*, arXiv:2603.00785v1 (2026); repository https://github.com/neuraparse/qantis
- McCormick, Osborn, Angle, Streit, *Implementation of a Multiple Target Tracking Filter on an Adiabatic Quantum Computer*,
  arXiv:2110.08346; IEEE 2022, doi:10.1109/AERO53065.2022.9843451
- Ihara, *Enhancing multiple object tracking accuracy via quantum annealing*, Sci. Rep. 15:24294 (2025),
  doi:10.1038/s41598-025-07492-7
- Zaech et al., *Adiabatic Quantum Computing for Multi Object Tracking*, CVPR 2022, arXiv:2202.08837
- Govaers, Stooß, Ulmke, *Adiabatic Quantum Computing for Solving the Multi-Target Data Association Problem*, IEEE MFI 2021,
  doi:10.1109/MFI52462.2021.9591187
- Stollenwerk et al., *Quantum annealing applied to de-conflicting optimal trajectories for air traffic management*, IEEE T-ITS
  21(1) (2020), arXiv:1711.04889
