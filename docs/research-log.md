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

## 2026-09-14 — P1.4: QAOA on a simulator

Code: `src/p1_qaoa.py`. Tests: `tests/test_p1_qaoa.py`. Raw output with per-instance parameters and metrics:
`results/p1_4-qaoa-20260914-131628.json`.

Set-up: pure 2 × 2 (4 qubits, 50 new instances, seed 14) and pure 3 × 3 (9 qubits, **the same 50 instances as P1.2 and
P1.3**). QUBO → Ising with x = (1 − z)/2, coefficients divided by max |h|, |J|. QAOA depth p = 1, 2, 3; COBYLA minimising
⟨H⟩ (max 300 iterations), 6 random starts plus one start interpolated from depth p − 1. Two penalties: the computable
A = max|c| and the P1.2 oracle A = 1.5 × A_crit. Noiseless statevector simulation; 1024 samples drawn per instance for the
sample metrics.

**Tests — 24 of 24 pass.** The central new check: the NumPy simulator matches Qiskit's `Statevector` of the circuit built
from the Ising coefficients, on 2 × 2 and 3 × 3 — which verifies the Ising conversion, the angle conventions and the
simulator together. The run itself also stops if the Ising energies ever differ from the QUBO energies.

**2 × 2 (4 qubits).** Guessing: P(optimal) 0.0625, P(feasible) 0.125.

| penalty | p | P(optimal) ± SEM | P(feasible) ± SEM | CZ gates (heavy-hex estimate) | depth |
|---------|---|------------------|-------------------|-------------------------------|-------|
| A = max\|c\| | 1 | 0.258 ± 0.014 | 0.440 ± 0.013 | 11 | 43 |
| | 2 | 0.454 ± 0.025 | 0.710 ± 0.014 | 22 | 69 |
| | 3 | 0.578 ± 0.025 | 0.866 ± 0.011 | 39 | 137 |
| 1.5 × A_crit | 1 | 0.154 ± 0.006 | 0.227 ± 0.006 | | |
| | 2 | 0.409 ± 0.027 | 0.582 ± 0.035 | | |
| | 3 | 0.583 ± 0.028 | 0.755 ± 0.026 | | |

**3 × 3 (9 qubits).** Guessing: P(optimal) 0.0020, P(feasible) 0.0117.

| penalty | p | P(optimal) ± SEM | P(feasible) ± SEM | CZ gates (heavy-hex estimate) | depth |
|---------|---|------------------|-------------------|-------------------------------|-------|
| A = max\|c\| | 1 | 0.0176 ± 0.0008 | 0.102 ± 0.003 | 58 | 137 |
| | 2 | 0.0529 ± 0.0017 | 0.269 ± 0.009 | 152 | 228 |
| | 3 | 0.0771 ± 0.0027 | 0.409 ± 0.016 | 238 | 425 |
| 1.5 × A_crit | 1 | 0.0128 ± 0.0003 | 0.052 ± 0.002 | | |
| | 2 | 0.0155 ± 0.0007 | 0.049 ± 0.004 | | |
| | 3 | 0.0294 ± 0.0019 | 0.074 ± 0.010 | | |

What the simulator showed:
1. **QAOA learns the problem.** Every setting is well above guessing and improves with depth — at p = 3, P(optimal) is
   about 9× guessing on 2 × 2 and about 39× on 3 × 3.
2. **The best penalty for annealing is not the best penalty for QAOA.** On 3 × 3 the computable A = max|c| beats the
   P1.2 oracle 1.5 × A_crit by 1.4× (p = 1), 3.4× (p = 2) and 2.6× (p = 3), and the oracle leaves QAOA almost always
   infeasible (P(feasible) 0.05–0.07). On 2 × 2 max|c| is better at p = 1–2 and equal at p = 3. The P1.2 recommendation of
   1.5–2 × A_crit was an annealing result and does not transfer. A plausible reading, not tested here: shallow QAOA cannot
   concentrate amplitude precisely, so it needs a penalty that separates feasible from infeasible strings more strongly.
3. **Per sample, QAOA trails annealing on the same 3 × 3 instances.** With the same rule A = max|c|, one annealing restart
   found the optimum 35.5% of the time (P1.3); one QAOA sample at p = 3 finds it 7.7% of the time. This compares one
   sample with one restart — not equal computational cost — and it is noiseless QAOA.
4. **Depth is expensive in two-qubit gates.** On the heavy-hex CZ model, 3 × 3 at p = 3 needs about 238 CZ gates and depth
   425 — roughly six times the 39-CZ Grover circuit that already lost 16–32 percentage points on real devices in P0.5.
5. **"Optimum appears in 1024 shots" saturates.** It is 1.00 in every setting because P(optimal) ≥ 0.013 gives more than a
   dozen expected hits. At these sizes it does not separate anything; P(optimal) is the metric that does.

Stated limits:
- The optimiser minimises ⟨H⟩, the standard QAOA objective, not P(optimal) directly; objectives such as CVaR were not tried.
- COBYLA with 7 starts can land in local optima, especially at p = 3 on 9 qubits. The ± values are spread across
  instances, not optimiser uncertainty.
- Gate counts and depth come from a heavy-hex CZ model (`GenericBackendV2`, optimisation level 3), not from a real device.
- Noiseless simulation only.

What this suggests for P1.5, to be decided before any QPU time is spent: use A = max|c|; run 2 × 2 at p = 1 and p = 2
(11 and 22 CZ gates in the estimate) as the main hardware experiment, and at most 3 × 3 at p = 1 (58 CZ) as a stress point
expected to be dominated by noise. Full assignment-matrix readout calibration needs 2⁹ = 512 circuits at 9 qubits, so the
9-qubit case would need a per-qubit (tensored) readout correction instead of the P0.5 method.

## 2026-09-14 — P1.5 pre-registration: predictions written before submitting to hardware

Approved by the account owner to use the free Open Plan allowance. Code: `src/p1_5_hardware.py`. Tests:
`tests/test_p1_5_hardware.py` (29 of 29 pass, including tensored readout correction exactly undoing an independent
readout model and agreeing with the P0.5 full-matrix method).

**Dry run (no job submitted, no QPU time).**
- The rebuilt instances and the stored P1.4 parameters reproduce P1.4's P(optimal) exactly for all 25 circuits.
- Device ranking from today's calibration data, by median CZ error: `ibm_kingston` 0.0019 (median readout 0.0088),
  `ibm_fez` 0.0028 (0.0101), `ibm_marrakesh` 0.0032 (0.0137). Chosen: **`ibm_kingston`**.
- Transpiled on `ibm_kingston`: 2 × 2 p = 1 → 11 CZ, depth 45–49; 2 × 2 p = 2 → 22 CZ, depth 63–68; 3 × 3 p = 1 → 58 CZ,
  depth 128–134. These match the heavy-hex model estimates from P1.4.
- One job: 25 QAOA circuits + 4 readout calibration circuits, 2048 shots each, 59,392 shots in total.
- Pre-registered selection: the first 10 pure 2 × 2 instances (p = 1 and p = 2) and the first 5 pure 3 × 3 instances (p = 1),
  A = max|c|, parameters taken from the simulator — nothing tuned on hardware.

**Predictions, fixed before the results exist:**
1. 2 × 2, p = 1 (11 CZ): hardware P(optimal) stays close to the simulator — within 20% of the simulator value after readout
   correction.
2. 2 × 2, p = 2 (22 CZ): hardware keeps a smaller share of the simulator value than p = 1 does, **but p = 2 still beats p = 1 on
   hardware** in mean P(optimal). If this fails, extra depth is already not worth its noise at 4 qubits.
3. 3 × 3, p = 1 (58 CZ, depth ~130 — about the same depth as the P0 Grover circuit): hardware P(optimal) is clearly degraded
   from the simulator's 0.0176 but **remains above guessing (0.0020)**.
4. Readout correction raises P(optimal) by a few percentage points at most, as in P0.5; it does not change which of the
   comparisons above hold.

