# Research log

A dated record of what was tried, what worked, and what did not.
Entries are append-only. Mistakes stay in the log — they are part of the evidence.

---

## 2026-09-14 — Day 0

- Repository created. Goal for P0: implement Grover search from primitive gates (no library oracle
  helpers), verify the amplification behaviour on a simulator, then run the same circuit on real
  IBM hardware and compare the two distributions.
- Question P0 must answer: how far does the hardware result drift from the ideal distribution, and
  does that drift grow with the number of Grover iterations?

## 2026-09-14 — v0.1.0 archived

- Released `v0.1.0 - P0 baseline` on GitHub. Zenodo archived it automatically.
- Version DOI: 10.5281/zenodo.22741038 · Concept DOI (always the latest version): 10.5281/zenodo.22741037
- Creator metadata carried over from `CITATION.cff`, including the ORCID link.
- Honest status: the P0 code exists but has not been executed yet. The next release must contain real
  simulator and hardware results in `results/`.

## 2026-09-14 — P0 on the simulator: matches theory

Environment: Python 3.12.10 · qiskit 2.5.2 · qiskit-aer 0.17.2 · qiskit-ibm-runtime 0.49.0

**Single run at the optimal iteration count** (n = 3, marked = `101`, k = 2, 4096 shots,
circuit depth 22, gates: 23 H, 16 X, 4 CCX): marked state measured 3878 / 4096 = **0.9468**
(`results/p0-grover-20260914-113343.json`).

**Iteration sweep against closed form** — for N = 8, M = 1: P(k) = sin²((2k+1)θ), sin θ = 1/√8.
Seed 1234, 4096 shots per point (`results/p0-sweep-20260914-113455.json`):

| k | theory | simulator | diff | shot-noise σ | z |
|---|--------|-----------|------|--------------|---|
| 0 | 0.1250 | 0.1233 | −0.0017 | 0.0052 | −0.33 |
| 1 | 0.7813 | 0.7703 | −0.0110 | 0.0065 | −1.70 |
| 2 | 0.9453 | 0.9424 | −0.0029 | 0.0036 | −0.82 |
| 3 | 0.3301 | 0.3345 | +0.0044 | 0.0073 | +0.60 |
| 4 | 0.0122 | 0.0107 | −0.0015 | 0.0017 | −0.85 |
| 5 | 0.5480 | 0.5552 | +0.0072 | 0.0078 | +0.93 |

- Every point sits within 2σ of the formula (max |z| = 1.70). The implementation behaves as theory says.
- Re-running with the same seed reproduces the table exactly.
- The oscillation is the interesting part: past the optimum the state *over-rotates* — k = 4 is almost
  as bad as not searching at all (1.2%). "More iterations" is not "more search".
- Why this matters for hardware: each extra iteration also makes the circuit deeper, so on a noisy
  device the drop after k = 2 should be joined by a general flattening toward 1/8. That is the
  question for the hardware run.

## 2026-09-14 — P0 on real hardware: `ibm_kingston`

Job `dajnoini3e6s738qgf8g` · IBM Quantum Open Plan · 4096 shots per circuit · all six circuits in one job
(same calibration) · transpiled with optimization level 3 · **no error mitigation**.
Raw data: `results/p0-hardware-sweep-20260914-114702.json` · analysis: `src/p0_hardware_analysis.py`.

| k | two-qubit gates | depth | theory | hardware | diff |
|---|-----------------|-------|--------|----------|------|
| 0 | 0 | 4 | 0.1250 | 0.1218 | −0.0032 |
| 1 | 19 | 72 | 0.7813 | 0.7041 | −0.0771 |
| 2 | 39 | 139 | 0.9453 | **0.7881** | −0.1572 |
| 3 | 59 | 206 | 0.3301 | 0.2341 | −0.0959 |
| 4 | 79 | 273 | 0.0122 | 0.0500 | +0.0378 |
| 5 | 99 | 340 | 0.5480 | 0.4492 | −0.0988 |

What the device showed:

1. **The Grover peak survives.** k = 2 is still the best choice on hardware: 3228 / 4096 = 78.8%,
   against 12.5% for guessing.
2. **The first surprise was the circuit size.** The 4 CCX gates of the ideal k = 2 circuit become
   **39 two-qubit gates** after transpilation; every extra iteration adds about 20. The gap to theory
   follows: −0.3% with no two-qubit gates, −7.7% with 19, −15.7% with 39.
3. **Everything is pulled toward 1/8.** High points drop, and k = 4 *rises* from 1.2% to 5.0%.
4. **A single global depolarizing model is only a rough fit.** Solving p_hw = f·p_th + (1−f)/8 for the
   points where theory is far from 1/8 (k = 1, 2, 5) gives an implied per-two-qubit-gate fidelity of
   0.993–0.997. The value is not constant across k, so this model does not describe the device fully.
