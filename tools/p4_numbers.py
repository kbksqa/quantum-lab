# P4.1 - Every number the technical report uses, read from committed result files and written to paper/numbers.tex.
#
# The manuscript takes its numbers only from the macros defined here. tests/test_p4_numbers.py rebuilds the table and fails if
# paper/numbers.tex differs, or if a source file is not tracked by git. A few constants exist only in the research log (the IBM
# dashboard readings); they are listed separately in LOG_CONSTANTS, marked as not machine-checkable.
#
# Usage:
#     python tools/p4_numbers.py            # writes paper/numbers.tex and paper/numbers.json

from __future__ import annotations

import csv
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
R = "results/"
P0H = R + "p0-hardware-analysis-20260914-115305.json"
P05 = R + "p0_5-readout-20260914-121144.json"
P10 = R + "p1_0-baseline-augmented-T3-20260914-122157.json"
P11 = R + "p1_1-gate-20260914-124400.json"
P12 = R + "p1_2-penalty-20260914-125028.json"
P13 = R + "p1_3-annealing-20260914-125703.json"
P14 = R + "p1_4-qaoa-20260914-131628.json"
P15 = R + "p1_5-hardware-20260914-133130.json"
P21 = R + "p2_1-ilp-20260914-144533.json"
P22 = R + "p2_2-qubo-gate-20260914-145351.json"
P23 = R + "p2_3-heuristics-20260914-151102.json"
P25 = R + "p2_5-qaoa-20260914-160839.json"
P26 = R + "p2_6-hardware-20260914-163413.json"
P31 = R + "p3_1-instance-20260914-184805.json"
P32 = R + "p3_2-qaoa-20260914-190507.json"
P33 = R + "p3_3-q4-20260914-191429.json"
BENCH = "benchmark/p2/baselines.csv"


def supplementary() -> str:
    files = sorted((ROOT / "results").glob("p4_supplementary-*.json"))
    if not files:
        raise SystemExit("run tools/p4_supplementary.py first")
    return files[-1].relative_to(ROOT).as_posix()


_cache: dict = {}


def load(path: str):
    if path not in _cache:
        if path.endswith(".csv"):
            with open(ROOT / path, encoding="utf-8") as f:
                _cache[path] = list(csv.DictReader(f))
        else:
            _cache[path] = json.loads((ROOT / path).read_text(encoding="utf-8"))
    return _cache[path]


def get(path: str, *keys):
    value = load(path)
    for k in keys:
        value = value[k]
    return value


def share(rows, column):
    ok = [r for r in rows if r["feasible"] == "True"]
    return sum(r[column] == "True" for r in ok) / len(ok)


F3, F4, PCT1, INT = "{:.3f}", "{:.4f}", "pct1", "{:d}"


