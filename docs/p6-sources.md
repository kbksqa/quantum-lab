# P6.0 — source audit of the QANTIS POMDP-planning results (arXiv:2603.00785)

**Date:** 2026-09-15 · **Plan:** [`docs/p6-plan.md`](p6-plan.md) · **Companion:** [`docs/p3-sources.md`](p3-sources.md) (the MTDA half)

## Sources read

- **The paper:** arXiv:2603.00785v1, HTML version. Section, table and equation numbers are as they appear there. It was read
  from a text conversion. Four passages were checked against the live HTML page:
  - the PASS definition in §2.4
  - the k* formula in §5.2
  - the ISA definition in §8.6
  - the abstract page's version and ancillary listing
- **The public repository** https://github.com/neuraparse/qantis, cloned outside this repository. Paths below are relative to that
  clone.
  - **`c17c2b5`** (HEAD, 2026-04-30).
  - **`7c6509c`** (2026-02-28, "last stable version"), the commit dated with the paper. Findings marked "(both)" hold at both
    commits.
  - Between the two, the POMDP hardware scripts grew by several hundred lines: `run_end_to_end_pomdp_ibm.py` +620/−,
    `run_grover_belief_ibm.py` +160, `run_tiger_4state_ibm.py` +215. P6 compares against `7c6509c` wherever the difference
    matters.
- **References:** checked on Crossref, arXiv and publisher listings.

**How this is written.** Findings are paraphrased with references rather than quoted at length. The labels mean:
- **Confirmed:** checked directly in the text or code.
- **Unconfirmed:** inferred, and still to be tested in P6.1–P6.3.

Nothing here says whether the authors' private code — the README reserves hardware results for partners — behaves the same
way.

## 1. What the paper claims for POMDP planning

| item | where | content |
|---|---|---|
| Tiger instance | §8.2.1 | 2 states, 3 actions, 2 observations, γ = 0.95. The rewards are not stated in the paper. |
| Rewards used by the code | `packages/quantum-pomdp/src/quantum_pomdp/scenarios/tiger_problem.py` L37–40, L80–86 | listen −1; open the tiger's door −100; open the other door +10; listening correct with probability 0.85 |
| Belief circuit | §5.1, Eq. 6 | five registers; the full circuit has 11 qubits (§5.3), but Appendix Table 19 lists the register allocation per problem |
| Grover step | §5.2, §8.6 | k* = ⌊π/(4 arcsin√P(e)) − ½⌋. Hardware: one iterate, prior [0.97, 0.03], target observation 1. P(obs = 1) went 0.179 → 0.907 (theory 0.171 → 0.917), with posterior [0.849, 0.151] against exact [0.851, 0.149]. |
| Tiger minimal circuit | §5.3(b), §8.6 | 2 qubits, "ISA 12", Hellinger distance 0.025 / 0.014 |
| 4-state circuit | §8.6 | 3 qubits, logical depth 15, "ISA 162", Hellinger distance 0.128 (obs 0) and 0.044 (obs 1) |
| Closed loops | §8.6, Tables 16–17 | T = 4 with observations [0,0,0,0]: actions listen, listen, open-right, listen. T = 8 with observations [0,0,0,1,1,1,0,0]: open-right at t = 2 and open-left at t = 5. |
| Simulated planning | Table 6 | 100 episodes of 50 steps, horizon 5, seed 42. Rewards: POMCP 18.3 ± 12.7, DESPOT 19.1 ± 11.4, PBVI 17.6 ± 13.2, QBRL 18.7 ± 12.1. |
| Baseline settings | §8.1 | POMCP 1,000 simulations, UCB c = 25; DESPOT 500 scenarios, 100 particles; PBVI 200 belief points |
| PASS | §2.4, footnote in §8, §8.6 | Hellinger distance < 0.15, stated to correspond to "≤1.1% total-variation distance" |

## 2. The gaps listed in the plan — confirmed or withdrawn

**G1 — no data. Confirmed.**
- The repository tracks no result files (no JSON, CSV or NumPy data) at HEAD.
- `README.md` L26 and L114 state that hardware results are not published there.
- The arXiv abstract page lists only v1 (28 Feb 2026) and no ancillary files. §10 says an artifact bundle is included as an
  arXiv ancillary file.
- The paper gives one job ID (Table 15, Grover-AA).

**G2 — the pass threshold differs between paper and code. Confirmed (both).**
- *Paper:* 0.15.
- *Scripts:* 0.05 at `scripts/hardware/run_end_to_end_pomdp_ibm.py` L641 (7c6509c L424),
  `run_tiger_4state_ibm.py` L573/L586/L593 (7c6509c L371/L384/L391), and `run_tiger_ibm.py` L352 for the simulator
  (7c6509c L351).
