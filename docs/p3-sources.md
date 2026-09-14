# P3.0 — source audit of QANTIS (arXiv:2603.00785) and its public repository

**Date:** 2026-09-14 · **Plan:** [`docs/p3-plan.md`](p3-plan.md)

**Sources read**
- The paper: arXiv:2603.00785v1, HTML version, with section, table and equation numbers as they appear there.
- The public repository https://github.com/neuraparse/qantis at commit `c17c2b5` (2026-04-30), cloned outside this repository.
  Paths below are relative to that clone.
- The FPC-QAOA source the paper cites as [3]: Saavedra-Pino et al., arXiv:2512.21181 (abstract).

**How this is written.** Findings are paraphrased with references rather than quoted at length. "Confirmed" means checked
directly, by reading code or by running Qiskit here; "unconfirmed" means inferred and still to be tested in P3.1–P3.2.
Nothing here says whether the authors' private code — the repository calls it the Collaborator Edition — behaves the same way.

## 1. What the headline number measures

| item | paper | public code | status |
|---|---|---|---|
| quality metric | §8.6 and Table 15 describe hardware quality as QUBO values decoded from the top-10 bitstrings, relative to the Hungarian optimum −92.4 | `scripts/hardware/run_fpc_qaoa_ibm.py` L392 keeps the 10 most frequent bitstrings; L401–407 evaluate xᵀQx for each; L428 divides the lowest value by the absolute Hungarian objective | **confirmed** |
| value used | xᵀQx, without the penalty's constant term | same | **confirmed** |
| headline | p = 3, 64.1% ± 3.3% over three runs with twirling and dynamical decoupling (§8.6) | — | as reported |
| which angles | §8.6 states the 64.1% came from the analytical FPC initial schedule; warm-started COBYLA angles gave 49.4% ± 18.0% at p = 3 | — | as reported |

The metric is **not** P(optimal) and **not** an expectation value. It is the best of 10 selected samples. Q1 of the plan
(a random-sampling baseline for this metric) addresses exactly this.

## 2. Problems found in the public hardware script

**2.1 Angles are bound to the wrong parameters on the initial-schedule path — confirmed on Qiskit 2.5.2.**
- `run_fpc_qaoa_ibm.py` L215–221 builds the initial point interleaved as [γ₁, β₁, γ₂, β₂, …].
- L233–236 bind it with `dict(zip(raw_circuit.parameters, initial_point))`.
- `QAOAAnsatz.parameters` is ordered by name: all β first, then all γ. Run here at p = 3, the binding gave β[0] ← γ₁,
  β[1] ← β₁, β[2] ← γ₂, γ[0] ← β₂, γ[1] ← γ₃, γ[2] ← β₃.
- The same interleaved list is passed as `initial_point` to the QAOA solver (`fpc_qaoa_solver.py` L237–242), which also reads it in
  the ansatz's parameter order.
- COBYLA-optimised angles taken from `optimal_parameters` (L283–287, solver L252–255) come back in ansatz order, so that path
  binds correctly.
- *Consequence, if the private code does the same:* the initial-schedule circuit that §8.6 credits with 64.1% did not run the
  intended linear ramp. The circuit that ran was a different, still deterministic, set of angles. This is not proof that the
  headline is wrong, only that it may not come from the schedule described.
- The paper was run with Qiskit 2.3. The parameter ordering by name is long-standing; confirming it in that version is part
  of P3.2.

**2.2 Bitstrings are probably evaluated in reverse variable order — partly confirmed.**
- Qiskit count keys are little-endian: flipping only qubit 0 on 3 qubits gives the key `001`. Confirmed here.
- `_eval_bs` (L401–407) and the decoding (L414) read the key left to right, so index 0 of the evaluated vector is the *last*
  qubit.
- If `qiskit_optimization.translators.to_ising` maps variable i to qubit i (to be confirmed in P3.2, since that package is not
  installed here), every hardware bitstring was evaluated as its mirror image.
- This would change which of the 10 samples scores best, and could change the quality value.

**2.3 The public solver is not FPC-QAOA as described — confirmed.**
- The paper (§6.2) and its source [3] describe a fixed number of trainable schedule coefficients, independent of depth. The
  abstract of arXiv:2512.21181 says the trainable-parameter count stays constant regardless of depth.
- `fpc_qaoa_solver.py` passes the digitised schedule only as `initial_point` (L241) to a standard QAOA. COBYLA then optimises all
  2p angles.
- So the public code is standard QAOA with a schedule-based starting point, not FPC-QAOA.

**2.4 "ISA" is used in two ways — confirmed.**
- §2.4 defines ISA as compiled two-qubit-gate *depth*; §8.6 and Table 15 use the same numbers as gate counts.
- The script's resource print (L241) counts `cx` or `ecr` gates. On Heron devices, whose native two-qubit gate is CZ, that count
  would be 0. The published ISA numbers therefore did not come from this line.

**2.5 Defaults differ from the paper — confirmed.**
- The script defaults to `ibm_brisbane`, 8192 shots, depth 8 and COBYLA maxiter 100 (L40–65).
- The paper reports `ibm_fez`, 4096 shots and p = 3.
- The solver class defaults to 100,000 shots and maxiter 200 (`fpc_qaoa_solver.py` L110, L113).

## 3. The instance and the costs