def entries() -> list:
    S = supplementary()
    b = load(BENCH)
    runs = get(P05, "runs")
    gains = [100 * (r["corrected_success"] - r["raw_success"]) for r in runs]
    e = [
        # P0 / P0.5
        ("PzeroKingstonHardware", P0H, lambda: get(P0H, "fits", 2, "hardware"), F3),
        ("PzeroKingstonTheory", P0H, lambda: get(P0H, "fits", 2, "theory"), F3),
        ("PzeroFiveKingstonRaw", P05, lambda: runs[0]["raw_success"], F3),
        ("PzeroFiveKingstonCorrected", P05, lambda: runs[0]["corrected_success"], F3),
        ("PzeroFiveGainMinPP", P05, lambda: min(gains), "{:.1f}"),
        ("PzeroFiveGainMaxPP", P05, lambda: max(gains), "{:.1f}"),
        # P1
        ("PoneOptimumTruth", P10, lambda: get(P10, "summary", "share_optimum_equals_truth"), PCT1),
        ("PoneGateInstances", P11, lambda: sum(s["tested"] for s in get(P11, "summary")), INT),
        ("PoneGatePassed", P11, lambda: sum(s["passed"] for s in get(P11, "summary")), INT),
        ("PoneSafeOverCritThree", P12, lambda: get(P12, "summary", "pure 3x3", "median_safe_over_crit"), "{:.0f}"),
        ("PoneSafeOverCritFour", P12, lambda: get(P12, "summary", "pure 4x4", "median_safe_over_crit"), "{:.0f}"),
        ("PoneSAOracle", P13, lambda: get(P13, "part2_rules", "pure 3x3", "by_rule", "oracle_1.5x_crit", "success"), F3),
        ("PoneSAMaxAbs", P13, lambda: get(P13, "part2_rules", "pure 3x3", "by_rule", "max_abs", "success"), F3),
        ("PoneSASafe", P13, lambda: get(P13, "part2_rules", "pure 3x3", "by_rule", "safe", "success"), F3),
        ("PoneQAOAMaxAbsThree", P14, lambda: get(P14, "results", "pure 3x3", "by_rule", "max_abs", "by_depth", "p3", "p_optimal_mean"), F3),
        ("PoneQAOAOracleThree", P14, lambda: get(P14, "results", "pure 3x3", "by_rule", "oracle_1.5x_crit", "by_depth", "p3", "p_optimal_mean"), F3),
        ("PoneQAOAMaxAbsTwo", P14, lambda: get(P14, "results", "pure 2x2", "by_rule", "max_abs", "by_depth", "p3", "p_optimal_mean"), F3),
        ("PoneCZThreePthree", P14, lambda: get(P14, "results", "pure 3x3", "resources_heavy_hex_estimate", "p3", "two_qubit_gates"), INT),
    ]
    for key, label in (("pure 2x2 p1", "TwoPone"), ("pure 2x2 p2", "TwoPtwo"), ("pure 3x3 p1", "ThreePone")):
        s = lambda k=key: get(P15, "summary", k)  # noqa: E731
        e += [
            ("PoneFive%sCZ" % label, P15, lambda s=s: int(s()["two_qubit_gates_mean"]), INT),
            ("PoneFive%sSim" % label, P15, lambda s=s: s()["simulator_p_optimal"], F4),
            ("PoneFive%sHw" % label, P15, lambda s=s: s()["hardware_corrected_p_optimal"], F4),
            ("PoneFive%sKept" % label, P15, lambda s=s: s()["hardware_corrected_p_optimal"] / s()["simulator_p_optimal"], PCT1),
        ]
    e += [
        # P2
        ("PtwoGateRejectedPct", S, lambda: 100 * get(S, "p2_0_gate_rejection", "rate"), "{:.2f}"),
        ("PtwoGateTruePairs", S, lambda: get(S, "p2_0_gate_rejection", "true_pairs"), "{:,d}"),
        ("PtwoILPGate", P21, lambda: sum(v["checked"] for g in get(P21, "gate") for v in g["sizes"].values()), INT),
        ("PtwoHfourShare", P21, lambda: get(P21, "truth", "3", "share_optimum_equals_truth"), PCT1),
        ("PtwoHfourLow", P21, lambda: get(P21, "truth", "3", "wilson95")[0], PCT1),
        ("PtwoHfourHigh", P21, lambda: get(P21, "truth", "3", "wilson95")[1], PCT1),
        ("PtwoFactorDefault", P21, lambda: get(P21, "factor_study", 0, "share_optimum_equals_truth"), F3),
        ("PtwoFactorPure", P21, lambda: get(P21, "factor_study", 3, "share_optimum_equals_truth"), F3),
        ("PtwoFactorBearing", P21, lambda: get(P21, "factor_study", 4, "share_optimum_equals_truth"), F3),
        ("PtwoFactorBearingNoClutter", P21, lambda: get(P21, "factor_study", 7, "share_optimum_equals_truth"), F3),
        ("PtwoQUBOGate", P22, lambda: sum(s["tested"] for s in get(P22, "summary")), INT),
        ("PtwoQUBOGatePassed", P22, lambda: sum(s["passed"] for s in get(P22, "summary")), INT),
        ("PtwoLRLowClutter", P23, lambda: get(P23, "h2_settings", "clutter 0", "lr_reaches_optimum"), PCT1),
        ("PtwoGapClutterZero", P23, lambda: get(P23, "h2_settings", "clutter 0", "share_with_gap"), F3),
        ("PtwoGapClutterTwo", P23, lambda: get(P23, "h2_settings", "clutter 2", "share_with_gap"), F3),
        ("PtwoGapSpacingClose", P23, lambda: get(P23, "h2_settings", "spacing 25 m", "share_with_gap"), F3),
        ("PtwoGapSpacingFar", P23, lambda: get(P23, "h2_settings", "spacing 100 m", "share_with_gap"), F3),
        ("PtwoBenchInstances", BENCH, lambda: len(b), "{:,d}"),
        ("PtwoBenchInfeasible", BENCH, lambda: sum(r["feasible"] != "True" for r in b), INT),
        ("PtwoBenchGap", BENCH, lambda: sum(r["has_gap"] == "True" for r in b), INT),
        ("PtwoBenchLR", BENCH, lambda: share(b, "lagrangian_optimal"), PCT1),
        ("PtwoBenchSA", BENCH, lambda: share(b, "annealing_optimal"), PCT1),
        ("PtwoBenchGreedy", BENCH, lambda: share(b, "greedy_optimal"), PCT1),
        ("PtwoBenchGreedyNorm", BENCH, lambda: share(b, "greedy_normalised_optimal"), PCT1),
        ("PtwoHthreeMaxAbs", P25, lambda: get(P25, "sets", "pure T=2", "qaoa", "max_abs p3", "p_optimal_mean"), F4),
        ("PtwoHthreeOracle", P25, lambda: get(P25, "sets", "pure T=2", "qaoa", "oracle_1.5x_crit p3", "p_optimal_mean"), F4),
        ("PtwoGoRatio", P25, lambda: get(P25, "go_no_go", "candidates", 6, "ratio_to_guessing"), "{:.1f}"),
        ("PtwoGoCZ", P25, lambda: int(get(P25, "go_no_go", "candidates", 6, "median_cz")), INT),
        ("PtwoSixAKept", P26, lambda: get(P26, "experiments", "A", "summary", "retention_corrected"), F3),
        ("PtwoSixAHw", P26, lambda: get(P26, "experiments", "A", "summary", "hardware_corrected_p_optimal"), F4),
        ("PtwoSixBSim", P26, lambda: get(P26, "experiments", "B", "summary", "simulator_p_optimal"), F4),
        ("PtwoSixBHw", P26, lambda: get(P26, "experiments", "B", "summary", "hardware_corrected_p_optimal"), F4),
        ("PtwoSixBGuess", P26, lambda: get(P26, "experiments", "B", "summary", "ratio_to_guessing_corrected"), "{:.1f}"),
        ("PtwoSixUsage", P26, lambda: get(P26, "experiments", "A", "usage_seconds") + get(P26, "experiments", "B", "usage_seconds"), INT),
        # P3
        ("PthreeOptimum", P31, lambda: get(P31, "variants", "code", "hungarian_as_coded", "objective"), "{:.2f}"),
        ("PthreeOptimumPaperEq", P31, lambda: get(P31, "variants", "paper", "hungarian_as_coded", "objective"), "{:.2f}"),
        ("PthreeOptimumLarge", P33, lambda: get(P33, "optimum"), "{:.2f}"),
        ("PthreeQualityA", P32, lambda: get(P32, "grades", "C2_method_A_p3_quality"), F3),
        ("PthreePoptA", P32, lambda: get(P32, "methods", "A paper FPC", "p3", "p_optimal"), F4),
        ("PthreeReversedA", P32, lambda: get(P32, "methods", "A paper FPC", "p3", "quality_top10_reversed_mean"), F3),
        ("PthreeQualityC", P32, lambda: get(P32, "methods", "C initial, correct", "p3", "quality_top10_mean"), F3),
        ("PthreeQualityD", P32, lambda: get(P32, "methods", "D initial, as bound", "p3", "quality_top10_mean"), F3),
        ("PthreeRandomMean", P32, lambda: get(P32, "Q1_random_baseline", "mean"), F3),
        ("PthreeRandomPninetyfive", P32, lambda: get(P32, "Q1_random_baseline", "p95"), F3),
        ("PthreeRandomAboveHeadline", P32, lambda: get(P32, "Q1_random_baseline", "share_at_or_above_headline"), PCT1),
        ("PthreeRandomBestOfAll", S, lambda: get(S, "p3_2_random_sampling", "best_of_all_mean"), F3),
        ("PthreeLargeQualityPone", P33, lambda: get(P33, "method_a", "p1", "quality_top10_mean"), F3),
        ("PthreeLargeQualityPtwo", P33, lambda: get(P33, "method_a", "p2", "quality_top10_mean"), F3),
        ("PthreeLargeRandomMean", P33, lambda: get(P33, "random_baseline", "mean"), F3),
        ("PthreeLargeRandomAbove", P33, lambda: get(P33, "random_baseline", "share_at_or_above_0.204"), PCT1),
    ]
    return e