## 2026-09-14 — P1.5 results: QAOA on `ibm_kingston`, checked against the predictions

Job `dajp9gvi3e6s738qj4rg`, submitted 13:31:32, 17 seconds after the predictions were committed (`e2ff7e1`, 13:31:15).
Raw data, counts and per-qubit readout errors: `results/p1_5-hardware-20260914-133130.json`.
Readout calibration: per-qubit P(1|0) at most 0.6% and P(0|1) at most 1.4% on every qubit used.

| circuits | CZ | depth | P(optimal) simulator | hardware raw | corrected | corrected / simulator | P(feasible) simulator → corrected |
|----------|----|-------|----------------------|--------------|-----------|-----------------------|-----------------------------------|
| 2 × 2, p = 1 (10 instances) | 11 | 47 | 0.2140 | 0.1913 | 0.1962 | 0.917 | 0.418 → 0.393 |
| 2 × 2, p = 2 (10 instances) | 22 | 64 | 0.5445 | 0.4762 | 0.4847 | 0.890 | 0.722 → 0.639 |
| 3 × 3, p = 1 (5 instances) | 58 | 132 | 0.0201 | 0.0174 | 0.0180 | 0.896 | 0.108 → 0.087 |

Guessing: P(optimal) 0.0625 on 2 × 2 and 0.0020 on 3 × 3.

**Prediction by prediction:**
1. **2 × 2, p = 1 within 20% of the simulator — held.** Mean retention 0.917; every one of the 10 instances between 0.87 and 0.98.
2. **p = 2 keeps a smaller share than p = 1 but still beats it — held.** Retention 0.890 against 0.917, and p = 2 beat p = 1
   on **all 10 instances**, by 0.29 in P(optimal) on average. Doubling the CZ count cost less than 3 points of retention.
3. **3 × 3, p = 1 clearly degraded but above guessing — half held.** It stayed far above guessing (0.0180 against 0.0020, 9×).
   But it was **not** clearly degraded: it kept about 90% of the simulator's P(optimal), the same as the 4-qubit circuits.
   The P1.4 expectation that 3 × 3 would be "dominated by noise" was wrong. With about 41 expected optimal hits per
   circuit, shot noise alone is about ±15% per instance and about ±7% on the 5-instance mean, so the per-instance spread
   (0.62–1.15) is consistent with sampling.
4. **Readout correction adds a few points at most and changes no comparison — held.** Gains: +0.5, +0.9 and +0.1 points.

**What else the numbers show — observations, not conclusions:**
- **Feasibility degrades with depth more than P(optimal) does.** Retention in P(feasible) falls 0.94 → 0.89 → 0.80 across
  11, 22 and 58 CZ gates, while retention in P(optimal) stays near 0.9 for all three.
- **The calibration CZ error predicts the 3 × 3 loss but not the 2 × 2 loss.** With median CZ error 0.0019, 58 CZ gates predict
  about 0.90 of the signal kept — close to what 3 × 3 kept. The same arithmetic predicts 0.98 for 11 CZ gates, but 2 × 2 at
  p = 1 kept only about 0.92. Something besides two-qubit gate error costs the small circuits a similar few percent; which
  effect it is was not tested here.
- **The pre-registered plan worked as intended:** the simulator parameters transferred to hardware without retuning,
  and the device chosen by calibration data delivered the best retention seen in this project so far.

Stated limits:
- One job, one device, one calibration window, 5 or 10 instances per setting, 2048 shots per circuit.
- The 3 × 3 result rests on 5 instances; its mean has a sampling uncertainty of roughly ±7%.
- Readout correction assumes independent errors between qubits.
- QPU seconds were not read from the dashboard yet.

Next: P1.6 — write-up of P1 as a whole, release and DOI.

## 2026-09-14 — P1.6: QPU time, summary and release

**QPU time.** The IBM Quantum dashboard showed **8 m 57 s remaining** after P1.5, against 9 m 51 s after the P0 sweep.
P0.5 (three jobs, 110,592 shots) and P1.5 (one job, 59,392 shots) therefore used **54 seconds together** — about 0.32 ms per
shot. The dashboard was not read between the two, so they are not split here. Total for the project so far: 63 seconds of
the 10-minute allowance.

**Summary.** P1 as a whole — question, steps, results, the corrections made along the way, limits — is written up in
`docs/p1-summary.md`.

**Release.** P0.5 and P1.0–P1.5 are released together as `v0.3.0`, archived on Zenodo.

## 2026-09-14 — P2 plan pre-registered

Plan: `docs/p2-plan.md`, written and committed before any P2 code or result. Subject: multi-sensor data association as
three-dimensional assignment, which is NP-hard — the problem P1's two-dimensional case deliberately avoided.

Checked before writing it:
- `scipy.optimize.milp` (SciPy 1.18.1, HiGHS) is available in the project environment. On a random 3 × 3 × 3 axial assignment it
  returned 4.029437, identical to brute force over all permutation pairs — so an exact baseline exists without a new dependency.
- The core reference (Deb, Yeddanapudi, Pattipati, Bar-Shalom 1997, IEEE TAES 33(2)) and the related quantum work cited in the plan
  were looked up and confirmed to exist.

Five hypotheses are fixed in the plan (H1 gates, H2 where Lagrangian relaxation fails, H3 solver-dependent penalties, H4 higher
optimum-vs-truth ceiling with three sensors, H5 hardware repeatability), plus a QPU budget of 3 minutes for P2 and a go/no-go
rule for putting three-dimensional QAOA on hardware.

## 2026-09-14 — P2.0: multi-sensor scene, tuple hypotheses and costs

Code: `src/p2_scene.py`. Tests: `tests/test_p2_scene.py` (12). Result: `results/p2_0-scene-20260914-140309.json`. No QPU.

**Set-up as implemented.** Three sensors sit on a 2 km circle around the scene, at 90°, 210° and 330°. Each reports a position.
The error comes from range (σ = 10 m) and bearing (σ = 0.02 rad, which is 40 m across the line of sight at 2 km). The covariance
attached to each measurement is evaluated at its reported position, not the true one. Other settings: P_D = 0.9, one expected
false alarm per sensor, 200 m clutter margin, 50 m target spacing, pairwise gate 9.21. For comparison, P1.0's innovation was
circular with about 23 m per axis; here each sensor's error ellipse is 10 × 40 m and points in a different direction.

**Choices the plan left open, made here:**
- A single-measurement tuple takes the cheaper of two readings — "target seen by one sensor" or "false alarm" (cost 0) — and
  records which one it took. Comparisons with the truth are made on the partition, so this label does not affect them.
- Without clutter the ln λ term is dropped and false alarms are forbidden. Every valid partition shifts by the same constant.
- All sensors share one clutter window, so λ is the same for each.

**Verification (independent routes):**
- Measurement covariance equals J · diag(σ_r², σ_θ²) · Jᵀ, with J from finite differences of the polar-to-Cartesian map.
- The fused position and the tuple cost match a numerical BFGS minimisation of scipy's Gaussian log-density — the cost to 6
  decimals. This held on more than 300 random tuples (with and without missed detections and clutter) and on every pure-mode tuple.
- Every enumerated tuple is accounted for: kept + removed by gate + removed as impossible = ∏(M_s + 1) − 1.
- On low-noise pure scenes the truth has the lowest cost of all 36 partitions.
- The gate rejects **378 of 38,683 true pairs = 0.98%**, against the 1.00% expected for a 99% chi-square gate. The same check is
  kept as a test with a separate seed. Evaluating the covariance at the reported position does not visibly bias the gate.

**Results (200 augmented scenes per size, seed 2026):**

