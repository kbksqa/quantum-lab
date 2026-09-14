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
