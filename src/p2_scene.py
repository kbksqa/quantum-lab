# P2.0 - Multi-sensor snapshot scene, tuple hypotheses and their costs (multi-dimensional assignment).
#
# Textbook set-up, nothing operational:
#   - T targets in a 2D region, seen at one instant by S sensors (default 3) placed on a circle around the scene
#   - each sensor reports a position; its error comes from range and bearing errors, so the error ellipse is short
#     along the line of sight and long across it - each sensor sees a differently oriented ellipse
#   - detection probability P_D per target per sensor; Poisson clutter, uniform in a window around the targets
#   - a hypothesis is a tuple (i_1, ..., i_S): measurement i_s of sensor s (1-based), or 0 when sensor s did not see it
#   - cost of a target tuple = generalised likelihood ratio, target position replaced by its weighted least-squares
#     estimate x_hat from the tuple's measurements:
#         sum over detecting sensors  [ -ln P_D + ln lambda + 1/2 r_s' R_s^-1 r_s + 1/2 ln|2 pi R_s| ],  r_s = z_s - x_hat
#       + sum over missing sensors    [ -ln(1 - P_D) ]
#   - a measurement declared a false alarm costs 0 (the reference); a single-measurement tuple takes the cheaper of
#     "target seen by one sensor" and "false alarm", and records which
#   - pairwise chi-square gating between the measurements of a tuple
#   - without clutter (lambda = 0) the ln lambda term is dropped and false alarms are impossible; every valid partition
#     then changes by the same scene-dependent constant, so the optimum does not move
#
# A valid association is a partition: every real measurement belongs to exactly one tuple.
# "Pure" mode (P_D = 1, no clutter, no gating) leaves only full tuples: T^S of them, the smallest QAOA instances.
#
# Usage:
#     python src/p2_scene.py                     # one example scene + tuple statistics for T = 2..6
#     python src/p2_scene.py --scenes 500 --seed 7

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import itertools
import json
import math
import pathlib

import numpy as np

RESULTS = pathlib.Path(__file__).resolve().parents[1] / "results"
PURE = {"p_detect": 1.0, "clutter_per_sensor": 0.0, "gate": None}


@dataclasses.dataclass
class Params:
    n_sensors: int = 3
    sensor_radius: float = 2000.0       # m, sensors on a circle around the scene centre
    sigma_range: float = 10.0           # m
    sigma_bearing: float = 0.02         # rad (40 m across the line of sight at 2 km)
    p_detect: float = 0.9
    clutter_per_sensor: float = 1.0     # expected false alarms per sensor in the window
    window_pad: float = 200.0           # m, clutter window margin around the targets
    gate: float | None = 9.21           # chi-square, 2 degrees of freedom, 99%, for every pair in a tuple
    spacing: float = 50.0               # m, nominal separation between targets


@dataclasses.dataclass
class Scene:
    sensors: np.ndarray         # S x 2
    targets: np.ndarray         # T x 2 true positions
    measurements: list          # per sensor: M_s x 2
    covariances: list           # per sensor: M_s x 2 x 2, evaluated at the reported position
    origin: list                # per sensor: list of target index, or -1 for clutter
    clutter_density: float      # false alarms per m^2 per sensor (0 without clutter)


@dataclasses.dataclass
class TupleSet:
    tuples: list                # K tuples of S ints
    costs: np.ndarray           # K
    false_alarm: list           # K bools, True for a single measurement that is cheaper as a false alarm
    counts: dict                # every tuple that was enumerated and dropped, by reason


def sensor_positions(n_sensors: int, radius: float) -> np.ndarray:
    angles = math.pi / 2 + 2 * math.pi * np.arange(n_sensors) / n_sensors
    return radius * np.column_stack([np.cos(angles), np.sin(angles)])


def measurement_covariance(position: np.ndarray, sensor: np.ndarray, sigma_range: float, sigma_bearing: float) -> np.ndarray:
    offset = position - sensor
    r = float(np.hypot(offset[0], offset[1]))
    u = offset / r
    v = np.array([-u[1], u[0]])
    return sigma_range ** 2 * np.outer(u, u) + (r * sigma_bearing) ** 2 * np.outer(v, v)