| T | measurements / sensor | tuples mean | median | max | truth survives gating | truth tuples cut | targets unseen | singletons as target / false alarm |
|---|---|---|---|---|---|---|---|---|
| 2 | 2.83 | 26.1 | 25 | 53 | 0.960 | 9 | 0 | 0 / 1697 |
| 3 | 3.62 | 47.7 | 49 | 92 | 0.965 | 7 | 1 | 1 / 2171 |
| 4 | 4.58 | 71.2 | 68 | 165 | 0.960 | 8 | 1 | 91 / 2654 |
| 5 | 5.59 | 93.4 | 91 | 164 | 0.885 | 23 | 2 | 1301 / 2055 |
| 6 | 6.49 | 114.4 | 115 | 179 | 0.865 | 32 | 1 | 3521 / 373 |

Pure mode keeps exactly T³ tuples: 8, 27 and 64 for T = 2, 3, 4. In augmented mode no tuple was removed as impossible.

**Special cases, counted:**
- **Gating cuts the truth in 3.5–13.5% of scenes.** Each true pair is rejected about 1% of the time, and a full tuple has three
  pairs, so larger scenes lose the truth more often. In those scenes no solver can return the true association.
- **The singleton label flips with scene size.** "Target seen by one sensor" costs +0.40 at T = 2 but −0.07 at T = 6. The clutter
  window grows with the target spread, so λ falls. The label sits on a knife edge, but the cost is small either way and partitions
  are unaffected. Any later result that uses the label must say so.
- Targets missed by all three sensors: 5 of 4,000, as expected for (1 − 0.9)³.

**Consequence for H4 (not yet a result):** the optimum can equal the truth only where the truth survives gating. That caps it
at 0.965 at T = 3, against the 0.822 measured in P1.0 at T = 3. H4 is tested in P2.1, once exact optima exist.

Next: P2.1 — exact ILP baseline and the brute-force gate.

## 2026-09-14 — P2.1: exact ILP baseline, brute-force gate, and H4

Code: `src/p2_ilp.py`. Tests: `tests/test_p2_ilp.py` (7). Result: `results/p2_1-ilp-20260914-144533.json`. No QPU.
One variable per kept tuple, one equality constraint per real measurement, solved with `scipy.optimize.milp` (HiGHS)
with the relative MIP gap set to 0. The independent check enumerates every valid partition by exact-cover search, using no
costs to prune.

**H1 (ILP part) — held.**

| mode | T | checked | skipped (over 200,000 partitions) | cost mismatch | same partition |
|---|---|---|---|---|---|
| augmented | 1 | 200 | 0 | 0 | 200 |
| augmented | 2 | 200 | 0 | 0 | 200 |
| augmented | 3 | 199 | 1 | 0 | 199 |
| augmented | 4 | 189 | 11 | 0 | 189 |
| pure | 2 | 50 | 0 | 0 | 50 |
| pure | 3 | 50 | 0 | 0 | 50 |

In total 888 instances were checked, with the largest cost difference 1.4 × 10⁻¹⁴. Every solver status was optimal, every ILP
answer re-checked as a valid partition, and there were no near-ties. Enumeration reached 193,928 partitions on one instance.
The 12 skipped instances are counted here, not dropped. The ILP took about 4 ms per scene, and at most 11 ms for 203 variables.

**H4 — failed.** The prediction was that three fused sensors would make the optimum equal the truth *more* often than P1.0's
0.822. It did so far less often:

| T | scenes | optimum = truth | 95% interval | truth cut by gate | truth feasible but costlier |
|---|---|---|---|---|---|
| 2 | 200 | 0.415 | 0.349–0.484 | 7 | 110 |
| **3** | **500** | **0.274** | **0.237–0.315** | 25 | 338 |
| 4 | 200 | 0.190 | 0.142–0.250 | 19 | 143 |
| 5 | 200 | 0.145 | 0.103–0.200 | 29 | 142 |
| 6 | 200 | 0.100 | 0.066–0.149 | 25 | 155 |

At every size, whenever the truth survived gating it never cost less than the ILP optimum (0 cases). The failure is therefore
in what the model prefers, not in the solver.

**Diagnosis, added after the result — exploratory, not pre-registered.**

*How the optimum differs from the truth* — in the 363 T = 3 scenes where they differ (a scene can show several of these):
- a clutter measurement joined to a target's tuple: 280
- measurements of different targets joined into one tuple: 219
- a target's measurement left on its own: 53
- truth cut by the gate: 25

*One factor at a time* — T = 3, 300 scenes, the same scene seed for every variant:

| variant | optimum = truth | 95% interval |
|---|---|---|
| default | 0.303 | 0.254–0.358 |
| no clutter | 0.630 | 0.574–0.683 |
| P_D = 1 | 0.560 | 0.503–0.615 |
| pure (P_D = 1, no clutter, no gate) | 0.737 | 0.684–0.783 |
| spacing 100 m | 0.480 | 0.424–0.536 |
| spacing 200 m | 0.587 | 0.530–0.641 |
| bearing σ 0.005 rad (about 10 m round) | 0.833 | 0.787–0.871 |
| bearing σ 0.005 rad and no clutter | 0.933 | 0.899–0.956 |

Reading:
- **The biggest single factor is the 40 m cross-range error.** Each sensor's ellipse covers a large area, so clutter often falls
  inside a target's gate. When a sensor missed the target, joining that clutter really is the more likely explanation under the
  model. With about 10 m round errors the share rises to 0.833.
- **Even with no clutter, no missed detections and no gate, only 0.737 of scenes are solved to the truth.** Targets 50 m apart
  with 40 m cross-range errors are ambiguous from the data alone.
- **Why the hypothesis was wrong:** P1.0 associated measurements with *tracks whose predicted positions were known*. A
  single-instant multi-sensor scene has no such anchor — the target positions must come from the measurements themselves.
  "Comparable noise" was not comparable: 10 × 40 m ellipses per sensor against 23 m round innovations with a known prediction.
- **Not tested:** whether the generalised likelihood ratio — which fits the target position to the very measurements it scores —
  adds to the clutter joining, compared with a likelihood that integrates over the position. That is left as an open question;
  the pre-registered cost is kept.

**Consequences.**
- The P2.3–P2.5 solver comparisons are scored against the ILP optimum, so they are unaffected.
- Accuracy against the truth in the benchmark must be reported together with these limits.
- The planned P2.4 sweep does not vary bearing error, which turned out to matter most. Adding it would change the
  pre-registered plan and needs a separate, logged decision.

Next: P2.2 — QUBO for multi-sensor assignment and its gate against the ILP.

## 2026-09-14 — P2 plan, amendment 1: bearing error added to the P2.4 sweep

Decision by the author after reading the P2.1 diagnosis. The P2.4 sweep also varies bearing error, over 0.005, 0.01 and 0.02 rad.
It is recorded in `docs/p2-plan.md` under "Amendments"; the original text is left unchanged. The amendment changes nothing else:
H4 stays failed and is not re-tested under the new dimension as if that had been planned.

## 2026-09-14 — P2.2: QUBO for multi-sensor assignment, and its gate

Code: `src/p2_qubo.py`. Tests: `tests/test_p2_qubo.py` (6). Result: `results/p2_2-qubo-gate-20260914-145351.json`. No QPU.

**Formulation.** There is one variable per kept tuple, and each real measurement must be covered exactly once. The penalty is
A · Σ_m (cover_m − 1)². Expanded: Q_kk = c_k − A·n_k, where n_k is the number of measurements in tuple k; Q_kl = 2A × (the number
of measurements tuples k and l share); offset = A × (number of measurements). With two sensors this reduces to the P1 form, and a
test checks that. The default penalty is A = 2Σ|c| + 1, by the same argument as P1.1.

**Verification (independent routes):**
- On valid partitions (the ILP answer, and the truth when it survives gating), energy equals the partition cost.
- On 150 random bit strings, energy − cost equals A × squared cover violation, with the cover counted directly from the tuples.
- The brute-force argmin decodes to a partition whose cost equals the ILP optimum.

**H1 (QUBO part) — held.** Brute force over all 2^K states for K ≤ 20 variables, 100 scenes per setting:

| setting | T | tested | passed | skipped (K > 20) | infeasible | variables mean / max | quadratic terms mean (tested) |
|---|---|---|---|---|---|---|---|
| default | 1 | 94 | 94 | 6 | 0 | 10.9 / 34 | 19.6 |
| default | 2 | 32 | 32 | 68 | 0 | 25.6 / 54 | 50.1 |
| bearing 0.005 rad | 2 | 85 | 85 | 15 | 0 | 16.4 / 39 | 26.6 |
| bearing 0.005 rad | 3 | 38 | 38 | 62 | 0 | 22.0 / 37 | 27.8 |
| pure | 2 | 100 | 100 | 0 | 0 | 8.0 / 8 | 24.0 |
| P_D = 1, no clutter, gated | 3 | 77 | 77 | 15 | 8 | 16.0 / 27 | 79.5 |
| P_D = 1, no clutter, gated, bearing 0.005 rad | 3 | 91 | 91 | 0 | 9 | 3.6 / 8 | 1.8 |

**GATE PASSED: 517 / 517.** The skipped and infeasible scenes are counted, not dropped.

**Special cases, counted:**
- **Infeasible scenes (17).** With P_D = 1 and no clutter, a single-measurement tuple is impossible. When the gate cuts a true
  tuple, some measurement is left in no kept tuple, so neither the ILP nor the QUBO has any valid answer. `build_qubo` refuses
  such scenes; the gate checks the ILP status first and counts them.
- **The brute-force limit bites early.** At the default settings only 32 of 100 T = 2 scenes have 20 variables or fewer. The
  gate mostly covers T ≤ 2, plus the sparser T = 3 settings.
- **Small-penalty check (recorded, not part of the gate).** A = max|c| still leaves the optimum as the minimum in 514 of the
  517 tested instances. The 3 exceptions are degenerate T = 1 scenes where every kept tuple is a false alarm costing 0, so
  max|c| = 0 and the penalty vanishes. Any rule of the form A = max|c| needs a positive floor.

**For P2.5 (QAOA):** the smallest instances are pure T = 2, with 8 variables and 24 quadratic terms. Pure T = 3 has 27 variables,
beyond this project's simulator budget. The sparse "P_D = 1, no clutter, gated, bearing 0.005 rad" scenes at T = 3 have 3.6
variables on average and are close to trivial.

Next: P2.3 — greedy, Lagrangian relaxation with duality gap, simulated annealing.

## 2026-09-14 — P2.3: classical baselines against the exact optimum, and H2

Code: `src/p2_heuristics.py`, plus `lp_relaxation` added to `src/p2_ilp.py`. Tests: `tests/test_p2_heuristics.py` (6).
Result: `results/p2_3-heuristics-20260914-151102.json`. No QPU.

**Methods.**
- **Greedy:** take tuples cheapest first, skipping any that reuse a measurement.
- **Lagrangian relaxation (LR):** relax the sensor-3 constraints, which leaves a 2D assignment with dummies. Multipliers follow
  subgradient steps; every iteration recovers a feasible answer with a second 2D assignment.
- **Simulated annealing (SA):** the P1 routine and schedule — 64 restarts, 100 sweeps — on the P2.2 QUBO with A = max(max|c|, 1).

The LR inner problem has integral solutions, so the best possible Lagrangian bound equals the LP relaxation. The **duality gap is
therefore measured exactly, as ILP optimum − LP bound**, independently of how well the subgradient converges.

**Verification:**
- L(u) matches a separately built and solved integer program on 60 random multiplier vectors.
- LP bound ≤ optimum ≤ LR upper bound, and LR lower bound ≤ LP bound, on every test scene and every experiment scene.
  The run counted 0 violations of any of these.
- Every LR answer is a valid partition.

**How H2 was made operational** — written into the code header before the first run:
- "most" means LR equals the optimum in more than half the scenes, at clutter 0 and at clutter 0.5.
- "rises" means a higher gap share at clutter 2 than at clutter 0, and at spacing 25 m than at 100 m, with non-overlapping 95%
  Wilson intervals. The right direction with overlapping intervals counts as partly held.
- Overall: held if all three parts hold, failed if all three fail, partly held otherwise.

The first run computed every number but crashed while writing the JSON (numpy integers). After a one-line serialisation fix, the
rerun reproduced every printed number exactly, and that rerun is the saved file.

**Results (T = 4, 200 scenes per setting; SA on the first 40):**

| setting | share with gap [95%] | LR = optimum [95%] | LR certified | greedy optimal | SA best-of-64 optimal | SA feasible share |
|---|---|---|---|---|---|---|
| clutter 0 | 0.065 [0.038, 0.108] | 0.995 [0.972, 0.999] | 0.935 | 0.000 | 0.075 | 0.998 |
| clutter 0.5 | 0.080 [0.050, 0.126] | 0.995 [0.972, 0.999] | 0.915 | 0.380 | 0.200 | 0.694 |
| clutter 1 (default) | 0.140 [0.099, 0.195] | 0.985 [0.957, 0.995] | 0.860 | 0.300 | 0.100 | 0.709 |
| clutter 2 | 0.080 [0.050, 0.126] | 0.990 [0.964, 0.997] | 0.920 | 0.370 | 0.150 | 0.766 |
| spacing 25 m | 0.130 [0.090, 0.184] | 0.990 [0.964, 0.997] | 0.865 | 0.155 | 0.000 | 0.610 |
| spacing 100 m | 0.085 [0.054, 0.132] | 0.995 [0.972, 0.999] | 0.915 | 0.660 | 0.700 | 0.855 |
| *T = 2, default (100 scenes)* | 0.020 | 1.000 | 0.980 | 0.660 | 0.900 | 0.840 |
| *T = 6, default (100 scenes)* | 0.210 | 0.970 | 0.790 | 0.140 | 0.000 | 0.539 |

**H2 — partly held.**
- "Most" held, and strongly: LR returned the exact optimum in 99.5% of scenes at clutter 0 and at clutter 0.5.
- "Rises with clutter" held only as a direction: 0.080 at clutter 2 against 0.065 at clutter 0, with overlapping intervals. The
  shares are not monotone either — 0.140 at clutter 1 is the highest.
- "Rises with closer spacing" also held only as a direction: 0.130 against 0.085, with overlapping intervals.
- Outside the verdict, the gap share grows with the number of targets: 0.02 at T = 2, 0.21 at T = 6.

**Other findings:**
- **A duality gap rarely stops LR.** In scenes with a gap, LR still returned the optimum in 86–100% of cases; recovering a
  feasible answer from the relaxed pairs usually lands on it. The benchmark's "hard" subset (scenes with a gap) is therefore
  hard for the LP bound, not necessarily for LR.
- **The subgradient reached the LP bound closely.** The median shortfall was 0 in every setting; the largest were 0.29 and 0.57
  (clutter 0.5, spacing 25 m). The median number of iterations was 3–13.
- **SA is weak at this budget:** mostly feasible, rarely optimal — it gets stuck in feasible local minima. No penalty or
  schedule study was run for P2.

**Special cases, counted:**
- **Greedy fails completely without clutter, because of the cost convention.** With λ = 0 the ln λ term is dropped, so every cost
  is positive: single-measurement tuples cost about 12.5, pairs about 19.6 and triples about 28.1. Cheapest-first therefore picks
  only singletons — 100 / 100 all-singleton partitions in a separate check. The partition optimum is unchanged by the convention,
  but greedy's ordering is not. Any cheapest-first method must normalise per measurement before it is compared without clutter.
  The same shift also changes the QUBO's infeasible energies, and may affect SA at clutter 0; that was not tested.
- Infeasible scenes: 0. Bound violations: 0.

Next: P2.4 — the benchmark package (instance files, checker, baseline table, the sweep including bearing error), release and DOI.

## 2026-09-14 — P2.4: the benchmark package