5. **The noise is not uniform.** At k = 2, wrong outcomes one bit away from `101` appear with 3.7% per
   state, two bits away 2.7%, three bits away 2.1%. A uniform depolarizing channel with f = 0.808 would
   give about 2.4% to every wrong state. Errors prefer *nearby* states — consistent with local bit flips
   (readout and single-qubit errors) rather than full scrambling.

Caveats — stated so they are not mistaken for conclusions:
- One job, one calibration, one qubit layout. No repetition yet, so no error bars across runs.
- For k = 3 and k = 4 theory is close to 1/8, so f there is dominated by shot noise and is not used.
- The runtime metrics call did not return QPU seconds for this job.

Open questions for the next step:
- How much of the k = 2 loss is readout error? Measure it directly and apply readout mitigation.
- Does repeating the job on another day or device (`ibm_fez`, `ibm_marrakesh`) give the same curve?

## 2026-09-14 — QPU time used by the hardware sweep

- The runtime metrics call returned nothing, so usage was read from the IBM Quantum dashboard instead:
  **9 m 51 s remaining** of the 10-minute Open Plan allowance after job `dajnoini3e6s738qgf8g`.
- The whole sweep (6 circuits × 4096 shots = 24,576 shots) therefore cost about **9 QPU seconds**.
- At that rate the remaining allowance covers about 65 more sweeps of the same size — enough for a
  readout-error measurement and repeats on `ibm_fez` and `ibm_marrakesh` without running out.

## 2026-09-14 — P0.5 plan and method check on a simulator

Question: how much of the k = 2 loss on hardware is readout error, and is the "one bit away" bias from P0
caused by readout or by the gates?

Method (`src/p0_5_readout.py`): in one job per device, run Grover k = 2 and eight calibration circuits that
prepare each basis state on **the same physical qubits Grover is measured on**. The eight measured
distributions form the assignment matrix A[j][s] = P(read j | prepared s). Correct the Grover result by
solving A·p = p_measured, clipping negatives and renormalising. Test: if the one-bit-away bias disappears
after correction, it came from readout; if it survives, it came from the gates.

Before spending any QPU time, the method was checked on a simulator with ideal gates and a **known**
symmetric readout error (seed 1234, 4096 shots):

| injected readout error | raw success | corrected | theory | gap after correction | distance-1 per state raw → corrected |
|------------------------|-------------|-----------|--------|----------------------|--------------------------------------|
| 3% | 0.8579 | 0.9390 | 0.9453 | 0.0063 | 0.0353 → 0.0092 |
| 8% | 0.7217 | 0.9234 | 0.9453 | 0.0219 | 0.0756 → 0.0143 |

- The estimated per-bit readout errors come out at 2.7–3.1% and 7.7–8.0%, matching what was injected.
- The correction recovers theory well at 3% and less precisely at 8% — calibration shot noise is amplified
  by the matrix inversion. That residual is the method's own error bar and must be kept in mind on hardware.
- **Readout error alone reproduces the P0 signature.** A 3% readout error gives 0.035 per state at
  distance 1 — close to the 0.037 seen on `ibm_kingston`. The hypothesis is plausible; hardware decides.

## 2026-09-14 — P1.0: scenario generator and Hungarian baseline

Plan: `docs/p1-plan.md` (pre-registered). Code: `src/p1_scenario.py`. Tests: `tests/test_p1_scenario.py`.

Textbook parameters: constant-velocity Kalman prediction (dt = 1 s, white-noise acceleration σ = 1 m/s²),
previous-estimate σ = 20 m / 5 m/s, measurement σ = 10 m per axis, P_D = 0.9, on average 1 false alarm per
scan in a window 200 m around the tracks, chi-square gate 9.21 (2 dof, 99%), targets spaced about 50 m apart
so the association is genuinely ambiguous. Cost = −ln(P_D·N(z; ẑ, S)/λ), missed detection −ln(1 − P_D),
augmented (T + M) × (T + M) matrix.

**Tests — 6 of 6 pass**, each against a route independent of the code under test:
- the cost equals −(ln P_D + log N(z; ẑ, S) − ln λ) computed with SciPy's multivariate normal, to 9 decimals
- the Hungarian optimum on the augmented matrix equals direct enumeration of every valid association on
  240 random scenes with 1–4 targets
- no assigned pair ever lies outside the gate; same seed gives the same scene; matrix shapes are right;
  with near-zero noise the optimum always equals the truth