LOG_CONSTANTS = [
    ("QPUSecondsPzero", 9, "research log, P0 hardware sweep: IBM dashboard reading"),
    ("QPUSecondsTotal", 81, "research log, P2.6: 63 s from dashboard readings plus 18 s reported by the P2.6 jobs"),
]


def fmt(value, spec: str) -> str:
    if spec == PCT1:
        return "%.1f\\%%" % (100 * value)
    return spec.format(value)


def build() -> tuple[str, dict]:
    lines = ["% Generated by tools/p4_numbers.py from committed result files. Do not edit by hand.", ""]
    table = {}
    for name, source, fn, spec in entries():
        if not re.fullmatch(r"[A-Za-z]+", name):
            raise ValueError("macro name %r must be letters only" % name)
        text = fmt(fn(), spec)
        table[name] = {"value": text, "source": source}
        lines.append("\\newcommand{\\%s}{%s}" % (name, text))
    lines += ["", "% Constants that exist only in the research log (not machine-checkable):"]
    for name, value, note in LOG_CONSTANTS:
        table[name] = {"value": str(value), "source": note}
        lines.append("\\newcommand{\\%s}{%s}  %% %s" % (name, value, note))
    names = [n for n in table]
    if len(names) != len(set(names)):
        raise ValueError("duplicate macro names")
    return "\n".join(lines) + "\n", table


def main() -> None:
    tex, table = build()
    (ROOT / "paper" / "numbers.tex").write_text(tex, encoding="utf-8")
    (ROOT / "paper" / "numbers.json").write_text(json.dumps(table, indent=2), encoding="utf-8")
    print("wrote %d numbers to paper/numbers.tex and paper/numbers.json" % len(table))


if __name__ == "__main__":
    main()