Code: `src/p2_benchmark.py`, plus `greedy_normalised` and `measurement_reference` in `src/p2_heuristics.py`.
Tests: `tests/test_p2_benchmark.py` (5; 65 in the project). Output: `benchmark/p2/` — `instances.jsonl.gz` (2.1 MB),
`baselines.csv`, `summary.md`, `manifest.json`, and a hand-written `README.md` describing the format. No QPU.

**Contents.**
- **Sweep:** 540 settings (plan plus amendment 1) × 3 replicates = 1,620 instances. Each instance has its own seed
  [2031, setting index, replicate].
- **Each instance** carries: generator seed and parameters, sensors, measurements with covariances, the truth, every allowed
  tuple with its cost, the exact optimum, the LP bound and a gap flag.
- **The checker** needs only an instance and an answer. It uses nothing beyond the Python standard library and reports
  validity, cost, gap to the optimum and agreement with the truth. The baselines are scored through the same checker.

**Verification:**
- The ILP partition scores as valid and optimal with zero gap; the truth scores as equal to the truth.
- Reused, missing, unknown, malformed and empty answers are all rejected.
- Instances survive a write and read round trip unchanged, and each regenerates from its own seed alone.
- The per-measurement normalisation shifts every partition by the same constant.
- The command-line checker, run on trial instances with one deliberately broken answer and one unknown id, reported both.
- **Reproducibility:** a second full build produced a byte-identical decompressed instance file (SHA-256 `5d494e42962420dc…`)
  and identical baseline results, ignoring timing columns.

**Results (full table in `benchmark/p2/summary.md`):**

| | value |
|---|---|
| instances / infeasible | 1,620 / 14 |
| instances with an LP gap | 43 (2.7%) — 0.0% at σ_θ 0.005, 7.4% at σ_θ 0.02 |
| optimum = truth | 0.560 overall; 0.748 at σ_θ 0.005 down to 0.349 at 0.02; 0.349 at 25 m spacing |
| tuples per instance | mean 41, max 278 |

| method | valid | optimal | median gap when not optimal | median seconds |
|---|---|---|---|---|
| greedy | 0.987 | 0.527 | 3.86 | < 0.001 |
| greedy_normalised | 0.987 | 0.415 | 3.92 | < 0.001 |
| lagrangian | 0.990 | 0.987 | 0.26 | < 0.001 |
| annealing (64 × 100 sweeps) | 1.000 | 0.633 | 3.78 | 0.035 |

Annealing falls from 0.960 at T = 2 to 0.345 at T = 6. Lagrangian relaxation stays at 0.98 or above at every size.

**Special cases, counted:**
- **Greedy has no valid answer on 21 instances,** all with no clutter and P_D = 1. Without single-measurement tuples, a
  cheapest-first choice can leave a measurement with no tuple still available.
- **Lagrangian relaxation has no valid answer on 16 instances,** all with P_D = 1 *and* clutter. Recovery keeps the relaxed
  (i1, i2) pairs, and with P_D = 1 a pair of two real measurements must be completed by a sensor-3 measurement — (i1, i2, 0) is
  impossible. When the gate leaves too few, no iteration recovers a valid answer. This was not seen in P2.3, which used P_D = 0.9.
  With 5 more valid-but-not-optimal answers, these are the 21 instances of `hard_subset_lagrangian_not_optimal`.
- **The normalisation helps greedy only without clutter.** At clutter 0 it lifts greedy from 0.000 to 0.267 (P_D 0.8) and 0.385
  (P_D 0.9). With clutter it is worse: for example 0.281 against 0.607 at clutter 1, P_D 0.9. Plain costs reward joining
  measurements, which is right when clutter exists; the normalised keys order tuples by fit alone. Both variants stay in the
  table.
- Among the 43 LP-gap instances, Lagrangian relaxation still found the optimum in 38 (0.884). The LP-gap subset is hard for the
  bound more than for the method.
- 14 instances have no valid answer at all (P_D = 1, no clutter, a true tuple cut by the gate). They are kept and listed.

**Ready for release** as the benchmark named in the roadmap. The release and DOI need the author's approval before publishing.

## 2026-09-14 — Release v0.4.0

Approved by the author. P2.0–P2.4 and the benchmark are released together as `v0.4.0` and archived on Zenodo under the
project's concept DOI. `CITATION.cff` now names v0.4.0. P2.5 (QAOA on a simulator, H3, and the hardware go/no-go) is next.

Zenodo DOI for v0.4.0: 10.5281/zenodo.22745727. The concept DOI 10.5281/zenodo.22741037 resolves to it.

## 2026-09-14 — P2.5: QAOA on a simulator, H3, and the hardware go/no-go

Code: `src/p2_qaoa.py`. Tests: `tests/test_p2_qaoa.py` (5; 70 in the project). Result: `results/p2_5-qaoa-20260914-160839.json`.
No QPU.

**Set-up.** The instance sets and the operational form of H3 were written into the code header before the first run.
- **pure T = 2:** 30 instances, always 8 variables.
- **sparse T = 2:** 30 instances with bearing error 0.005 rad and 6–12 variables. Getting 30 took 104 generated scenes; 74 were
  rejected for having more than 12 variables.

Each instance was enumerated over all 2^K strings to get the exact A_crit. Every instance had A_crit > 0, and the max|c| floor of
1 was never needed.
- **Annealing:** the P1 routine at A = s × A_crit, at max|c| and at the safe penalty.
- **QAOA:** depths 1–3, at A = max|c| and A = 1.5 × A_crit, using the P1.4 simulator and optimiser.

**Verification:**
- The enumerated violation matches the QUBO energy: E − cost = A·V on every string.
- A_crit is confirmed by brute force: at A just above it the minimum is the optimum, and at 0.9 × A_crit the minimum is below it.
- The Ising conversion reproduces every enumerated energy.
- The simulator matches Qiskit's `Statevector` on three-dimensional circuits.

**Annealing, mean success per restart:**

| penalty | pure T = 2 | sparse T = 2 |
|---|---|---|
| 1.1 × A_crit | **0.654** | 0.481 |
| 1.5 × A_crit | 0.469 | **0.640** |
| 2 × A_crit | 0.410 | 0.567 |
| 5 × A_crit | 0.309 | 0.410 |
| 50 × A_crit | 0.240 | 0.184 |
| max\|c\| | 0.304 | 0.475 |
| safe | 0.246 | 0.202 |

**QAOA, mean P(optimal) per sample** (uniform guessing: 0.0039 for pure, 0.0010 for sparse):

| set | depth | A = max\|c\| | A = 1.5 × A_crit | paired difference (mean ± SE) | median difference | max\|c\| better in |
|---|---|---|---|---|---|---|
| pure | 1 | 0.0288 | 0.0246 | 0.0042 ± 0.0014 | 0.0054 | 87% |
| pure | 2 | 0.0595 | 0.0285 | 0.0310 ± 0.0028 | 0.0234 | 100% |
| pure | 3 | 0.0687 | 0.0304 | 0.0383 ± 0.0042 | 0.0395 | 97% |
| sparse | 1 | 0.0126 | 0.0112 | 0.0014 ± 0.0019 | 0.0002 | 57% |
| sparse | 2 | 0.0780 | 0.0546 | 0.0234 ± 0.0144 | 0.0026 | 60% |
| sparse | 3 | 0.1561 | 0.1210 | 0.0351 ± 0.0286 | **−0.0235** | 33% |

**H3 — partly held.**
- **Annealing part: held.** The best multiplier was 1.1 (pure) and 1.5 (sparse); both are ≤ 2.
- **QAOA part: partly held.** In the pure set the P1 result replicates clearly: the larger penalty wins at every depth, by more
  than 9 standard errors at p = 3. In the sparse set the mean difference is positive at every depth, but at p = 3 it is within
  2 standard errors. **Three instances carry it** (+0.58, +0.42, +0.33). Without them the mean is −0.010, the median is −0.024,
  and 1.5 × A_crit is better on two thirds of the instances. On the typical sparse instance, the P1 preference for max|c| does
  not replicate.