- 0.15 appears only for the final hardware check in `run_tiger_ibm.py` L463 (7c6509c L464).
- The 4-state obs-0 value of 0.128 therefore passes in the paper and fails in the scripts that produced it.

**G3 — "ISA depth". Confirmed (both).**
- *Paper wording:* §8.6 defines it as "the post-transpilation two-qubit gate count", while §2.4 calls it the "compiled
  two-qubit-gate depth".
- *Scripts record the total circuit depth* (`.depth()`): `run_grover_belief_ibm.py` L502–506 (7c6509c L358–362),
  `run_tiger_4state_ibm.py` L439 (7c6509c L294), `run_tiger_ibm.py` 7c6509c L381–382.
- *Loop depths are constants:* the end-to-end loop hard-codes "known from previous runs" values of 11, 12 and 18
  (L293–297; 7c6509c L220–221). Hardware runs overwrite them with the measured total depth (L563–567).
- *Whether the reported numbers match total depth or two-qubit gate count* is what C3 tests in P6.2.

**G4 — Hellinger 0.15 against "≤1.1% total variation". Confirmed as stated.** The claim appears in §2.4, the §8 footnote and
§8.6, where it is also said to be sufficient because the policy is invariant below about 5% total variation. It is graded
mathematically as C7 in P6.1.

**G5 — Table 6 cannot come from the public entry point. Confirmed (both).**
- *The simulation loop:* `scripts/run_experiment.py` L100–107 (identical at 7c6509c) selects an action and adds
  `expected_reward` at a belief that never changes. It never samples a hidden state or an observation, never updates the
  belief, and calls none of the baselines.
- *The baselines differ from §8.1:*
  - `classical_baselines/pomcp.py` describes itself as a "simplified wrapper" using random rollouts instead of UCB1 (L31–32,
    L48), with `exploration_constant` 1.0 (L52) against c = 25 in the paper.
  - `pbvi.py` defaults to 100 belief points (L54) against 200.
  - `despot.py` draws 500 random scenarios (L51, L74–76); no particle parameter appears.
- *The QBRL "quantum" path:* `algorithms/qbrl.py` builds a circuit at L212 and then uses `classical_update` at L214. The
  circuit is never used. This agrees with the Table 7 footnote ("calls classical_update() internally"). It does not agree with
  §8.2.1's "confirming exact Bayesian conditioning via amplitude amplification", nor does it explain QBRL's belief KL of 0.014
  in Table 6.

**G6 — Table 21 and the iteration formula. Confirmed as an inconsistency in the text.**
- *Three different formulas* for the optimal number of iterations:
  - §5.2: ⌊π/(4 arcsin√P(e)) − ½⌋
  - the Table 21 caption: ⌊(π/4)√(1/P(e))⌋ = 3
  - the Table 21 text: ⌊π/(4 arcsin√P(e))⌋ = 3
- *Still to compute:* whether the table's amplified probabilities (0.192, 0.485, 0.912, 0.721, 0.298 for G = 1–5) follow
  sin²((2G+1)θ) is graded as C6 in P6.1.

**G7 — "5.1× usable samples" counts circuit runs. Confirmed for the public circuit (both).**
- *Structure:* `run_grover_belief_ibm.py` L150–208 builds A, S_f, A†, S₀, A. The belief oracle A is applied twice and its
  inverse once, three applications per shot against one for the baseline circuit.
- *Paper wording:* §8.6 compares "~1 run" with "~6" classical repetitions.
- *Still to compute:* the per-oracle-call accounting is Q1 in P6.1.

**G8 — mitigation settings. Confirmed.**
- *Twirling randomisations:* none of the four POMDP scripts sets `num_randomizations`; only
  `run_advanced_mitigation.py`, `run_fpc_qaoa_ibm.py` and the later `run_vns_tiger.py` do. The paper states N_twirl = 32.
- *ZNE in `run_tiger_ibm.py`:*
  - It uses scale factors [1, 1.5, 2, 3] (L437; 7c6509c L438). The paper reports {1, 3, 5} for Tiger ZNE; its Bell ZNE uses
    {1, 1.5, 2, 3}.
  - The next line passes the name `ibm`, which is not defined anywhere in the file (L438; 7c6509c L439), so the `--zne` path
    raises a NameError as published.
  - *Unconfirmed:* how the paper's full-circuit ZNE value (0.277) was obtained.
- *BIQAE:* `run_biqae_ibm.py` transpiles at optimisation level 2 (L278), against level 3 in §8.6.
- *Environment:* the package pins `qiskit>=2.0,<3` (`packages/quantum-common/pyproject.toml` L24). §8.6 states Qiskit 1.3 and
  qiskit-ibm-runtime 0.34.

**G9 — citations.**

