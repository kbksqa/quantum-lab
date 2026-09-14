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
