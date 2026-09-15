# P6 plan — reproduction study of QANTIS's POMDP-planning results

**Status: draft for the author's approval, written on 2026-09-15.** It becomes the pre-registration when it is approved and
pushed, before any P6 code is written or any P6 number is computed. Same rules as P3.

## Why this study

P3 reproduced the multi-target data association half of QANTIS (arXiv:2603.00785) and left its POMDP-planning half out of
scope. Planning under uncertainty is the second part of this project's research direction, and the paper is the only
hardware-validated quantum POMDP result found in the P3 searches. P6 applies the P3 method to that half: rebuild what the
paper describes, check each claim on a noiseless simulator, add exact classical baselines, and use hardware only if a
registered go rule allows it.

**Expectation, stated now.** A first read suggests that the POMDP half is small. Its instances are the textbook Tiger problem
(2 states) and a 4-state belief-update example. Its circuits have 2–3 qubits, plus one 11-qubit framework circuit. P6 is
therefore planned as a short study.

## What the paper reports (first read on 2026-09-15, to be re-verified in P6.0)

- **Instances:**
  - Tiger: 2 states, 3 actions, 2 observations, discount 0.95, listening correct with probability 0.85. Rewards appear in the
    public code (−1 / −100 / +10), not in the paper.
  - A "4-state Corridor Tiger" with only a listen action and P(hear-left | state) = [0.85, 0.70, 0.30, 0.15].
  - GPS-denied grids (simulation only).
- **Quantum parts:**
  - a quantum Bayes belief update on 2–3 qubits (and an 11-qubit framework circuit)
  - one Grover amplitude-amplification iterate on a 2-qubit belief oracle
  - Bayesian amplitude estimation (BIQAE) on a 1-qubit oracle
  - Actions are chosen classically.
- **Headline hardware claims (`ibm_marrakesh`, February 2026):**
  - Grover k = 1 with prior [0.97, 0.03]: P(target observation) 0.179 → 0.907 (theory 0.171 → 0.917), "5.1×", post-selected
    posterior [0.849, 0.151] against exact [0.851, 0.149].
  - Tiger 2-qubit circuit: Hellinger distance 0.025 / 0.014.
  - 4-state circuit: 0.128 / 0.044.
  - Closed loops of T = 4 and T = 8 steps with maximum Hellinger 0.0169 and 0.0149.
- **Pass criterion in the paper:** Hellinger distance < 0.15, described as "≤1.1% total-variation distance".
- **Simulated planning (Table 6):** reward — POMCP 18.3 ± 12.7, DESPOT 19.1 ± 11.4, PBVI 17.6 ± 13.2, QBRL 18.7 ± 12.1.

## Gaps found by the first read (each to be confirmed or withdrawn in P6.0 with a quote or file/line reference)

1. **No data.** The repository has no hardware or simulation results. The cited ancillary bundle is not listed on arXiv.
   Only one IBM job ID is given.
2. **Pass threshold.** The scripts' pass threshold is 0.05, not 0.15. Under 0.05 the 4-state result 0.128 would fail.
3. **Circuit depth.** "ISA depth" is defined as a two-qubit gate count, but the scripts record the total circuit depth.
4. **Hellinger and total variation.** Hellinger 0.15 cannot mean at most 1.1% total variation, because total variation is at
   least H².
5. **Table 6.** The simulation entry point never samples a hidden state or an observation and never updates the belief, so it
   cannot produce Table 6. The POMCP and DESPOT baselines in the code do not implement particles or search trees.
6. **Table 21.** Its amplified probabilities do not match sin²((2G + 1)θ), and its iteration count differs from §5.2.
7. **Oracle calls.** The Grover circuit calls the oracle three times, so "5.1× usable samples" counts circuit runs, not oracle
   calls.
8. **Error mitigation.** The twirling count, ZNE scale factors and transpiler level differ between paper and code. One ZNE
   branch references an undefined name.
9. **Citations to check:** [10] (Aaronson, "unpublished"), [17] (first author's name), [4] (no arXiv number), [12] ("NeurIPS"
   for 2010).

## Claims under test, and how each is graded

Grades as in P3: **reproduced**, **partly reproduced**, **not reproduced** (enough information, but a different result), **not
reproducible** (information missing).

- **C1 — Grover k = 1 on the 2-qubit Tiger oracle (noiseless).** The paper's theory values are P(target observation) 0.171 →
  0.917 and posterior [0.851, 0.149].
  - Reproduced: our circuit, built from the paper, gives these values to the paper's rounding (±0.0005).
  - Partly reproduced: within ±0.005.
  - Not reproduced: otherwise.
- **C2 — exact belief updates (noiseless).** The 2-qubit Tiger circuit and the 3-qubit 4-state circuit produce the exact Bayes
  posterior after post-selection, for both observations.
  - Reproduced: Hellinger distance below 1e-9.