def generate(n_targets: int, params: Params, rng: np.random.Generator) -> Scene:
    sensors = sensor_positions(params.n_sensors, params.sensor_radius)
    targets = np.column_stack([(np.arange(n_targets) - (n_targets - 1) / 2) * params.spacing,
                               rng.normal(0, params.spacing / 2, n_targets)])
    low = targets.min(axis=0) - params.window_pad
    high = targets.max(axis=0) + params.window_pad
    clutter_density = params.clutter_per_sensor / float(np.prod(high - low)) if params.clutter_per_sensor > 0 else 0.0

    measurements, covariances, origin = [], [], []
    for sensor in sensors:
        z, o = [], []
        for i, x in enumerate(targets):
            if rng.random() < params.p_detect:
                R = measurement_covariance(x, sensor, params.sigma_range, params.sigma_bearing)
                z.append(rng.multivariate_normal(x, R))
                o.append(i)
        if params.clutter_per_sensor > 0:
            for _ in range(rng.poisson(params.clutter_per_sensor)):
                z.append(rng.uniform(low, high))
                o.append(-1)
        order = rng.permutation(len(z))
        z = np.array([z[k] for k in order]).reshape(-1, 2)
        measurements.append(z)
        origin.append([o[k] for k in order])
        covariances.append(np.array([measurement_covariance(p, sensor, params.sigma_range, params.sigma_bearing)
                                     for p in z]).reshape(-1, 2, 2))
    return Scene(sensors, targets, measurements, covariances, origin, clutter_density)


def fuse(zs: list, Rs: list) -> tuple[np.ndarray, np.ndarray]:
    """Weighted least-squares position from several measurements: (x_hat, its covariance)."""
    infos = [np.linalg.inv(R) for R in Rs]
    P = np.linalg.inv(sum(infos))
    return P @ sum(I @ z for I, z in zip(infos, zs)), P


def target_cost(zs: list, Rs: list, n_missing: int, p_detect: float, clutter_density: float) -> float:
    if n_missing and p_detect >= 1:
        return math.inf
    x_hat, _ = fuse(zs, Rs)
    log_lambda = math.log(clutter_density) if clutter_density > 0 else 0.0
    cost = -n_missing * math.log(1 - p_detect) if n_missing else 0.0
    for z, R in zip(zs, Rs):
        r = z - x_hat
        _, logdet = np.linalg.slogdet(2 * math.pi * R)
        cost += -math.log(p_detect) + log_lambda + 0.5 * float(r @ np.linalg.solve(R, r)) + 0.5 * logdet
    return cost


def pair_d2(z_a: np.ndarray, R_a: np.ndarray, z_b: np.ndarray, R_b: np.ndarray) -> float:
    d = z_a - z_b
    return float(d @ np.linalg.solve(R_a + R_b, d))


def build_tuples(scene: Scene, params: Params) -> TupleSet:
    S = len(scene.sensors)
    sizes = [len(m) for m in scene.measurements]
    gate_ok = {}
    if params.gate is not None:
        for a, b in itertools.combinations(range(S), 2):
            for i in range(sizes[a]):
                for j in range(sizes[b]):
                    gate_ok[a, i, b, j] = pair_d2(scene.measurements[a][i], scene.covariances[a][i],
                                                  scene.measurements[b][j], scene.covariances[b][j]) <= params.gate

    counts = {"enumerated": 0, "removed_by_gate": 0, "removed_infinite_cost": 0,
              "singleton_as_target": 0, "singleton_as_false_alarm": 0}
    tuples, costs, false_alarm = [], [], []
    for tup in itertools.product(*[range(m + 1) for m in sizes]):
        detected = [s for s in range(S) if tup[s] > 0]
        if not detected:
            continue
        counts["enumerated"] += 1
        if params.gate is not None and not all(gate_ok[a, tup[a] - 1, b, tup[b] - 1]
                                               for a, b in itertools.combinations(detected, 2)):
            counts["removed_by_gate"] += 1
            continue
        zs = [scene.measurements[s][tup[s] - 1] for s in detected]
        Rs = [scene.covariances[s][tup[s] - 1] for s in detected]
        cost = target_cost(zs, Rs, S - len(detected), params.p_detect, scene.clutter_density)
        is_false_alarm = False
        if len(detected) == 1 and scene.clutter_density > 0 and cost > 0.0:
            cost, is_false_alarm = 0.0, True
        if math.isinf(cost):
            counts["removed_infinite_cost"] += 1
            continue
        if len(detected) == 1:
            counts["singleton_as_false_alarm" if is_false_alarm else "singleton_as_target"] += 1
        tuples.append(tup)
        costs.append(cost)
        false_alarm.append(is_false_alarm)
    return TupleSet(tuples, np.array(costs), false_alarm, counts)


