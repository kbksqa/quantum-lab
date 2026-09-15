# P6 report — reproducing QANTIS's POMDP-planning results

**Paper under study:** B. Y. Eker, Arslan, Nazlı, Demirgil, Deligöz, *QANTIS: A Hardware-Validated Quantum Platform for POMDP
Planning and Multi-Target Data Association*, arXiv:2603.00785v1 (2026).
- **Public repository:** https://github.com/neuraparse/qantis, read at HEAD `c17c2b5`. Scripts, packages and configuration
  were used from `7c6509c`, the commit dated with the paper.

**This study:**
- **Plan:** [`docs/p6-plan.md`](p6-plan.md), pre-registered before any code.
- **Source audit:** [`docs/p6-sources.md`](p6-sources.md).
- **Full record:** [`docs/research-log.md`](research-log.md).
- **Code:** `src/p6_*.py`, `tools/p6_*.py`. **Results:** `results/p6_*.json`.
- **Quantum computer time used:** 20 s.

**Scope.**
- *Covered:* the POMDP-planning half of the paper. The multi-target data association half was covered in P3
  ([`docs/p3-report.md`](p3-report.md)).
- *Not covered:* the GPS-denied grid results, the BIQAE sweep and the hardware loops.
- *Limits of the evidence:* the findings concern a published artefact and are stated as checkable facts. The authors' private
  code and raw hardware data were not available.

## Summary

- **The POMDP instance is small.**
  - *Problem:* the textbook Tiger problem (2 states), plus a 4-state belief-update example.
  - *Quantum part:* a Bayes update on 2–3 qubits and one Grover iterate on a 2-qubit belief oracle.
  - *Actions:* chosen classically, by a planner that looks one step ahead.
- **What reproduces:**
  - the belief-update circuits, which give exact Bayes posteriors
  - the Grover theory values, 0.171 → 0.917 with posterior [0.851, 0.149]
  - the closed-loop action sequences
  - **the Grover hardware result** — three replicates on `ibm_kingston` gave 0.179 → 0.906, amplification 5.05, against the
    paper's one run of 0.179 → 0.907, 5.1×
- **The advantage is smaller than stated.** The paper reports a 5.1× usable-sample yield per circuit run. Counted per
  application of the belief oracle — the quantity its O(P(e)^−1/2) argument concerns — the gain is **1.79× in theory and
  1.68× on hardware**, because the Grover circuit applies the oracle three times.
- **What does not reproduce:**
  - Table 21 does not follow the Grover formula.
  - "Hellinger < 0.15" does not mean "≤1.1% total variation".
  - The reported "ISA depth" numbers are total circuit depths, not the two-qubit gate counts the paper defines.
  - Table 6 cannot be rebuilt from the paper or produced by the public entry point.
- **Paper and public code disagree** on the pass threshold (0.15 against 0.05) and on several mitigation settings. Two
  citations are wrong.

## Claims and grades

Grades as defined in the plan: reproduced · partly reproduced · not reproduced · not reproducible · not tested.

| | claim (from the paper) | grade | evidence |
|---|---|---|---|
| C1 | Grover k = 1 theory: P(obs = 1) 0.171 → 0.917, posterior [0.851, 0.149] | **reproduced** | 0.1710 → 0.9172, [0.8509, 0.1491]; the circuit matches the reflection formula to 4 × 10⁻¹⁶ |
| C2 | the belief circuits give the exact Bayesian posterior | **reproduced** | Hellinger distance ≤ 3.3 × 10⁻¹⁶ over 41 two-state and 21 four-state priors, listen and open actions |
| C3 | "ISA depth" 12 / 18 / 162 (and 4,237) are two-qubit gate counts | **not reproduced** | On FakeMarrakesh, opt. level 3, 20 seeds: 12, 18, 13 and 4 equal the **total depth** exactly (CZ counts 2, 3, 2, 0); 162 and 4,237 match neither count (141 depth / 45 CZ; 3,602–4,035 depth / 1,420–1,496 CZ) |
| C4 | closed loops choose listen, listen, open-right, listen (T = 4) and open at t = 2 and t = 5 (T = 8) | **reproduced** | Exact posteriors with the horizon-1 planner; the public QBRL planner chooses the same action on every belief tested |
| C5 | Table 6 rewards (about 18 ± 12 for all four planners) | **not reproducible** | The public entry point prints only "avg reward −20.00" and never calls the baselines. The paper omits the rewards, discounting, what follows an open action and the tiger placement. |
| C6 | Table 21's amplified P(e) follow sin²((2G+1)θ) | **not reproduced** | For G = 1–5 the table gives 0.192, 0.485, 0.912, 0.721, 0.298; the formula gives 0.392, 0.816, 1.000, 0.804, 0.377 |
| C7 | Hellinger < 0.15 ≡ ≤1.1% total-variation distance | **not reproduced** | Total variation lies between H² and H√(2−H²). [0.5, 0.5] against [0.706, 0.294] has H = 0.1499 and TV = 20.6%. |
| HW | Grover k = 1 on IBM Heron: 0.179 → 0.907, 5.1×, posterior Hellinger 0.0015 | **reproduced** | `ibm_kingston`, 3 replicates of 8,192 shots: 0.1794 → 0.9058, 5.05×, Hellinger 0.0065; all five pre-registered predictions held |

## Questions added by this study

**Q1 — usable posterior samples per application of the belief oracle.**