- **C3 — circuit sizes.** The reported 12 (Tiger listen), 18 (Grover) and 162 (4-state) are two-qubit gate counts, as the paper
  defines them, after transpiling at optimisation level 3 to an offline IBM Heron r2 model (`FakeMarrakesh` or `FakeFez`).
  - Reproduced: the stated number lies within the range of two-qubit gate counts over 20 transpiler seeds.
  - Partly reproduced: it lies within the range of total depths instead.
  - Not reproduced: neither.
  - The 11-qubit framework circuit (4,237) is checked the same way if the public code can build it; otherwise not
    reproducible.
- **C4 — closed-loop action sequences.** With the one-step planner the paper describes, exact belief updates and the stated
  observation sequences, the loops choose these actions:
  - T = 4: listen, listen, open-right, listen
  - T = 8: open-right at t = 2 and open-left at t = 5

  Graded per loop.
- **C5 — Table 6.** The public entry point, or a protocol fully determined by the paper, gives the table's rewards within
  their stated spreads. Expected in advance: not reproducible (the episode protocol is not given).
- **C6 — Table 21.** The amplified probabilities follow sin²((2G + 1)θ) for the stated P(e) and G. Graded by direct
  computation.
- **C7 — the pass criterion.** "Hellinger < 0.15 ≡ ≤1.1% total variation". Graded by the exact relation between the two
  distances; for two-outcome distributions it is computed directly.

## Questions the reproduction adds (not claims of the paper)

- **Q1 — cost per usable sample.** Usable posterior samples per oracle call for:
  - the direct belief circuit
  - the Grover k = 1 circuit
  - classical rejection sampling from the same prior
- **Q2 — exact Tiger baseline.** The optimal policy and value by value iteration on the belief interval, compared with the
  one-step planner used in the hardware loop. The simulated reward of both is reported under explicitly stated episode
  protocols.
- **Q3 — threshold sensitivity.** Which of the paper's hardware results change grade between thresholds 0.15 and 0.05.

## Milestones

| ID | Milestone |
|----|-----------|
| P6.0 | Source audit: re-read the paper's POMDP sections and the public code; confirm or withdraw every gap above with a quote or file/line reference in `docs/p6-sources.md`; verify the POMDP references |
| P6.1 | Circuits rebuilt from the paper; C1, C2, C6, C7 and Q1 on a noiseless simulator; cross-check against the public scripts run in a separate environment, in dry-run mode |
| P6.2 | C3 (offline transpilation), C4 (loops) and Q2–Q3 |
| P6.3 | C5: an attempt to reproduce Table 6 |
| P6.4 | Hardware, only if the go rule below is met, with predictions committed first |
| P6.5 | Reproduction report `docs/p6-report.md`, release and DOI |

## Hardware rules

- **Budget:** at most 60 s of QPU time for all of P6. The project has used 90 s so far.
- **Go rule for P6.4:** all of the following, otherwise the hardware claims are "not tested":
  - C1 reproduced
  - C3 at least partly reproduced for the Grover circuit
  - a dry-run QPU-time estimate for three replicates of the Grover k = 1 experiment within budget
- **Scope if go:**
  - *Experiment:* only the Grover k = 1 experiment — baseline and Grover circuits, 8,192 shots, three replicates — with the
    paper's mitigation (twirling and dynamical decoupling) as far as the documentation allows; any omission stated.
  - *Circuits and device:* nothing optimised on hardware; the device chosen from that day's calibration data.
  - *Readout:* calibration circuits in the same job, as in every earlier hardware run of this project.
- **Approval:** the author approves the QPU use explicitly.

## Use of the authors' code

- **The reproduction:** the circuits and the Tiger model are **re-implemented from the paper**.
- **Public repository (MIT):** used only to fill parameters the paper omits (such as the rewards) and to cross-check. It runs
  from the separate clone outside this repository and is not copied in.
- **Findings:** reported neutrally in the report. Contacting the authors again — as after P3 — is a separate action and needs
  the author's approval.

## Out of scope

- The GPS-denied grid results (Table 7), the BIQAE sweep (Table 13) and the BIQAE hardware results.
- Hardware runs of the full 11-qubit circuit and of the closed loops.
- Code added to the repository after the paper (`run_vns_tiger.py`, `decision_engine.py`, `risk.py`, `verify.py`).
- Any claim of quantum advantage.

## Sources

- Eker, Arslan, Nazlı, Demirgil, Deligöz, *QANTIS: A Hardware-Validated Quantum Platform for POMDP Planning and Multi-Target
  Data Association*, arXiv:2603.00785v1 (2026); repository https://github.com/neuraparse/qantis (clone at `c17c2b5`; the paper-date
  commit `7c6509c` is used for any comparison that depends on code changed since).
- L. P. Kaelbling, M. L. Littman, A. Cassandra, *Planning and acting in partially observable stochastic domains*, Artificial
  Intelligence 101, 99–134 (1998) — the Tiger problem.
- G. Brassard, P. Høyer, M. Mosca, A. Tapp, *Quantum amplitude amplification and estimation*, Contemporary Mathematics 305,
  53–74 (2002).
- Further POMDP-method references of the paper ([4], [5], [10], [12], [13], [17], [30]) are verified in P6.0 before use.
