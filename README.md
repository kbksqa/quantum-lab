# quantum-lab

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22741037.svg)](https://doi.org/10.5281/zenodo.22741037)

Hands-on experiments in quantum algorithms, focused on **combinatorial problems that appear in multi-sensor tracking and planning** — multi-target data association (MTDA), assignment, and decision making under uncertainty.

Every experiment is run twice: on a classical simulator and, where it fits, on **real quantum hardware** (IBM Quantum, Open Plan). Results — including the failures — are recorded in `results/` and in the research log.

> All data in this repository is **synthetic or public**. Nothing here originates from any operational system.

## Why this repository exists

I am an engineer with two decades of experience in multi-sensor data fusion and target tracking, now working toward research in quantum information theory. Most quantum algorithm research has never met a real tracking problem; most tracking engineers cannot read a quantum paper. This repository is my attempt to stand in both places, in public, one experiment at a time.

## Roadmap

| ID | Experiment | Status |
|----|------------|--------|
| P0 | Grover search: amplitude amplification on a simulator and on real hardware | done — simulator matches theory; run on `ibm_kingston` |
| P0.5 | Readout error versus gate error, on three devices | done — readout recovers only 1.5–3.3 pp; most loss is from gates |
| P1 | Assignment / data association as QUBO — brute force vs simulated annealing vs QAOA ([plan](docs/p1-plan.md)) | in progress — P1.0 baseline · P1.1 QUBO gate passed (588 / 588) · P1.2 penalty study · P1.3 annealing baseline done |
| P2 | **Reproducible MTDA benchmark**: synthetic scenario generator (clutter, missed detections) plus classical and quantum baselines | planned |
| P3 | Reproduction study of a published quantum tracking / planning result | planned |
| P4 | Technical report, archived with a DOI | planned |

## Getting started

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

python src/p0_grover.py                 # simulator only
python src/p0_grover.py --hardware      # also run on IBM Quantum (needs a free account)
```

Save your IBM Quantum token once:

```python
from qiskit_ibm_runtime import QiskitRuntimeService
QiskitRuntimeService.save_account(channel="ibm_quantum_platform", token="YOUR_TOKEN")
```

## Repository layout

```
src/        experiment code, one file per experiment
results/    raw outputs and run summaries (kept in git on purpose — they are the evidence)
docs/       research log, notes, derivations
notebooks/  exploratory work
```

## How to cite

See `CITATION.cff`. Each tagged release is archived on Zenodo and receives a DOI.

## License

Apache License 2.0 — see `LICENSE`.
