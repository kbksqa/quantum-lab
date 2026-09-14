# P2 benchmark — multi-sensor data association as multi-dimensional assignment

A reproducible benchmark for solvers of the three-dimensional assignment problem that arises when several sensors observe
the same targets at one instant. The problem is NP-hard. Each instance comes with its exact optimum, so any method —
classical heuristic, annealer, or quantum algorithm — can be scored the same way.

> All data is **synthetic**, generated from recorded seeds by `src/p2_scene.py`. Nothing here comes from a real sensor or system.

## Files

| file | content |
|------|---------|
| `instances.jsonl.gz` | one JSON object per line, one instance per object |
| `baselines.csv` | every baseline method on every instance, scored by the checker |
| `summary.md` | the baseline table, grouped by each sweep factor |
| `manifest.json` | sweep, seeds, counts, the hard subsets and the infeasible instances |

## The sweep

5 target counts × 4 clutter levels × 3 detection probabilities × 3 spacings × 3 bearing errors = **540 settings**, with
3 replicates each.

| factor | values |
|--------|--------|
| targets | 2, 3, 4, 5, 6 |
| expected false alarms per sensor | 0, 0.5, 1, 2 |
| detection probability P_D | 0.8, 0.9, 1.0 |
| target spacing | 25, 50, 100 m |
| bearing error σ_θ | 0.005, 0.01, 0.02 rad (added by plan amendment 1) |

Fixed: 3 sensors on a 2 km circle, range error 10 m, pairwise chi-square gate 9.21, 200 m clutter margin.

## Instance format

```jsonc
{
  "id": "p2-123-0",                       // setting index, replicate
  "format": "quantum-lab P2 multi-sensor assignment instance v1",
  "generator": {"code": "src/p2_scene.py", "seed": [2031, 123, 0], "targets": 4, "params": { ... }},
  "sensors": [[x, y], ...],               // S = 3 sensor positions, metres
  "clutter_density": 4.1e-06,             // false alarms per m² per sensor
  "measurements": [[[x, y], ...], ...],   // per sensor
  "covariances": [[[[a, b], [b, c]], ...], ...],
  "truth": {"targets": [[x, y], ...], "origin": [[target index or -1, ...], ...], "partition": [[i1, i2, i3], ...]},
  "tuples": [[i1, i2, i3], ...],          // every allowed hypothesis
  "costs": [c, ...],                      // one per tuple
  "false_alarm": [false, ...],            // single-measurement tuple cheaper as a false alarm
  "tuple_counts": { ... },                // what the generator enumerated and dropped, by reason
  "optimum": {"cost": c, "partition": [[i1, i2, i3], ...]},   // null when the instance has no valid answer
  "lp_bound": c,                          // LP relaxation, equal to the best Lagrangian bound
  "has_gap": false                        // optimum - lp_bound > 1e-6 * max(1, |optimum|)
}
```

A tuple `[i1, i2, i3]` says that measurement `i1` of sensor 1, `i2` of sensor 2 and `i3` of sensor 3 come from one target.
Indices are **1-based per sensor**; `0` means that sensor did not see it. A valid answer is a **partition**: a set of allowed
tuples that uses every measurement of every sensor exactly once. Its cost is the sum of its tuples' costs. The goal is the
minimum-cost partition.

The problem needs nothing but `tuples`, `costs` and the measurement counts. Positions, covariances and the truth are there for
anyone who wants to build their own cost or check accuracy.

## Scoring an answer

```bash
python src/p2_benchmark.py check benchmark/p2/instances.jsonl.gz answers.json --details scores.json
```

`answers.json` maps instance ids to partitions: `{"p2-123-0": [[1, 2, 0], [0, 1, 1], ...], ...}`. For each answer the checker
reports:
- `valid` — a partition made of allowed tuples
- `cost` and `gap_to_optimum`
- `optimal` — within 1e-6 relative of the optimum
- `equals_truth` and `truth_tuples_recovered`

The checker in `src/p2_benchmark.py` (`check`, `load_instances`) uses only the Python standard library, so it can be copied
on its own.

## Reading the results — limits to keep in mind

- **The optimum is not the truth.** The exact optimum of this cost equals the true association in only a minority of
  realistic scenes. Large cross-range errors, clutter inside gates and close targets make the data ambiguous. See the P2.1
  entry of `docs/research-log.md`. Solvers should be compared on cost; accuracy against the truth measures the model as much
  as the solver.
- **Gating can cut the truth.** In some instances a true tuple is not allowed, so no answer can equal the truth.
- **Infeasible instances.** With P_D = 1 and no clutter, single-measurement tuples are impossible. When the gate cuts a true
  tuple, some measurement has no allowed tuple, and the instance has no valid answer (`optimum` is null). These instances are
  listed in `manifest.json` and kept for completeness.
- **Cost convention without clutter.** With no clutter the ln λ term is dropped and every cost is positive. The optimum is
  unaffected, but cheapest-first methods are not; `greedy_normalised` shows the fix.
- **"Hard" subsets.** `hard_subset_lp_gap` lists instances whose LP relaxation is below the optimum.
  `hard_subset_lagrangian_not_optimal` lists instances where the Lagrangian relaxation baseline missed the optimum — the
  subset where there is still room to improve.

## Baselines

| method | description |
|--------|-------------|
| `greedy` | cheapest tuple first, skip tuples that reuse a measurement |
| `greedy_normalised` | the same, after subtracting each measurement's fixed cost share (`p2_heuristics.measurement_reference`) |
| `lagrangian` | relax sensor 3, subgradient on the multipliers, feasible answer recovered by a second 2D assignment (at most 200 iterations) |
| `annealing` | simulated annealing on the QUBO of P2.2 with A = max(max\|c\|, 1), 64 restarts × 100 sweeps; the best valid restart is kept |

Baseline limits, all counted in `baselines.csv`:
- `greedy` and `greedy_normalised` return no valid answer on 21 instances, all with no clutter and P_D = 1.
- `lagrangian` returns no valid answer on 16 instances, all with P_D = 1 and clutter present, because its recovery step cannot
  complete some pairs.
- `greedy_normalised` beats `greedy` only without clutter.

Rebuild everything with `python src/p2_benchmark.py build` (instances, baselines, summary and manifest). Two builds produce
identical instances and identical baseline results; only the timings differ.

## License and citation

Apache License 2.0, like the rest of the repository. Cite the repository release that contains the benchmark (see `CITATION.cff`).
