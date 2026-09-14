# P4 plan — technical report on P0–P3, archived with a DOI

**Status: written on 2026-09-14, before any manuscript text.** P4 runs no new experiment. What is fixed in advance here is what the
report may claim, how every number in it is tied to a committed result, and which decisions belong to the author before anything
is published.

## Purpose

- Present the whole project — P0 to P3 — as one citable technical report.
- Serve as a public record of the author's research practice: pre-registration, hard gates, corrections kept, a reproduction study.
  The report is meant to be readable as a writing sample for graduate applications in quantum information.
- Put the P3 findings about a published result on record in a form that can be answered, cited and corrected.

## Audience

Researchers in quantum optimisation who have not worked on tracking, and tracking engineers who have not worked on quantum
computing. The report explains each side's basics in a paragraph, not a chapter.

## Working title

*Pre-registered small-scale experiments on quantum optimisation for multi-target data association: exact baselines, a reproducible
benchmark, IBM hardware runs and a reproduction study*

The title is to be shortened by the author if wished.

## Rules the report follows

1. **No new results.** Every number comes from a file in `results/` or `benchmark/` that is already committed and released.
   Nothing is re-run to "improve" a figure.
2. **Every number is traceable, and checked by machine.**
   - A script (`tools/p4_numbers.py`) reads the committed result files and writes every number the manuscript uses to one table.
   - The manuscript takes its numbers only from that table.
   - A test fails if any number in the table no longer matches its source file.
3. **Failures and corrections are reported with the same weight as successes.** That includes H4 (P2) failed; the P1.2 study bug;
   the wrong expectations in P1.4 and in H4's reasoning; P2.3's serialisation crash; H5's day half untested; C3 not tested.
4. **No claim of quantum advantage**, and no statement stronger than the grade a claim received in the log.
5. **Statements about the QANTIS paper are limited to what `docs/p3-report.md` confirms**, with its limits: public code only;
   noiseless simulation; one instance per size.
6. **All data are synthetic or public.** Nothing operational, no unit or system names.
7. **References are checked.** Every cited work is looked up and its bibliographic details confirmed before it is cited — the lesson
   of the QANTIS citation error.

## Structure (target 14–20 pages plus appendices)

| section | content | source |
|---|---|---|
| Abstract | question, what was done, the four main findings, limits | all |
| 1 Introduction | why data association; why small, checkable experiments; contributions | README, plans |
| 2 Way of working | pre-registration, hard gates, independent checks, append-only log, releases with DOIs | plans, log |
| 3 Two-dimensional assignment (P1) | QUBO gate; penalty is solver-dependent; QAOA on `ibm_kingston` | `docs/p1-summary.md` |
| 4 Multi-sensor assignment (P2) | ILP/QUBO gates; H4 failure and diagnosis; Lagrangian relaxation; benchmark; 3D QAOA on hardware; H5 | `docs/p2-summary.md`, `benchmark/p2/` |
| 5 Reproduction of QANTIS (P3) | instances; method; metric against random sampling; code defects; what was not tested | `docs/p3-report.md` |
| 6 Lessons across the project | penalties per solver; metrics need random baselines; shallow circuits kept ~90% on hardware; how bugs were caught | log |
| 7 Limits | sizes, synthetic data, noiseless simulation for P3, one calibration window per hardware run | summaries |
| Data and code availability | repository, releases, DOIs, how to rerun | README, CITATION |
| AI-assistance disclosure | wording decided by the author (see decisions) | — |
| Appendix A | P0 and P0.5 (Grover, readout versus gate error) | log |
| Appendix B | benchmark format and checker | `benchmark/p2/README.md` |

**Figures** are generated only by scripts from committed results; no hand-drawn plots. A first list:
- P1 penalty sweep for annealing and QAOA
- P2 optimum-equals-truth against bearing error
- P2 baselines by target count
- simulator against hardware retention for P1.5 and P2.6
- P3 metric distribution for QAOA against uniform sampling

## Decisions that belong to the author (P4.0)

These are not defaults; each is asked before drafting starts.

1. **Affiliation line.** The report must not suggest endorsement by any employer or organisation. Options include
   "Independent researcher" or a personal affiliation of the author's choosing.
2. **AI-assistance disclosure.** Journals, arXiv and many universities expect AI use to be disclosed, and an AI system cannot be an
   author. Proposed wording, for the author to change: *"Code, analysis and drafting were carried out with the assistance of an AI
   system (Claude, Anthropic). The author directed the work, reviewed every result and takes full responsibility for the content."*
3. **Contacting the QANTIS authors before the report is archived.** The P3 release is already public. Common practice before
   publishing a critique in a paper is to give the authors the findings and a chance to respond. Suggested: a short, factual message
   to the corresponding author, or a GitHub issue, with a reasonable period before P4 is archived. This is a public communication in
   the author's name and needs explicit approval of the text.
4. **Publication route.**
   - (a) A Zenodo record of type "report", uploaded by the author through the Zenodo web interface and linked to the software's
     concept DOI.
   - (b) A later arXiv submission (quant-ph), which needs an endorser.
   - (c) A later journal or conference submission.
   - (a) is the P4 deliverable; (b) and (c) are separate decisions.
5. **Toolchain.** No LaTeX, pandoc or plotting library is installed.
   - Options: LaTeX compiled locally with Tectonic, a single program that would have to be installed; LaTeX compiled on Overleaf by
     the author; or Markdown rendered to PDF.
   - Figures need matplotlib, added as a development-only dependency.
   - Recommended: LaTeX sources in `paper/`, compiled with Tectonic, figures from matplotlib — each installation with the author's
     approval.
6. **Licence of the report text.** The code is Apache-2.0; for the manuscript CC BY 4.0 is usual.

## Milestones

| ID | Milestone |
|----|-----------|
| P4.0 | The author's decisions above, recorded in the log |
| P4.1 | `paper/` skeleton; `tools/p4_numbers.py` and its test; figure scripts |
| P4.2 | Draft of sections 3–5 (the results), then 1, 2, 6, 7 and the abstract |
| P4.3 | Consistency pass: every number from the table, every reference verified, every limit stated; test suite green |
| P4.4 | Author's review; changes made; optional reading by a third person chosen by the author |
| P4.5 | PDF build; release of the repository (v1.0.0 proposed); Zenodo report record by the author; memory and README updated |

## Out of scope

- New experiments or QPU use
- Rewriting any registered plan or past log entry
- Submission to arXiv, a journal or a conference — each a separate later decision
- Any contact with third parties without the author's approval