| | direct circuit | Grover k = 1 | classical rejection sampling |
|---|---|---|---|
| oracle applications per shot | 1 | 3 | 1 |
| theory | 0.171 | 0.306 | 0.171 |
| our hardware (mean of 3) | 0.179 | 0.302 | — |

- **Per oracle application,** the Grover circuit gains 1.79× in theory and 1.68× on hardware.
- **Per shot,** the gain is 5.36× in theory and 5.05× on hardware — the quantity the paper reports.

**Q2 — exact Tiger baseline** (rewards from the public code, γ = 0.95).
- **Value iteration:** V*(0.5) = 19.37. The optimal policy opens a door once P(tiger behind it) < 0.0397. The paper's horizon-1
  planner opens below 0.1.
- **From a uniform start** both take identical actions, since the reachable beliefs are 0.15 and 0.030.
- **Simulated, 100 × 50 steps, seed 42, continuing after an open:** 57.6 ± 65.0 undiscounted, 21.9 ± 24.2 discounted.

**Q3 — the pass threshold.**
- *Grade changes:* of 15 reported hardware distances, only the 4-state obs-0 result (0.128) passes at the paper's 0.15 and
  fails at the code's 0.05.
- *Consistency:* the paper's distances recompute from its printed posteriors within their rounding.

## Differences between paper and public code

Each is described in `docs/p6-sources.md` with file and line references, at both commits where it matters.

1. **Pass threshold.** 0.15 in the paper; 0.05 in the loop, 4-state and Tiger scripts.
2. **"ISA depth".** Defined as a two-qubit gate count; the scripts record `.depth()`. The loop hard-codes depths "known from
   previous runs".
3. **Observation independence.** The 2-state and 4-state circuits are the same gates for either observation; the observation
   only selects the shots kept. The paper explains the 4-state obs-0 / obs-1 difference by different gate paths.
4. **Closed loop.**
   - The planner is classical with horizon 1.
   - BIQAE estimates an amplitude equal to the current belief, from a prior centred on it, and does not select actions.
   - Each step's reference uses the hardware-propagated prior, so errors cannot accumulate in the reported distances.
   - Open-door steps are H ⊗ H, uniform by construction.
5. **Simulation.** The entry point never samples a state or an observation and never calls the configured POMCP, PBVI or
   DESPOT. The QBRL "quantum" path builds a circuit and then updates classically. The baselines differ from §8.1: random
   rollouts, c = 1 rather than 25, and 100 belief points rather than 200.
6. **Mitigation.**
   - The twirling randomisation count is not set.
   - The Tiger ZNE uses scale factors [1, 1.5, 2, 3], and its code path passes an undefined name.
   - BIQAE is transpiled at level 2.
7. **Environment.** The code requires Qiskit ≥ 2.0; the paper states Qiskit 1.3.
8. **Data.** No results in the repository; the cited arXiv ancillary bundle is not listed.

**Within the paper:**
- *Iterations:* three different formulas for the optimal Grover iteration count (§5.2 gives 2 for P(e) = 0.05, Table 21 gives
  3).
- *Credible intervals:* "all 95% credible intervals cover" (§5.2) against two misses in the T = 8 loop (§8.6).

**Citations:**
- [10] is listed as an unpublished work by Aaronson alone. A published article with that title is J. Barry, D. T. Barry,
  S. Aaronson, Phys. Rev. A 90, 032311 (2014).
- [17]'s first author is Alexandra Ramôa, not "João Ramoa".

## Limits of this reproduction

- **Private material:** the private code and raw hardware data were not available. Differences are confirmed in the public
  code only.
- **Hardware:** one experiment — the smallest, 2–3 CZ — on one device on one day. The 4-state, full-circuit and loop hardware
  results were not re-run. The device differed from the paper's (`ibm_kingston` rather than `ibm_marrakesh`).
- **Circuit sizes:** these were measured on an offline backend model with Qiskit 2.5. A different version or calibration
  snapshot could change the 4-state and full-circuit depths.
- **Rewards:** the Tiger rewards come from the public code, because the paper does not give them.

## Suggestions for reporting such results

- Count quantum speed-ups in oracle applications, not in circuit runs, when the argument is about query complexity.
- Define circuit-size metrics once, and report both the two-qubit gate count and the depth.
- State the full episode protocol (rewards, discounting, resets, initial state) for simulated planning tables.
- When a pass threshold is translated into another distance, check the relation.

## Reproducing this study

```bash
python src/p6_tiger.py                                   # C1, C2, C6, C7, Q1
<separate env>/python tools/p6_repo_crosscheck.py --qantis-repo <clone> --scripts <7c6509c scripts> --out results/...
<separate env>/python tools/p6_export_circuits.py --tree <7c6509c tree> --out-dir <folder> --beliefs <json>
python src/p6_resources.py --circuits <folder>           # C3
python src/p6_loops.py                                   # C4, Q2, Q3
<separate env>/python tools/p6_table6_entrypoint.py --tree <7c6509c tree> --out results/...
python src/p6_table6.py --entrypoint results/p6_3-entrypoint-XXXX.json    # C5
python src/p6_hardware.py --dry-run                      # then --plan ..., with IBM Quantum access
python -m unittest discover -s tests
```

134 automated tests pass. Nothing from the authors' repository is copied into this repository; the cross-checks import it from
a separate clone or an extracted tree at run time.
