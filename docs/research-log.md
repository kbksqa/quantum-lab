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

## 2026-09-14 — P1.2: the penalty study

Code: `src/p1_penalty.py`. Tests: `tests/test_p1_penalty.py`. Raw output: `results/p1_2-penalty-20260914-125028.json`.

**The critical penalty is exact, not searched for.** With E_A(x) = cost(x) + A·V(x) and V = 0 exactly on feasible
strings, the optimum wins iff A > (optimum − cost(x)) / V(x) for every infeasible x, so
A_crit = max(0, max over infeasible x of (optimum − cost(x)) / V(x)), computed by enumeration.
Test: just above A_crit the brute-force QUBO minimum is feasible and optimal; 0.1% below it, an infeasible string wins.

**Tests — 16 of 16 pass** (4 new: the threshold check above; energies from cost + A·V equal the QUBO matrix energy
on every bit string; the normalised gap lies in (0, 1]; annealing is deterministic per seed and solves a tiny instance).

Set-up: 50 instances each of pure 3 × 3 (9 variables), pure 4 × 4 (16) and augmented 2-target scenes (mean 11,
at most 18), seed 12. For A = 1.1, 1.5, 2, 5, 10, 50 × A_crit and the provably safe A = 2·Σ|c| + 1:
- **normalised gap** (E1 − E0)/(Emax − E0) — solver-independent
- **simulated annealing**: single-bit flips, 64 restarts, 100 sweeps, geometric schedule from
  T_start = largest single-flip |ΔE| (grows with A) to T_end = 0.05 × cost spread (independent of A).
  **The annealing numbers depend on this schedule.**

How generous the safe penalty is: median A_safe / A_crit = **46.8×** (3 × 3), **105.6×** (4 × 4), **21.6×** (augmented).
The simple rule A = max|c| was above A_crit in **all 150 instances** — observed, not proven.

| setting | A / A_crit | normalised gap (median) | SA finds optimum | SA ends feasible |
|---------|-----------|-------------------------|------------------|------------------|
| pure 3 × 3 | 1.1 | 0.0045 | 0.565 | 0.651 |
| | **1.5** | **0.0112** | **0.662** | 0.968 |
| | 2 | 0.0091 | 0.554 | 0.988 |
| | 5 | 0.0043 | 0.343 | 1.000 |
| | 10 | 0.0023 | 0.253 | 1.000 |
| | 50 | 0.0005 | 0.191 | 1.000 |
| | safe (46.8) | 0.0005 | 0.183 | 1.000 |
| pure 4 × 4 | 1.1 | 0.0016 | 0.257 | 0.314 |
| | **1.5** | **0.0049** | **0.541** | 0.848 |
| | 2 | 0.0039 | 0.455 | 0.955 |
| | 5 | 0.0018 | 0.201 | 1.000 |
| | 10 | 0.0010 | 0.118 | 1.000 |
| | 50 | 0.0002 | 0.048 | 1.000 |
| | safe (105.6) | 0.0001 | 0.045 | 1.000 |
| augmented, 2 targets | 1.1 | 0.0052 | 0.423 | 0.487 |
| | 1.5 | 0.0180 | 0.653 | 0.772 |
| | **2** | **0.0264** | **0.683** | 0.840 |
| | 5 | 0.0180 | 0.574 | 0.874 |
| | 10 | 0.0090 | 0.438 | 0.882 |
| | 50 | 0.0018 | 0.265 | 0.884 |
| | safe (21.6) | 0.0057 | 0.324 | 1.000 |

What the numbers say:
1. **There is a sweet spot, and it is close to A_crit.** Both the solver-independent gap and annealing success peak
   at 1.5–2 × A_crit in every setting.
2. **Too small is bad in one way:** at 1.1 × A_crit infeasible strings sit just above the optimum, the gap is small,
   and annealing often ends infeasible (31–65% feasible).
3. **Too large is bad in another:** the energy range explodes, cost differences become tiny relative to it, and
   annealing wanders among valid but poor assignments — feasible 100% of the time, optimal rarely.
4. **The provably safe penalty is expensive, and more so as instances grow.** Against the best multiplier, annealing
   success drops 0.662 → 0.183 (3.6× worse) on 3 × 3 and 0.541 → 0.045 (12× worse) on 4 × 4.

Stated limits and one unexplained point:
- A_crit needs enumeration, which is exponential — it is an oracle for studying the problem, not something a real
  solver can compute. The practical question it raises is whether a *computable* rule such as A = max|c| lands near
  the sweet spot. That is the natural first question for P1.3.
- Annealing results are conditional on the schedule above; the gap metric points the same way without any solver.
- **Unexplained:** on augmented scenes the feasible share stays at 0.88 even at 50 × A_crit, while the safe penalty
  (a median 21.6 ×) reaches 1.000. The per-instance data needed to explain this was not saved in this run.
  A plausible hypothesis — not yet tested — is that with a very large A, moving an assignment by single bit flips
  passes through doubly-violating states whose barrier freezes annealing in infeasible local minima, and that the
  per-instance safe multipliers differ from 50 × in a way that avoids this. P1.3 will save per-instance results to check.