| ref | as printed | found | status |
|---|---|---|---|
| [1] | Brassard, Høyer, Mosca, Tapp, Contemp. Math. 305, 53–74, 2002 | same, doi:10.1090/conm/305/05215 | correct |
| [4] | Cunha, Ramôa, Sequeira, de Oliveira, Barbosa, *Hybrid quantum-classical algorithm for near-optimal planning in POMDPs*, 2025 | arXiv:2507.18606: the v1 title (24 Jul 2025) matches; v2 (29 Jun 2026) is retitled *Quantum Bayesian Networks Can Speed up Reinforcement Learning in Partially Observable Environments* | correct for v1; no arXiv number given — **withdrawn as an error** |
| [5] | Li, Vidwans, Wang, Soley, Quantum 10:1962, 2026 | same, doi:10.22331/q-2026-01-14-1962 | correct |
| [10] | Scott Aaronson, *Quantum POMDPs*, 2014, "unpublished manuscript / blog post" | J. Barry, D. T. Barry, S. Aaronson, *Quantum partially observable Markov decision processes*, Phys. Rev. A 90, 032311 (2014) | **authors and publication status wrong**, if this is the work meant |
| [12] | Silver, Veness, NeurIPS 23, 2164–2172, 2010 | same pages, published as NIPS 2010 | correct except the venue's name at the time |
| [13] | Ye, Somani, Hsu, Lee, JAIR 58:231–266, 2017 | same, doi:10.1613/jair.5328 | correct |
| [17] | "João Ramoa" and Luís Paulo Santos, *Bayesian quantum amplitude estimation*, Quantum 9:1856, 2025 | first author **Alexandra Ramôa**, doi:10.22331/q-2025-09-11-1856 | **first author's name wrong** |
| [30] | Pineau, Gordon, Thrun, IJCAI 2003, 1025–1030 | a search listing gives 1025–1032; the proceedings index could not be opened | pages unresolved |

## 3. Further findings from this audit

**3.1 The minimal and 4-state circuits do not depend on the observation. Confirmed for the public code (both).**
- `_build_minimal_tiger_circuit` (`run_tiger_ibm.py` L104–193) and `_build_tiger_4state_circuit` (`run_tiger_4state_ibm.py`
  L123–225) take a target observation but never use it in the gates. It only selects which shots are kept.
- §8.6 explains the obs-0 / obs-1 difference in the 4-state result (0.128 against 0.044) by different gate paths. For the
  public circuit, both results come from the same gates.
- *Unconfirmed:* whether the two rows came from one run or two runs of that circuit.

**3.2 "Open door" steps are trivial circuits. Confirmed.**
- For the open actions the minimal circuit is H on both qubits (L169–175), so the post-selected posterior is uniform by
  construction.
- The Hellinger distance of 0.0003 at t = 2 in Table 16 measures noise on that trivial circuit, not a belief update.

**3.3 The closed loop.** Confirmed at HEAD; the planner line also at 7c6509c.
- *Planner:* classical with horizon 1 (`QBRLConfig(horizon=1, use_quantum=False)`, L288; 7c6509c L215). The action is
  selected from the current belief (L333), not from the BIQAE estimate.
- *BIQAE:* estimates an amplitude equal to the current belief (L325), with its prior centred on that same value (L360). This
  differs from §5.3, where BIQAE estimates P(o | b, a) and sets the number of Grover iterations.
- *References and belief propagation:*
  - The next step's prior is the hardware posterior (L595).
  - Each step's reference is the exact Bayes update of that hardware-propagated prior (L495).
  - Per-step Hellinger distances therefore do not accumulate error along the trajectory.
- *Silent fallback:* if no shots survive post-selection, the hardware belief silently becomes uniform (L584).

**3.4 The paper contradicts itself on credible intervals. Confirmed.** §5.2 says "all 95% credible intervals" covered the truth
across seven amplitudes and all backends. The T = 8 summary in §8.6 reports that two of eight intervals missed, and Table 17
is a single run.

**3.5 Already recorded in P3, not repeated here:** the licence (Apache 2.0 in the paper, MIT in the repository), and the
repository describing itself as a Community Edition.

## Consequences for P6.1–P6.3

- **C1, C2, C6, C7 and Q1** can be computed from the paper alone. The Tiger rewards needed by C4 and Q2 come from the code
  (L37–40), as the plan allows.
- **C3:**
  - *Circuit data:* the reported "ISA" numbers are compared with both the two-qubit gate count and the total depth, over
    transpiler seeds.
  - *The 11-qubit framework circuit:* built only if the public code can do so without modification, otherwise graded not
    reproducible.
- **C4** is run with the loop's own conventions — planner horizon 1 and the prior propagated from the previous posterior —
  using exact posteriors, so only the action sequence is tested.
- **C5** is expected to be graded not reproducible. The public entry point cannot produce Table 6, and the paper does not state
  the episode protocol (discounting, resets after a door opens).