**Hardware go/no-go — GO by the registered rule, and a fragile one.**
- The rule is met by the sparse set at depth 1: mean P(opt) is 12.7× guessing (max|c|; 11.3× with 1.5 × A_crit), and the median
  estimated CZ count is 29. Every sparse instance is at least 6.7× guessing at p = 1.
- No other combination passes. Pure T = 2 needs 85 CZ even at p = 1 (24 ZZ terms), and sparse p = 2 needs a median of 67.
- **Fragility 1:** the CZ median comes from the first 5 instances, and their counts were 8, 20, 29, 79 and 85 — the estimate
  depends on each instance's number of ZZ terms (4–23).
- **Fragility 2:** the absolute signal is small. Median P(opt) at p = 1 is 0.008, which is about 17 optimal samples in 2,048 shots
  against about 2 from guessing.
- Consequence for P2.6: a three-dimensional hardware run is permitted, but only on instances whose own estimated CZ count is
  ≤ 60. The instance selection and the numeric predictions have to be registered before any submission, and the QPU use needs
  the author's approval.

**Stated limits:** 30 instances per set, noiseless simulation, one optimiser configuration, and a transpiled CZ count that is an
estimate for a generic heavy-hex model rather than a specific device.

Next: P2.6 — hardware. The P1.5 repeat for H5, and a small three-dimensional QAOA run on instances with ≤ 60 estimated CZ, with
predictions registered first.

## 2026-09-14 — P2.6 pre-registration: plan and predictions before any submission

The author chose to run both hardware experiments. Code: `src/p2_6_hardware.py`. Tests: `tests/test_p2_6_hardware.py` (3,
offline; 73 in the project). Plan: `results/p2_6-plan-20260914-162820.json`. **No job has been submitted.** The script refuses
to submit without a registered plan file, and when given one it re-transpiles and stops if any registered 3D circuit would
exceed 60 CZ.

**Rebuild checks, passed.** The 10 P1.5 2 × 2 instances reproduce P1.4's P(optimal) exactly with the stored p = 2
parameters. All 30 P2.5 sparse instances reproduce their optimum, variable count and P(optimal) to 1e-9.

**Device ranking from today's calibration data** (median CZ error / median readout error):
`ibm_kingston` 0.0020 / 0.0088, `ibm_fez` 0.0029 / 0.0101, `ibm_marrakesh` 0.0032 / 0.0109.

**Experiment A — H5 repeat.**
- On `ibm_fez`, the best device other than `ibm_kingston`, the device used in P1.5.
- The same 10 pure 2 × 2 instances at p = 2 as P1.5, 22 CZ each, simulator mean P(optimal) 0.5445.
- **Deviation from the plan, stated now:** H5 was registered as "another day and another device". This run is on the same
  calendar day as P1.5 (several hours later, a separate calibration window), so it tests the *device* half only. The
  *day* half stays untested unless the run is repeated on a later date.

**Experiment B — three-dimensional QAOA, p = 1.**
- On `ibm_kingston`.
- Selection by the registered rule — the first 10 P2.5 sparse instances whose transpiled circuit has at most 60 CZ — gave
  instances 0, 2, 4, 5, 6, 8, 10, 11, 12, 13. Instances 1, 3, 7 and 9 exceeded 60.
- CZ counts: 32, 22, 8, 57, 57, 8, 15, 53, 49, 17. Simulator mean P(optimal) 0.0164; uniform guessing 0.0011.
- The selection keeps the sparser instances, so its simulator mean is above the full set's 0.0126.

One job per device, 12 circuits each (10 QAOA + 2 readout calibration), 2048 shots: 49,152 shots in total, an estimated 16 s
of QPU time at P1.5's rate. The P2 budget is 3 minutes.

**Predictions, fixed before any result exists.** Retention = corrected hardware mean P(optimal) / simulator mean.
1. **A1 (H5):** retention between 0.84 and 0.94; point estimate 0.87. The reasoning: P1.5 kept 0.890 on a device with a median CZ
   error of 0.0019, and `ibm_fez`'s higher error (0.0029) over 22 CZ costs about 2 points. Graded: held inside 0.84–0.94,
   partly held inside 0.79–0.99, failed otherwise.
2. **A2:** corrected mean P(optimal) on `ibm_fez` is below P1.5's 0.4847 on `ibm_kingston`.
3. **B1 (go rule on hardware):** corrected mean P(optimal) is at least 5 × guessing, that is ≥ 0.0055.
4. **B2:** retention between 0.75 and 1.05; point estimate 0.88. P1.5 kept 0.90 at 58 CZ on the same device, and these circuits
   have 8–57.
5. **B3:** readout correction changes the mean P(optimal) by less than 15% of its raw value.

Sampling noise, stated in advance: at P(optimal) ≈ 0.016 with 2048 shots on each of 10 circuits, the standard error of the mean
is about 0.0009, so B2's retention carries roughly ±0.06 from shots alone.

The submission waits for the author's explicit approval to use QPU time.

## 2026-09-14 — P2.6 results: hardware, checked against the predictions

Approved by the author after the pre-registration commit `4ea93d0` was on GitHub. Submitted with the registered plan file.
Re-transpiling gave the same CZ counts as the plan for every circuit.
- Job `dajrv77i3e6s738qm8dg` on `ibm_fez`; job `dajrv7omhr3c73e9c6r0` on `ibm_kingston`.
- Result: `results/p2_6-hardware-20260914-163413.json`. **QPU usage reported by the jobs: 9 s + 9 s = 18 s.**

**Experiment A — the P1.5 2 × 2 p = 2 circuits on `ibm_fez`:**

| | simulator | hardware raw | hardware corrected | retention (corrected) |
|---|---|---|---|---|
| P2.6, `ibm_fez` | 0.5445 | 0.4730 | **0.4856** | **0.892** |
| P1.5, `ibm_kingston` | 0.5445 | 0.4762 | 0.4847 | 0.890 |

Per instance, retention ran from 0.81 to 1.01. The shot-noise standard error of the corrected mean is about 0.003
(retention ±0.006).

**Experiment B — three-dimensional QAOA, p = 1, on `ibm_kingston`:**

| instance | CZ | simulator P(opt) | hardware corrected | ratio |
|---|---|---|---|---|
| 0 | 32 | 0.0078 | 0.0065 | 0.84 |
| 2 | 22 | 0.0212 | 0.0275 | 1.30 |
| 4 | 8 | 0.0230 | 0.0160 | 0.69 |
| 5 | 57 | 0.0032 | 0.0081 | 2.48 |
| 6 | 57 | 0.0032 | 0.0045 | 1.39 |
| 8 | 8 | 0.0586 | 0.0585 | 1.00 |
| 10 | 15 | 0.0289 | 0.0361 | 1.25 |
| 11 | 53 | 0.0032 | 0.0040 | 1.23 |
| 12 | 49 | 0.0027 | 0.0017 | 0.65 |
| 13 | 17 | 0.0121 | 0.0096 | 0.80 |
| **mean** | | **0.0164** | **0.0173** (raw 0.0166) | **1.052** |

Guessing is 0.0011, so hardware reached **15.7× guessing**. The shot-noise standard error of the mean is about 0.0009
(retention ±0.054). P(feasible): simulator 0.114, hardware corrected 0.105.

**Predictions:**
1. **A1 — held.** Retention 0.892, inside 0.84–0.94; the point estimate was 0.87.
2. **A2 — failed.** `ibm_fez` gave 0.4856, not below `ibm_kingston`'s 0.4847. The difference, 0.0009, is well inside the shot
   noise (about 0.003); the higher median CZ error did not show up in these 22-CZ circuits.
3. **B1 — held.** Corrected mean 0.0173 ≥ 0.0055, and 15.7× guessing.
4. **B2 — failed, by 0.0015.** Retention 1.052, just above the registered upper bound of 1.05. With about ±0.05 from shot noise
   alone, it is consistent with "no measurable loss" — but the registered range was missed.
