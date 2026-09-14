# P3 report — reproducing QANTIS's multi-target data association result

**Paper under study:** B. Y. Eker, Arslan, Nazlı, Demirgil, Deligöz, *QANTIS: A Hardware-Validated Quantum Platform for POMDP
Planning and Multi-Target Data Association*, arXiv:2603.00785v1 (2026). Public repository
https://github.com/neuraparse/qantis at commit `c17c2b5`.

**This study:** plan [`docs/p3-plan.md`](p3-plan.md) (pre-registered before any code) · source audit
[`docs/p3-sources.md`](p3-sources.md) · full record [`docs/research-log.md`](research-log.md) · code `src/p3_*.py`,
`tools/p3_repo_crosscheck.py` · results `results/p3_*.json` · **quantum computer time used: 0 s**.

**Scope.** Only the paper's multi-target data association (MTDA) results were examined. Its POMDP-planning results were not.
The findings below concern a published artefact and are stated as checkable facts. The authors' private code (the repository calls
it the Collaborator Edition) and raw hardware data were not available, so nothing here says what that code did.

## Summary

- **The instances and their optimal values reproduce exactly.** An independent re-implementation gives QUBO matrices identical to
  the authors' public code for both hardware instances. The optimal values −92.35 and −131.98 match the paper's −92.4 and −132.0.
- **They reproduce only with a cost term the paper does not state.** The code adds ln(clutter density) to every association cost.
  With the paper's cost equation the small instance has optimum −32.85 and a different optimal association.
- **The method works on a noiseless simulator** at the level the claim requires: quality 0.836 at p = 3, against the hardware's
  64.1%.
- **The headline metric does not distinguish QAOA from random sampling on this instance.**
  - The metric is the best of the 10 most frequent bitstrings, divided by the optimum.
  - Uniformly random bitstrings score 64.1% or more in 43% of 4096-shot samples; their 95th percentile is 86.6%.
  - On the 19-variable instance the paper's hardware values (20.4% and 11.5%) are at the level of random sampling (mean 15.0%).
- **P(optimal)**, which the paper does not report, stays near the uniform level at every depth the paper reports.
- **Three defects in the public hardware and solver code were confirmed:**
  1. angles bound to the wrong parameters on the initial-schedule path
  2. bitstrings evaluated in mirror order
  3. a solver that trains all 2p angles rather than a fixed number of schedule coefficients
- **The hardware claim was not re-run.** The registered hardware metric could not have confirmed or refuted anything.

## Claims and grades

Grades as defined in the plan: reproduced · partly reproduced · not reproduced · not reproducible · not tested.

| | claim (from the paper) | grade | evidence |
|---|---|---|---|
| C1 | The 2 × 3 instance has Hungarian optimum −92.4 | **reproduced** (caveat) | −92.3549, the unique minimum over all 2,048 strings; Q identical to the authors' code. Needs the code's ln(clutter) cost term, absent from the paper's equation (§6.1), which gives −32.85. |
| C2 | FPC-QAOA (k = 3, COBYLA) reaches at least the hardware quality without noise (≥ 60.8% at p = 3) | **reproduced** | 0.836 mean over 200 samples of 4096 shots |
| C3 | 64.1% ± 3.3% at p = 3 on IBM hardware | **not tested** | Not run by decision after Q1: the registered metric cannot separate signal from noise here |
| C4 | Greedy (GNN) is already optimal on the 2 × 3 instance | **reproduced** (caveat) | Greedy picks the optimal association. The objective the code reports for it (−80.01) counts pairs only; its full QUBO value is −92.35. Not optimal under the paper's cost equation, nor on the 3 × 4 instance (95.4%). |

## Questions added by this study

**Q1 — is the headline metric informative? No, by the rule registered before the result.**

| distribution (2 × 3 instance) | top-10 quality, mean | 95th percentile | best of all 4096 samples |
|---|---|---|---|
| uniformly random bitstrings | 0.582 | **0.866** | **0.995** |
| paper's FPC-QAOA, p = 3, noiseless | 0.836 | — | 1.000 |
| paper's hardware headline | 0.641 | — | — |

- **Why random sampling scores so well.** Only 5.2% of all strings reach 0.641, but at least one of 10 nearly random strings does
  about 41% of the time.
- **The best-sample measure is weaker still.** The optimum appears in 85.5% of uniform 4096-shot samples (2,048 states).
- **Levels, not proportions.** The repository solver's simulator qualities (0.869, 0.882, 0.909) and the paper's "90.9%" are the
  energy levels 7, 6 and 3 of this instance divided by the optimum, not graded proportions.