def truth_partition(scene: Scene) -> list:
    S, T = len(scene.sensors), len(scene.targets)
    groups = [[0] * S for _ in range(T)]
    partition = []
    for s in range(S):
        for j, source in enumerate(scene.origin[s]):
            if source >= 0:
                groups[source][s] = j + 1
            else:
                single = [0] * S
                single[s] = j + 1
                partition.append(tuple(single))
    partition += [tuple(g) for g in groups if any(g)]
    return sorted(partition)


def is_partition(scene: Scene, partition: list) -> bool:
    used = [[0] * len(m) for m in scene.measurements]
    for tup in partition:
        if not any(tup):
            return False
        for s, index in enumerate(tup):
            if index > 0:
                used[s][index - 1] += 1
    return all(n == 1 for row in used for n in row)


def partition_cost(tuple_set: TupleSet, partition: list) -> float:
    lookup = dict(zip(tuple_set.tuples, tuple_set.costs))
    return float(sum(lookup.get(tup, math.inf) for tup in partition))


def scene_statistics(scene: Scene, params: Params) -> dict:
    tuple_set = build_tuples(scene, params)
    truth = truth_partition(scene)
    present = set(tuple_set.tuples)
    detected_by = [0] * len(scene.targets)
    for s in range(len(scene.sensors)):
        for source in scene.origin[s]:
            if source >= 0:
                detected_by[source] += 1
    return {
        "measurements_per_sensor": [len(m) for m in scene.measurements],
        "tuples": len(tuple_set.tuples),
        "truth_tuples_cut": sum(tup not in present for tup in truth),
        "targets_unseen": sum(n == 0 for n in detected_by),
        "counts": tuple_set.counts,
    }


def summarise(rows: list) -> dict:
    tuples = [r["tuples"] for r in rows]
    counts = {key: int(sum(r["counts"][key] for r in rows)) for key in rows[0]["counts"]}
    return {
        "scenes": len(rows),
        "mean_measurements_per_sensor": float(np.mean([np.mean(r["measurements_per_sensor"]) for r in rows])),
        "tuples_mean": float(np.mean(tuples)),
        "tuples_median": float(np.median(tuples)),
        "tuples_max": int(max(tuples)),
        "share_truth_survives_gating": float(np.mean([r["truth_tuples_cut"] == 0 for r in rows])),
        "truth_tuples_cut_total": int(sum(r["truth_tuples_cut"] for r in rows)),
        "targets_unseen_total": int(sum(r["targets_unseen"] for r in rows)),
        "counts_total": counts,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenes", type=int, default=200)
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()

    params = Params()
    pure = dataclasses.replace(params, **PURE)
    rng = np.random.default_rng(args.seed)

    example = generate(3, params, rng)
    example_set = build_tuples(example, params)
    truth = truth_partition(example)
    print("example scene: 3 targets, measurements per sensor %s" % [len(m) for m in example.measurements])
    print("  origins per sensor : %s" % example.origin)
    print("  tuples kept        : %d  (%s)" % (len(example_set.tuples), example_set.counts))
    print("  truth partition    : %s  cost %.4f" % (truth, partition_cost(example_set, truth)))

    record = {
        "timestamp": dt.datetime.now().astimezone().isoformat(),
        "experiment": "P2.0 multi-sensor scene and tuple costs",
        "seed": args.seed,
        "params": dataclasses.asdict(params),
        "augmented": {},
        "pure": {},
    }
    print("augmented scenes (%d per size):" % args.scenes)
    print("  T  meas/sensor  tuples mean  median   max  truth survives gate  cut  unseen  singleton target/FA")
    for T in range(2, 7):
        s = summarise([scene_statistics(generate(T, params, rng), params) for _ in range(args.scenes)])
        record["augmented"][str(T)] = s
        c = s["counts_total"]
        print("  %d  %11.2f  %11.1f  %6.0f  %4d  %19.3f  %3d  %6d  %d/%d"
              % (T, s["mean_measurements_per_sensor"], s["tuples_mean"], s["tuples_median"], s["tuples_max"],
                 s["share_truth_survives_gating"], s["truth_tuples_cut_total"], s["targets_unseen_total"],
                 c["singleton_as_target"], c["singleton_as_false_alarm"]))
    print("pure scenes (P_D = 1, no clutter, no gate):")
    for T in (2, 3, 4):
        s = summarise([scene_statistics(generate(T, pure, rng), pure) for _ in range(20)])
        record["pure"][str(T)] = s
        print("  T=%d  tuples %d  (= T^S = %d)" % (T, s["tuples_max"], T ** params.n_sensors))

    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / ("p2_0-scene-%s.json" % dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
    out.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print("saved " + str(out))


if __name__ == "__main__":
    main()