5. **B3 — held.** Readout correction raised the mean by 4.2% (2.7% in A), under 15%.

**H5 — partly held.**
- **Device half: held, strikingly.** On a different device, with a 50% higher median CZ error, retention was 0.892 against P1.5's
  0.890.
- **Day half: not tested.** Same calendar day, as stated in the pre-registration.

**Exploratory, after the results — not pre-registered.**
- **In B, retention per instance rises with CZ count** (Spearman +0.52). The instances above 1 are mostly those whose simulator
  P(opt) is tiny (0.003, about 3× guessing). There, a handful of extra optimal shots — 16 against an expected 6.5 in 2048 —
  doubles the ratio.
- **Checked one explanation offline, using the stored counts.** Relaxation (T1) pushes qubits towards 0. Every optimal
  partition here selects fewer tuples (4–6 ones) than the simulator's average string (4.8–8.4), so a bias towards 0 would favour
  the optimum. Hardware strings did carry fewer ones than the simulator on **all 10 instances** (mean −0.11). However, that shift
  does not correlate with CZ count (+0.05) and only weakly with retention (+0.32), so it does not explain the CZ pattern. Shot
  noise on tiny probabilities is the simpler reading.
- **Consequence:** retention is a poor metric when the simulator's P(opt) is near guessing. For such instances, the ratio to
  guessing and the absolute counts are the numbers to report.

**QPU time.** P2 used 18 s against its 3-minute budget. The project total is 81 s. The job-reported usage suggests about
8 m 39 s remain in the current allowance; the dashboard was not read.

Next: P2.7 — summary of P2, release and DOI.

## 2026-09-14 — P2.7: summary of P2

P2 as a whole is written up in `docs/p2-summary.md`: the question, the steps, the five hypotheses with their outcomes, the
results, every correction and deviation, the limits, QPU time, and where it points. No new experiment was run; every number
there is taken from the entries above.

Hypotheses: H1 held, H2 partly held, H3 partly held, H4 failed, H5 partly held (device half only). QPU time: P2 18 s, project 81 s.

The v0.5.0 release and DOI wait for the author's approval.

## 2026-09-14 — Release v0.5.0

Approved by the author. P2.5–P2.7 are released together with everything since v0.4.0 as `v0.5.0`, archived on Zenodo under the
project's concept DOI. `CITATION.cff` now names v0.5.0. P2 is complete.

Zenodo DOI for v0.5.0: 10.5281/zenodo.22748338. The concept DOI resolves to it.

## 2026-09-14 — P3 plan pre-registered: a reproduction study of QANTIS

Plan: `docs/p3-plan.md`, written before any P3 code or result.

**Literature search.** Two independent searches looked for quantum approaches to data association in tracking. Findings, each
from the paper's own text:
- **QANTIS** (arXiv:2603.00785, 2026) is the only gate-model result found. It has an 11-qubit hardware instance and a public
  repository. It is **chosen**.
- McCormick et al. (arXiv:2110.08346), Ihara (*Sci. Rep.* 2025) and Zaech et al. (CVPR 2022) are D-Wave annealing studies.
  Their results are figures only, or their data are no longer public, or their instances are far beyond 12 qubits.
- Cloud annealing access was checked the same day. D-Wave Leap offers a trial of 1 minute of QPU time valid for one month.
  D-Wave has not been on Amazon Braket since November 2022.

**The plan registers:**
- four claims of the paper (C1 instance, C2 noiseless method, C3 hardware, C4 greedy), each with its grading rule
- four added questions, including a random-sampling baseline for the paper's "best of top-10 bitstrings" quality metric,
  with its decision rule fixed in advance
- a hardware go rule and a QPU budget of 3 minutes
- how the authors' MIT-licensed code may and may not be used

**Correction to earlier entries.** The P2 plan's related-work list says QANTIS "credits Stollenwerk et al. with the first QUBO
formulation of the problem for annealing". That accurately repeats QANTIS's claim, but the claim does not hold up. QANTIS's
reference [18] is an air-traffic trajectory paper (arXiv:1711.04889), and no data-association paper by Stollenwerk was found.
The earliest traceable data-association QUBO found is Govaers, Stooß and Ulmke (IEEE MFI 2021). The P2 plan text is left as
registered; this entry is the correction.

## 2026-09-14 — P3.0: source audit of QANTIS

Record: `docs/p3-sources.md`. Sources: the paper (arXiv:2603.00785v1, HTML), the public repository `neuraparse/qantis` at `c17c2b5`
(cloned outside this repository, nothing copied in), and the FPC-QAOA source arXiv:2512.21181. No P3 code, no QPU.

**Main findings, with what was confirmed and how:**
- **The headline metric is confirmed.** The script takes the 10 most frequent bitstrings, evaluates xᵀQx and divides the best by
  |Hungarian objective|. It is not P(optimal).
- **Parameter binding bug — confirmed on Qiskit 2.5.2.** `QAOAAnsatz.parameters` lists all β before all γ, but the script binds
  an interleaved [γ₁, β₁, …] list to it. This affects the analytical initial-schedule circuit, which the paper credits with 64.1%
  at p = 3. COBYLA-optimised angles bind correctly. Whether the private code shares the bug is unknown.
- **Bit order — partly confirmed.** Qiskit count keys are little-endian, and the script reads them left to right. Whether this
  mirrors the variables depends on `to_ising`, to be confirmed in P3.2.
- **The public solver optimises all 2p QAOA angles.** It uses the schedule only as a starting point, so it is not the fixed-
  parameter-count method the paper and its source describe. Confirmed by reading the code.
- **The code's association cost includes ln(clutter density = 1e-5)**, a shift of −11.51 missing from the paper's equation. Gating
  sets cost 0 instead of removing a variable. The missed-detection and false-alarm costs (5.0, 3.0) exist only in code.
- **"Hungarian optimal" in the code is a maximum-cardinality assignment** on the penalised diagonal, not necessarily the QUBO
  minimum.
- **"ISA" is defined as two-qubit depth but used as a gate count.** The script counts cx/ecr, which is 0 on CZ-native Heron.
- **Provenance.** The repository attributes arXiv:2110.08346 to "Stollenwerk et al., *Adiabatic Quantum Computing for Multi Object
  Tracking*, Fraunhofer FKIE". That merges McCormick et al. (the arXiv id), Zaech et al. (the title) and Govaers et al. (FKIE).
  The λ = 1.5·max|c| rule was found in none of them.
- **Materials.** The paper's ancillary bundle still returns 404. The repository says hardware data go to reviewers on request.

**Consequences, without changing the plan:**
- C1 will report both the code's "Hungarian" value and the brute-force QUBO minimum.
- C2 will simulate the paper's method, the public code's method and the misbound initial circuit, and grade C2 on the paper's.
- Q1 will evaluate the metric in both bit orders.

These are findings about a published artefact, reported neutrally. Contacting the authors remains subject to the author's approval.

Next: P3.1 — rebuild the instance, check −92.4 and greedy, brute force over 2^11.

## 2026-09-14 — P3.1: the QANTIS instance rebuilt; C1 and C4

Code: `src/p3_qantis_instance.py`, re-implemented from the paper and the audit, with no code copied. Tests:
`tests/test_p3_qantis_instance.py` (8; 81 in the project). Result: `results/p3_1-instance-20260914-184805.json`. No QPU.

**Verification.**
- Costs match scipy's Gaussian log-density, plus the clutter term in the "code" variant.
- On 2,000 random bit strings E(x) = cost(x) + λ·V(x) − λ(N + M), with cost and V counted directly.
- The Hungarian-as-coded value equals the best maximum-cardinality association, found by enumeration.
- Brute force matches the enumeration of all valid associations.
- **Cross-check against the authors' own code**, run from the clone at `c17c2b5`: identical Q (max |difference| 0), identical
  λ = 15.344812, identical Hungarian objective −92.354924.