**Baseline, 3 targets, 500 scenes, seed 2026:**

| mode | mean track accuracy vs truth | scenes where optimum = truth | matrix size | QUBO variables (mean) |
|------|------------------------------|------------------------------|-------------|-----------------------|
| augmented (P_D = 0.9, clutter) | 0.8980 | 0.8220 | 4–11 (mean 6.72) | 46.5 |
| pure (P_D = 1, no clutter) | 0.9453 | 0.9180 | 3 | 9 |

What this already says about the rest of P1:
1. **The optimum is not the truth.** Even a perfect solver returns the true association in only 82% of
   augmented scenes and 92% of pure ones at this spacing. That ceiling comes from the noise and the cost
   model, not from the solver — so every QUBO, annealing and QAOA result will be scored against the
   *optimum* (P(optimal)) and, separately, against the truth.
2. **Size decides where quantum can run.** A realistic augmented 3-target scan averages 46.5 binary variables
   and reaches 121 — far beyond what QAOA runs reliably on current hardware. This confirms the plan: hardware
   only for pure 2 × 2 and 3 × 3 instances (4 and 9 variables); larger instances stay on classical solvers.

Next: P1.1 — QUBO builder and the hard gate (QUBO minimum = Hungarian optimum on every test instance).

## 2026-09-14 — P1.1: QUBO builder — the gate is passed

Code: `src/p1_qubo.py`. Tests: `tests/test_p1_qubo.py`. Raw gate output: `results/p1_1-gate-20260914-124400.json`.

Encoding: one binary variable per **allowed** cell of the assignment matrix (gated-out cells get no variable,
so no big-M constants), E(x) = Σ c·x + A·Σ_rows(Σx − 1)² + A·Σ_cols(Σx − 1)², stored as an upper-triangular
Q with Q_kk = c_k − 2A, Q_kl = 2A per shared row or column, offset 2nA.

Penalty for the gate: **A = 2·Σ|c| + 1.** Argument: an infeasible string violates at least one constraint, so
its penalty is at least A; its cost part is at least −Σ|c|; the optimum costs at most Σ|c|. So no infeasible
string can undercut the optimum. This A is deliberately generous; P1.2 asks how small it can be.

One design change found while writing it: in the augmented matrix the dummy × dummy block (clutter row j,
miss column i) was fully open at zero cost. It only needs a cell where track i may take measurement j — those
are exactly the cells that complete a real assignment. Every valid association still has a completion of the
same cost, with fewer variables and far fewer duplicate optima.

**Tests — 12 of 12 pass** (6 from P1.0, 6 new), each against a quantity computed without the QUBO:
- energy of every valid permutation equals the plain assignment cost
- on 200 random bit strings with random A, energy − cost equals A × squared constraint violation exactly
- pruning the augmented matrix never changes the Hungarian optimum (200 scenes, 1–4 targets)
- brute-force QUBO minimum equals the Hungarian optimum, and its argmin decodes to a valid assignment

**Gate — seed 11, 100 scenes per setting, exhaustive search up to 20 variables:**

| setting | tested | passed | skipped (> 20 vars) | variables mean (max) | before pruning → after |
|---------|--------|--------|---------------------|----------------------|------------------------|
| pure 2 × 2 | 100 | 100 | 0 | 4.0 (4) | 4.0 → 4.0 |
| pure 3 × 3 | 100 | 100 | 0 | 9.0 (9) | 9.0 → 9.0 |
| pure 4 × 4 | 100 | 100 | 0 | 16.0 (16) | 16.0 → 16.0 |
| augmented, 1 target | 100 | 100 | 0 | 4.8 (11) | 5.7 → 4.8 |
| augmented, 2 targets | 100 | 100 | 0 | 10.3 (18) | 12.6 → 10.3 |
| augmented, 3 targets | 88 | 88 | 12 | 16.7 (26) | 22.7 → 16.7 |

**GATE PASSED: 588 / 588** — the QUBO minimum equals the Hungarian optimum on every instance checked.

Stated limits:
- Exhaustive verification stops at 20 variables; 12 of the 3-target augmented scenes were larger and were
  not brute-forced. The algebraic tests hold at any size, but the minimum itself was not checked there.
- On the 3-target augmented scenes, pruning the dummy block cut the variables by about a quarter
  (22.7 → 16.7 on the same scenes). The larger reduction from P1.0's naive n² count comes mostly from not
  creating variables for gated-out cells; P1.0 used a different scene set, so the two numbers are not compared
  directly here.

Next: P1.2 — how small can the penalty A be before infeasible strings win, and what does a large A do to the
energy landscape a heuristic or QAOA has to search?