Next: P1.3 — simulated annealing baseline with computable penalty rules (A = max|c| versus the 1.5 × A_crit oracle),
saving per-instance results.

## 2026-09-14 — P1.3: simulated annealing baseline, and a correction to P1.2

Code: `src/p1_annealing.py`. Tests: `tests/test_p1_annealing.py`. Raw output with per-instance results:
`results/p1_3-annealing-20260914-125703.json`. Annealing: same routine and schedule as P1.2, 64 restarts, seed 13.

**Tests — 20 of 20 pass.** The key new check: the P1.2 instance sets were rebuilt from the same seed and order of random
draws, and their median safe/critical penalty ratios match the committed P1.2 result file to 9 decimal places in all
three settings. Part 1 below therefore analyses exactly the instances P1.2 used.

### Part 1 — the P1.2 anomaly was a flaw in my study code

P1.2 set A = s × base with base = A_crit, but fell back to base = 10⁻⁶ whenever A_crit = 0.

| augmented 2-target scenes | instances | feasible share, P1.2 rule at 50× | feasible share, safe penalty |
|---------------------------|-----------|----------------------------------|------------------------------|
| A_crit = 0 | 6 | 0.023 | 1.000 |
| A_crit > 0 | 44 | 1.000 | 1.000 |
| all | 50 | 0.883 | 1.000 |

**Correction to the P1.2 entry.** The flat feasible share of about 0.88 across 1.1–50 × A_crit on augmented scenes came
from 6 instances that effectively had no penalty at all — 6 of 50 at ~2% plus 44 at 100% gives 0.883, matching P1.2's
0.884. The trapping hypothesis written in P1.2 is not needed and is withdrawn. The augmented multiplier rows in the
P1.2 table understate feasibility and success for that reason. The pure 3 × 3 and 4 × 4 rows are unaffected — none of
those instances has A_crit = 0 — so the P1.2 conclusions about the sweet spot and the cost of the safe penalty stand.

A_crit = 0 is a genuine case, not a bug in the formula: it happens when no infeasible string can undercut the optimum
(test instance C = [[−5, ∞], [∞, −5]]). Any positive A then works, and "multiples of A_crit" mean nothing.

### Part 2 — a penalty rule a real solver can compute

Same instances as P1.2. Per-restart success, best of 64 restarts, and share of restarts ending feasible:

| setting | max\|c\| / A_crit, median (min–max) | rule | success | best-of-64 optimal | feasible |
|---------|-------------------------------------|------|---------|--------------------|----------|
| pure 3 × 3 | 4.38 (2.49–7.36) | oracle 1.5 × A_crit | 0.641 | 1.000 | 0.962 |
| | | **A = max\|c\|** | **0.355** | 1.000 | 1.000 |
| | | safe | 0.190 | 1.000 | 1.000 |
| pure 4 × 4 | 7.38 (4.80–11.26) | oracle 1.5 × A_crit | 0.549 | 1.000 | 0.834 |
| | | **A = max\|c\|** | **0.147** | 1.000 | 1.000 |
| | | safe | 0.051 | 0.980 | 1.000 |
| augmented, 2 targets | 2.67 (1.17–42.62) | oracle 1.5 × A_crit (44 instances) | 0.739 | 1.000 | 0.878 |
| | | **A = max\|c\|** | **0.775** | 1.000 | 0.969 |
| | | safe | 0.328 | 1.000 | 1.000 |

- **A = max|c| was above A_crit in every instance** (smallest ratio 1.17). Still an observation, not a proof.
- **It sits between the oracle and the safe penalty.** Per restart it beats the safe penalty by 1.9× (3 × 3), 2.9× (4 × 4)
  and 2.4× (augmented). On pure instances it trails the oracle by 1.8× and 3.7×. On augmented scenes it slightly beats
  the oracle (0.775 vs 0.739), because 1.5 × A_crit is near the too-small regime there (feasible only 0.878).
- **Its overshoot grows with size** on pure instances (median 4.4× → 7.4× A_crit), so it drifts away from the sweet spot.
- **Best-of-64 hides the difference.** On these small instances the best restart finds the optimum for almost every rule
  (one exception: safe on 4 × 4, 0.98). Per-restart success is what separates them — and QAOA samples are closer to
  single restarts than to a best-of-64 search.

### Part 3 — beyond brute force, with A = max|c|

30 instances per setting, scored against the Hungarian optimum:

| setting | variables mean (max) | sweeps | success | best-of-64 optimal | feasible | median best gap / cost spread |
|---------|----------------------|--------|---------|--------------------|----------|-------------------------------|
| pure 5 × 5 | 25 (25) | 100 | 0.051 | 0.967 | 1.000 | 0.0000 |
| | | 400 | 0.077 | 0.967 | 1.000 | 0.0000 |
| pure 6 × 6 | 36 (36) | 100 | 0.009 | 0.467 | 1.000 | 0.0117 |
| | | 400 | 0.012 | 0.667 | 1.000 | 0.0000 |
| augmented, 3 targets | 17 (25) | 100 | 0.701 | 1.000 | 0.965 | 0.0000 |
| | | 400 | 0.799 | 1.000 | 0.989 | 0.0000 |

- **Dense instances get hard fast.** At 36 variables one restart finds the optimum about 1% of the time, and even the best
  of 64 restarts at 400 sweeps finds it in only two thirds of instances — for a problem Hungarian solves exactly in
  polynomial time.
- **Realistic tracking scenes are easy here.** Gating and pruning leave a sparse structure (17 variables on average for
  3 targets), and annealing succeeds 70–80% per restart.
- **More sweeps help, modestly** (6 × 6 best-of-64: 0.47 → 0.67).
- This is the classical heuristic reference for QAOA. It is not a claim that annealing on a QUBO is a sensible way to
  solve two-dimensional assignment — it is not.

Next: P1.4 — QAOA on a simulator for pure 2 × 2 and 3 × 3, with the penalty chosen from these results.

## 2026-09-14 — P0.5 on real hardware: readout is not the main loss, and the hypothesis is rejected

Plan and method check: see the P0.5 entries above. Submitted 12:11, collected 13:01. Raw data:
`results/p0_5-readout-20260914-121144.json` (job ids and physical qubits in the `-submitted` file).
Grover k = 2 plus 8 calibration circuits, one job per device, 4096 shots each; on all three devices the Grover circuit
transpiled to the same 39 two-qubit gates and depth 139.

| device | physical qubits | per-bit readout error range | success raw | readout-corrected | gain |
|--------|-----------------|-----------------------------|-------------|-------------------|------|
| `ibm_kingston` | 94, 93, 79 | 0.05% – 1.56% | 0.7856 | 0.8078 | +2.2 pp |
| `ibm_fez` | 8, 9, 10 | 0.10% – 0.84% | 0.7395 | 0.7547 | +1.5 pp |
| `ibm_marrakesh` | 13, 14, 15 | 0.03% – 2.37% | 0.6235 | 0.6567 | +3.3 pp |

Theory: 0.9453.

Error anatomy, probability per wrong state by Hamming distance from the marked state, raw → corrected:

| device | distance 1 | distance 2 | distance 3 | distance-1 / distance-3, raw → corrected |
|--------|------------|------------|------------|------------------------------------------|
| `ibm_kingston` | 0.0369 → 0.0297 | 0.0265 → 0.0263 | 0.0239 → 0.0241 | 1.54 → 1.23 |
| `ibm_fez` | 0.0444 → 0.0395 | 0.0344 → 0.0344 | 0.0242 → 0.0237 | 1.83 → 1.67 |
| `ibm_marrakesh` | 0.0545 → 0.0437 | 0.0554 → 0.0556 | 0.0466 → 0.0454 | 1.17 → 0.96 |

What the devices said:
1. **Readout error is small on these qubits** — at most 2.4% per bit and mostly below 1.6%, smaller than the 3% case
   used in the simulator check.
2. **Most of the loss comes from the gates.** Against theory the devices lose 14–32 percentage points; correcting the
   readout recovers only 1.5–3.3 of them.
3. **The hypothesis is rejected.** Correction removes part of the bias toward states one bit away, but on `ibm_kingston`
   and `ibm_fez` the bias survives (distance-1 still 1.2–1.7× distance-3). Gate errors must also push results toward
   nearby states. On `ibm_marrakesh` the bias disappears after correction, but that device is noisier overall and its
   wrong outcomes are closer to evenly spread.
4. **The P0 result reproduced.** `ibm_kingston` gave 0.7856 raw this afternoon against 0.7881 this morning — within
   0.25 percentage points, a few hours apart. (P0 did not record which physical qubits it used, so the layouts may differ.)
5. **Same circuit, different devices, very different results:** raw success from 0.62 to 0.79 with identical gate count
   and depth. Device choice matters as much as circuit design at this size.

Stated limits:
- One job per device, one calibration window each; the calibration circuits share the Grover job, which is the point,
  but also means no repetition.
- The correction has its own error bar (0.6 pp in the 3% simulator check, smaller at the ~1% readout seen here). The
  gains above are larger than that, but the distance-1 changes on `ibm_fez` are close to it.
- QPU seconds for this run were not read from the dashboard yet.

What changes for P1.5: readout correction is worth applying but will not rescue deep circuits. Circuit depth and device
choice decide the outcome; QAOA on hardware should use the shallowest circuits and the best device of the day.