**The instance.**
- Measurement 0 fails the gate for both tracks, so its two x variables carry cost 0.
- 11 variables and 21 quadratic terms; λ = 15.3448.
- The costs (code variant) are −9.813 and −10.230 for track 0, and −8.401 and −6.562 for track 1.

| cost variant | Hungarian as coded | brute-force minimum | optimal association | next energy level |
|---|---|---|---|---|
| **code** (with ln clutter) | **−92.3549** | −92.3549, unique | track 0 → meas 2, track 1 → meas 1, meas 0 false alarm | −90.0997 |
| paper's Eq. (no clutter term) | −32.8452 | −32.8452, unique | track 0 → meas 2, track 1 → meas 0 (ungated, cost 0), meas 1 false alarm | −32.4285 |

**C1 — reproduced.** −92.3549 rounds to the paper's −92.4 (difference 0.045, inside the registered ±0.05). It is also the true
QUBO minimum over all 2,048 strings, not just the maximum-cardinality value.
- **Caveat:** the value comes out only with the repository's cost, which includes ln(clutter density). The paper's own cost
  equation gives −32.85 and a *different* optimal association, one that uses an ungated pair at cost 0. The paper's number
  therefore depends on code details the paper does not state.

**C4 — reproduced.** The code's greedy (GNN) picks the optimal association.
- **Caveat:** the objective the code reports for GNN counts only the chosen pairs (−80.01); the full QUBO energy of the same
  association is −92.35. "GNN 100%" in Table 14 is right about the association, not about the reported number. Under the paper's
  cost equation GNN would not be optimal (−31.02 against −32.85).

**For the next steps.** The ground state is unique, but the next level sits only 2.26 above it on an energy scale of about 90.
That matters for how "quality" is scored (Q1) and for what QAOA must resolve.

Next: P3.2 — the method on a noiseless simulator (C2) and the metric baseline (Q1).

## 2026-09-14 — P3.2: QANTIS QAOA on a noiseless simulator; C2 and the metric baseline

Code: `src/p3_qantis_qaoa.py`. Tests: `tests/test_p3_qantis_qaoa.py`. Cross-check tool: `tools/p3_repo_crosscheck.py`, run in a
separate environment (qiskit 2.5.2, qiskit-optimization 0.7.0) against the clone at `c17c2b5`.
Results: `results/p3_2-qaoa-20260914-190507.json`, `results/p3_2-repo-crosscheck-20260914-190507.json`. No QPU.

**Set-up.**
- Instance: P3.1's instance (optimum −92.3549; 13 feasible strings of 2,048; uniform P(optimal) 0.00049).
- Circuit: the QAOA layer as in `QAOAAnsatz`, with the unscaled Ising Hamiltonian.
- Four methods: A, the paper's FPC-QAOA (6 trainable coefficients); B, the public code (all 2p angles trained, from the start
  point as the code binds it); C, the analytical initial schedule, bound correctly; D, the same schedule bound the way the public
  hardware script binds it.
- Training: COBYLA, 100 iterations, minimising ⟨H⟩.
- The paper's quality metric (best of the 10 most frequent of 4096 shots, divided by the optimum), repeated over 200 samples, with
  correct and reversed bit order.

**Cross-check against the authors' environment.**
- **`to_ising` maps variable i to qubit i** (maximum difference 4.5 × 10⁻¹³; reversed order 148). This confirms audit finding 2.2:
  the public hardware script evaluates every bitstring in mirror order.
- **`QAOAAnsatz` lists β before γ** in qiskit 2.5.2, confirming audit finding 2.1 in the authors' toolchain.
- The repository's own `FPCQAOASolver`, which reports its best sample, returned 0.882, 0.909 and 0.869 of the optimum at
  p = 1, 2, 3. The paper's simulator quality is 51.3%, 100% and 90.9%.
- The tests also confirm that our simulator equals `QAOAAnsatz` + `Statevector`, both bound by name and bound as the script binds.

**Results (mean over 200 samples of 4096 shots):**

| method | p | P(optimal) | P(feasible) | top-10 quality | top-10, reversed bits | best of all samples |
|---|---|---|---|---|---|---|
| A paper FPC | 1 | 0.0000 | 0.004 | 0.610 | 0.237 | 0.977 |
| A paper FPC | 2 | 0.0003 | 0.024 | 0.813 | 0.691 | 0.972 |
| **A paper FPC** | **3** | **0.0020** | **0.006** | **0.836** | 0.430 | 1.000 |
| A paper FPC | 4 | 0.0156 | 0.033 | 1.000 | 0.669 | 1.000 |
| B public code | 3 | 0.0001 | 0.030 | 0.641 | 0.447 | 0.977 |
| C initial, correct | 3 | 0.0002 | 0.005 | 0.575 | 0.585 | 0.985 |
| D initial, as bound | 3 | 0.0001 | 0.004 | 0.820 | 0.602 | 0.948 |
| **uniformly random bitstrings** | — | 0.0005 | 0.006 | **0.582** (p95 0.866) | 0.584 | **0.995** |

All four depths for every method are in the result file.

**C2 — reproduced, as registered.** Method A at p = 3 reaches a mean quality of 0.836, above the 0.608 threshold.

**Q1 — the headline metric is not informative, by the registered rule.**
- Uniformly random bitstrings reach a mean quality of 0.582, with a 95th percentile of **0.866**. The paper's 64.1% is below that.
- **43% of random 4096-shot samples score 0.641 or more.**
- Why: only 5.2% of the 2,048 strings reach 0.641, but among 10 strings drawn almost at random, at least one does about 41% of the
  time (1 − 0.948¹⁰).
- The paper's simulator measure (best sample) is weaker still. In 4096 uniform shots over 2,048 states the optimum itself appears
  in 85.5% of samples (86.5% in theory). Random sampling scores 0.995 on average, higher than the repository solver's
  0.87–0.91.

**Q2 — standard metrics.** P(optimal) stays near the uniform level at p ≤ 3 for every method: at most 0.0020, against uniform
0.0005. Only A at p = 4 is clearly concentrated (0.016, 32× uniform, and top-10 quality 1.000). ⟨E⟩/optimum stays at 0.28 or
below and is negative for the untrained schedules. On this instance a noiseless 11-qubit QAOA at these depths is barely
distinguishable from random sampling except at p = 4.

**Q3 — penalty rule.** λ = 1.0 · max|c| (10.23) keeps the same optimal string. P(optimal) for method A: 0.0013 / 0.0007 / 0.0009 at
p = 1, 2, 3, against 0.0000 / 0.0003 / 0.0020 with the paper's 1.5. There is no consistent difference at these tiny values, so P1's
preference for the smaller rule is neither confirmed nor contradicted here.

**Exploratory, after the results.**
- **The misbound circuit D scores 0.820 at p = 3,** higher than the correctly bound schedule C (0.575). With a metric this close to
  random, a wrong circuit can outscore the right one.
- **Reading the bits in reverse,** as the public script does, changes the score substantially — A at p = 3 drops from 0.836 to
  0.430 — without any change to the quantum state.
- **The repository solver's reported qualities, 0.869, 0.882 and 0.909, are exactly the energy levels 7, 6 and 3 of this instance**
  divided by the optimum. The lowest ten levels / optimum are 1.000, 0.976, 0.909, 0.905, 0.889, 0.882, 0.869, 0.866, 0.866, 0.866.
  The paper's "90.9%" at p = 3 is one of these levels.

**Consequence for P3.4 (hardware).**
- The go rule is met formally: C1 was reproduced, C2 was reproduced, and the budget question is still open.
- But Q1 shows that the hardware headline cannot distinguish a working circuit from noise. A hardware run judged by the same
  metric could not confirm or refute anything.
- If hardware is used, it should be judged on P(optimal), P(feasible) and the energy distribution against the uniform baseline.
  Before any submission that needs the author's decision: P3.4's success criterion is registered as the paper's metric (C3).

Next: the author decides whether P3.4 goes ahead. P3.3 (the 19-qubit instance on the simulator) does not depend on that decision.
