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