**Q2 — standard metrics.**
- **2 × 3:** P(optimal) for the paper's method is ≤ 0.002 at p ≤ 3, against 0.0005 for uniform sampling. It is 0.016 at p = 4.
- **3 × 4:** P(optimal) is 6.2 × 10⁻⁷ at p = 1 and 6.9 × 10⁻⁶ at p = 2, against 1.9 × 10⁻⁶ uniform.
- **Expectation:** ⟨E⟩/optimum stays at or below 0.28 throughout.

**Q3 — penalty weight.** λ = 1.0 · max|c| versus the paper's 1.5 · max|c|: P(optimal) differences at the 10⁻³ level, with no consistent
direction.

**Q4 — the 19-variable instance, noiseless.**

| | top-10 quality | paper, hardware |
|---|---|---|
| paper's method, p = 1 | 0.534 | 20.4% |
| paper's method, p = 2 | 0.759 | 11.5% |
| uniformly random | 0.150 mean (sd 0.313, 95th percentile 0.632); 44% of samples ≥ 20.4% | — |

## Defects found in the public code

Each is described in `docs/p3-sources.md` with file and line references. Confirmation used the authors' toolchain (qiskit 2.5.2,
qiskit-optimization 0.7.0) in a separate environment.

1. **Parameter binding.**
   - What happens: `QAOAAnsatz.parameters` lists all β before all γ. The hardware script binds an interleaved [γ₁, β₁, γ₂, …] list
     to it by position.
   - Where it matters: the analytical initial schedule, which the paper credits with the 64.1% headline, would not run as described.
     Optimised angles bind correctly.
   - Effect on the metric: at p = 3 the misbound circuit scores 0.820 on the paper's metric and the correctly bound one 0.575. A
     metric this close to random can rank a wrong circuit above the right one.
2. **Bit order.**
   - What happens: `to_ising` maps variable i to qubit i, and Qiskit count keys are little-endian. The script reads keys left to
     right, so it scores every hardware bitstring as its mirror image.
   - Effect: on the noiseless p = 3 distribution this changes the score from 0.836 to 0.430 without any change to the quantum state.
3. **Solver.** The public `FPCQAOASolver` passes the schedule only as a starting point and trains all 2p angles. That is not the
   fixed-parameter-count method the paper and its source (arXiv:2512.21181) describe.

Also documented in the audit:
- "ISA" is defined as a two-qubit-gate depth but used as a gate count.
- Ungated pairs keep their variables at cost 0.
- The missed-detection and false-alarm costs appear only in code.
- The cited ancillary artefact bundle returns 404.
- Citations to "Stollenwerk et al." merge three unrelated works, and the λ = 1.5 · max|c| rule has no traceable source.

## Limits of this reproduction

- The private code and raw hardware data were not available. The defects above are confirmed in the public code only.
- The C2 grade depends on details the paper leaves open. Those were fixed as follows, and are stated in the code:
  - schedules digitised at t = (l + ½)/p, as in the public code
  - a polynomial schedule
  - SciPy's COBYLA for 100 iterations
  - minimising ⟨H⟩
- The simulation was noiseless. No noisy model and no hardware were used, so C3 remains open.
- There is one instance per size (seed 42), because the paper reports one. Other seeds could behave differently.
- The random baseline assumes uniform sampling. Hardware noise is not uniform, but a result judged by this metric that cannot beat
  uniform sampling carries no evidence either way.

## Suggestions for reporting such results

- Report P(optimal) or P(feasible) and the energy distribution alongside any "best of k samples" metric. State k and the shot count.
- Show the same metric for uniformly random sampling at the same shot count.
- Test the bit order and the parameter binding with a circuit whose answer is known before running it on hardware.
- Publish the instance data and the cost constants with the paper, or in an archive that resolves.

## Reproducing this study

```bash
python src/p3_qantis_instance.py --qantis-repo <clone of neuraparse/qantis at c17c2b5>
python src/p3_qantis_qaoa.py
python src/p3_qantis_q4.py --qantis-repo <clone>
<separate env with qiskit-optimization>/python tools/p3_repo_crosscheck.py --qantis-repo <clone> --out results/p3_2-repo-crosscheck.json
python -m unittest discover -s tests
```

92 automated tests pass. Nothing from the authors' repository is copied into this repository; the cross-checks import it from a
separate clone at run time.