| item | paper | public code | status |
|---|---|---|---|
| generator | "random-Gaussian", seed 42 (§8.6, Table 14) | `scripts/hardware/__init__.py` L291–314: two standard-normal draws, predicted positions (N × 2) then measurements (M × 2), from `default_rng(42)`; innovation covariance 0.5·I for every track | **confirmed** (code) |
| association cost | c_ij = ½(d² + ln det 2πS) (§6.1) | `formulation/cost_matrix.py` L79–82: the negative log-likelihood *minus* ln(clutter density), with clutter density 1e-5 (L40). That equals ½(d² + ln det 2πS) + ln(1e-5) ≈ ½(d² + ln det 2πS) − 11.51 | **differs** — the code adds a constant −11.51 to every gated cost |
| gating | χ² 9.21 (§6.1) | an ungated pair keeps its variable, with cost 0 (L96; builder L231 skips only the cost term) | **differs in effect** — gating does not remove variables; n = NM + N + M always |
| missed-detection / false-alarm costs | not stated | 5.0 and 3.0 (`formulation/mtda_qubo_builder.py` L186–187; `configs/experiments/mht_default.yaml`) | **not reproducible from the paper alone** |
| penalty | λ = 1.5·max\|c_ij\| (Eq. 5 and Eq. 7) | 1.5 × max\|finite cost\| (`formulation/constraint_encoder.py` L60, L72), taken over the costs *including* the −11.51 shift and the zeros of ungated pairs | **confirmed**, with that caveat |
| variable order | not stated | all x_ij row by row, then the N missed-detection slacks, then the M false-alarm slacks (`formulation/association_variables.py` L51–67) | **confirmed** (code) |
| constraint form | Eq. 5 (§4.2) has no slack variables and "≤ 1" constraints; Eq. 7 (§6.1) has slacks and exact one-hot rows and columns | the code follows Eq. 7 | the paper is **internally inconsistent**; the code matches Eq. 7 |

## 4. What "Hungarian optimal −92.4" is in the code

`solvers/classical_solvers/hungarian_solver.py`:
- **Input matrix.** The diagonal Q entries of the x_ij variables (L73) — the costs *after* the penalty's linear terms have been
  added, so c_ij − 2λ. It is padded to a square with 1e6 (L77) and solved with `linear_sum_assignment` (L81).
- **Forced pairing.** This always pairs min(N, M) tracks with measurements. It never declares a missed detection when a pair
  exists, even when that would lower the QUBO value.
- **Objective.** The sum of the diagonal Q entries over the chosen pairs plus the implied slack variables (L103). For a feasible
  string that equals xᵀQx without the constant.

So "Hungarian optimal" is the QUBO value of a **maximum-cardinality** assignment. It is not necessarily the QUBO minimum. P3.1
therefore reports both this value and the brute-force minimum over all 2^11 strings. The paper's own artifact notes (§9) say a
"Hungarian slack costs" error was corrected during the campaign.

## 5. Provenance of the formulation

- **In the paper.** §3.2 and §4.2 say that "Stollenwerk et al. [18]" first cast data association as a QUBO and that λ = 1.5·max|c|
  follows them. Reference [18] is Stollenwerk et al., *Quantum annealing applied to de-conflicting optimal trajectories for air
  traffic management* — not a data-association paper.
- **In the repository.** The formulation code attributes the work to "Stollenwerk et al., *Adiabatic Quantum Computing for Multi
  Object Tracking*, Fraunhofer FKIE, arXiv:2110.08346", with the 1.5 rule in Section IV. That merges three different works:
  - arXiv:2110.08346 is McCormick, Osborn, Angle, Streit (Metron); their penalty weights are set by hand.
  - *Adiabatic Quantum Computing for Multi Object Tracking* is Zaech et al., CVPR 2022 (arXiv:2202.08837).
  - Fraunhofer FKIE's data-association QUBO is Govaers, Stooß, Ulmke, IEEE MFI 2021.
- **The 1.5 rule** was found in none of these sources during this audit. It is treated as the QANTIS authors' own choice.

## 6. Availability of materials

- **Ancillary bundle.** §9 cites an ancillary bundle (`anc/artifact-bundle.tar.gz`) holding the details of four corrected code
  errors. On 2026-09-14 both `https://arxiv.org/src/2603.00785v1/anc/artifact-bundle.tar.gz` and
  `https://arxiv.org/src/2603.00785/anc` returned HTTP 404; the abstract page returned 200.
- **Licence.** The repository README describes a Community Edition licensed MIT. It states that real hardware results are not
  published there, and that raw hardware data are available to reviewers on request. The paper states Apache 2.0.

## 7. Effect on the registered claims

| claim | effect of the audit |
|---|---|
| C1 instance | Testable. The generator and the missing costs are available in code; −92.4 is expected to be the maximum-cardinality value (§4), so both it and the brute-force QUBO minimum will be reported. The cost-formula difference (§3) means the instance follows the *code*, not the paper's equation, and that is stated. |
| C2 noiseless method | Testable, but "the method" has three candidates: the paper's FPC-QAOA (k trainable coefficients), the public code (2p angles from a schedule start), and the initial-schedule circuit as the script actually binds it (§2.1). All three are simulated; C2 is graded on the paper's description, and the other two are reported alongside. |
| C3 hardware | Unchanged rules. Whatever runs on hardware is the correctly bound circuit; the misbound variant is simulated only. |
| C4 greedy | Testable. Which greedy variant (with or without slack) is not specified; both are computed. |
| Q1 metric baseline | Unchanged; its importance is confirmed (§1). The metric is also computed with the bit order both ways (§2.2). |

None of the claims or thresholds in `docs/p3-plan.md` were changed.
