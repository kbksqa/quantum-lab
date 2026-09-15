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
# added for report version 1.1 (docs/p4-plan.md, amendment 1)
P28B = R + "p2_8-benchmark-20260915-102524.json"
P28C = R + "p2_8-cvar-20260915-102642.json"
P28H = R + "p2_8-h5-hardware-20260915-110607.json"
P50 = R + "p5_0-gates-20260915-140211.json"
P51 = R + "p5_1-study-20260915-141313.json"
P61 = R + "p6_1-tiger-20260915-150853.json"
P62R = R + "p6_2-resources-20260915-152850.json"
P62L = R + "p6_2-loops-20260915-152714.json"
P63E = R + "p6_3-entrypoint-20260915-171109.json"
P63 = R + "p6_3-table6-20260915-171313.json"
P64 = R + "p6_4-hardware-20260915-172851.json"


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


F3, F4, PCT1, INT, SCI = "{:.3f}", "{:.4f}", "pct1", "{:d}", "sci"


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
        ("PtwoSixAKept", P26, lambda: get(P26, "experiments", "A", "summary", "retention_corrected"), PCT1),
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
        # added while drafting (P4.2)
        ("PtwoQUBOInfeasible", P22, lambda: sum(s["infeasible"] for s in get(P22, "summary")), INT),
        ("PtwoHthreePurePositive", P25, lambda: get(P25, "sets", "pure T=2", "paired_max_abs_minus_oracle", "p3", "positive_share"), PCT1),
        ("PtwoHthreeSparsePositive", P25, lambda: get(P25, "sets", "sparse T=2", "paired_max_abs_minus_oracle", "p3", "positive_share"), PCT1),
        ("PtwoPureCZ", P25, lambda: int(get(P25, "go_no_go", "candidates", 0, "median_cz")), INT),
        ("PtwoBenchLRInvalid", BENCH, lambda: sum(r["feasible"] == "True" and r["lagrangian_valid"] != "True" for r in b), INT),
        ("PtwoBenchGreedyInvalid", BENCH, lambda: sum(r["feasible"] == "True" and r["greedy_valid"] != "True" for r in b), INT),
        ("PtwoBenchLRGap", BENCH, lambda: share([r for r in b if r["has_gap"] == "True"], "lagrangian_optimal"), PCT1),
        ("PtwoSixBCZMin", P26, lambda: min(get(P26, "experiments", "B", "two_qubit_gates")), INT),
        ("PtwoSixBCZMax", P26, lambda: max(get(P26, "experiments", "B", "two_qubit_gates")), INT),
        ("PthreePaperHungarian", P31, lambda: get(P31, "paper_hungarian"), "{:.1f}"),
        ("PthreeCOneDiff", P31, lambda: get(P31, "grades", "C1_difference"), F3),
        ("PthreeLargePaperOptimum", P33, lambda: get(P33, "paper_optimum"), "{:.1f}"),
        ("PthreeLargePaperPone", P33, lambda: get(P33, "paper_hardware_quality", "1"), PCT1),
        ("PthreeLargePaperPtwo", P33, lambda: get(P33, "paper_hardware_quality", "2"), PCT1),
    ]
    e += [
        # P2.8 (version 1.1)
        ("PtwoEightLRValid", P28B, lambda: get(P28B, "h7_verdict", "dissolve", "valid"), PCT1),
        ("PtwoEightLROptimal", P28B, lambda: get(P28B, "h7_verdict", "dissolve", "optimal"), PCT1),
        ("PtwoEightLRFormerFailures", P28B, lambda: len(get(P28B, "h7_verdict", "former_failures")), INT),
        ("PtwoEightLRFormerNowOptimal", P28B, lambda: get(P28B, "h7_verdict", "former_failures_now_optimal"), INT),
        ("PtwoEightJoinedGLR", P28B, lambda: get(P28B, "h6_verdict", "joined_clutter_total", "glr"), INT),
        ("PtwoEightJoinedMarginal", P28B, lambda: get(P28B, "h6_verdict", "joined_clutter_total", "marginal"), INT),
        ("PtwoEightClutterMeasurements", P28B, lambda: get(P28B, "h6_verdict", "joined_clutter_total", "clutter_measurements"), "{:,d}"),
        ("PtwoEightJoinedBetter", P28B, lambda: get(P28B, "h6_verdict", "H6a_less_clutter_joined", "better"), INT),
        ("PtwoEightJoinedWorse", P28B, lambda: get(P28B, "h6_verdict", "H6a_less_clutter_joined", "worse"), INT),
        ("PtwoEightTruthGain", P28B, lambda: get(P28B, "h6_verdict", "H6b_truth_more_often", "better"), INT),
        ("PtwoEightTruthLoss", P28B, lambda: get(P28B, "h6_verdict", "H6b_truth_more_often", "worse"), INT),
        ("PtwoEightCvarPone", P28C, lambda: get(P28C, "h8_verdict", "depths", "p1", "cvar_p_optimal_mean"), F4),
        ("PtwoEightExpPone", P28C, lambda: get(P28C, "h8_verdict", "depths", "p1", "expectation_p_optimal_mean"), F4),
        ("PtwoEightCvarPthree", P28C, lambda: get(P28C, "h8_verdict", "depths", "p3", "cvar_p_optimal_mean"), F3),
        ("PtwoEightExpPthree", P28C, lambda: get(P28C, "h8_verdict", "depths", "p3", "expectation_p_optimal_mean"), F3),
        ("PtwoEightHfiveKept", P28H, lambda: get(P28H, "h5_day_verdict", "retention_corrected"), PCT1),
        ("PtwoEightHfiveRawKept", P28H, lambda: get(P28H, "experiments", "A", "summary", "retention_raw"), PCT1),
        ("PtwoEightBadQubit", P28H, lambda: get(P28H, "experiments", "A", "per_qubit_errors", "16")[0], PCT1),
        ("PtwoEightUsage", P28H, lambda: get(P28H, "experiments", "A", "usage_seconds"), INT),
        # P5 (version 1.1)
        ("PfiveGateMaxDiff", P50, lambda: get(P50, "G1", "pure 3x3", "max_amplitude_difference"), SCI),
        ("PfiveXpenPone", P51, lambda: get(P51, "pure 3x3", "summary", "xpen p1", "p_optimal_mean"), F3),
        ("PfiveXpenPthree", P51, lambda: get(P51, "pure 3x3", "summary", "xpen p3", "p_optimal_mean"), F3),
        ("PfiveRxyPone", P51, lambda: get(P51, "pure 3x3", "summary", "rxy p1", "p_optimal_mean"), F3),
        ("PfiveRxyPthree", P51, lambda: get(P51, "pure 3x3", "summary", "rxy p3", "p_optimal_mean"), F3),
        ("PfivePermPone", P51, lambda: get(P51, "pure 3x3", "summary", "perm p1", "p_optimal_mean"), F3),
        ("PfivePermPthree", P51, lambda: get(P51, "pure 3x3", "summary", "perm p3", "p_optimal_mean"), F3),
        ("PfiveXpenCZ", P51, lambda: int(get(P51, "pure 3x3", "summary", "xpen p1", "median_cz_first_instances")), INT),
        ("PfiveRxyCZ", P51, lambda: int(get(P51, "pure 3x3", "summary", "rxy p1", "median_cz_first_instances")), INT),
        ("PfivePermCZ", P51, lambda: int(get(P51, "pure 3x3", "summary", "perm p1", "median_cz_first_instances")), "{:,d}"),
        ("PfiveXpenLiftPone", P51, lambda: get(P51, "pure 3x3", "summary", "xpen p1", "lift_mean"), "{:.1f}"),
        ("PfiveRxyLiftPone", P51, lambda: get(P51, "pure 3x3", "summary", "rxy p1", "lift_mean"), "{:.1f}"),
        ("PfivePermLiftPone", P51, lambda: get(P51, "pure 3x3", "summary", "perm p1", "lift_mean"), "{:.1f}"),
        ("PfivePermLift", P51, lambda: get(P51, "verdicts_pure_3x3", "H3_perm_lift_p3", "mean"), "{:.2f}"),
        ("PfivePermLiftSE", P51, lambda: get(P51, "verdicts_pure_3x3", "H3_perm_lift_p3", "sem"), "{:.2f}"),
        # P6 (version 1.1)
        ("PsixCOneBase", P61, lambda: get(P61, "C1", "ours", "p_obs1_baseline"), F4),
        ("PsixCOneGrover", P61, lambda: get(P61, "C1", "ours", "p_obs1_grover"), F4),
        ("PsixCOnePostLeft", P61, lambda: get(P61, "C1", "ours", "posterior")[0], F4),
        ("PsixCOneAmp", P61, lambda: get(P61, "C1", "ours", "amplification"), "{:.2f}"),
        ("PsixCTwoMax", P61, lambda: max(get(P61, "C2", "max_hellinger_2_state", "listen"),
                                         get(P61, "C2", "max_hellinger_4_state")), SCI),
        ("PsixCSixFormulaOne", P61, lambda: get(P61, "C6", "formula")[1], F3),
        ("PsixCSixFormulaThree", P61, lambda: get(P61, "C6", "formula")[3], F3),
        ("PsixCSixSectionIterations", P61, lambda: get(P61, "C6", "iteration_formulas", "section_5_2_floor(pi/(4 theta) - 1/2)"), INT),
        ("PsixCSevenH", P61, lambda: get(P61, "C7", "example", "hellinger"), F4),
        ("PsixCSevenTV", P61, lambda: get(P61, "C7", "example", "total_variation"), PCT1),
        ("PsixQOneTheory", P61, lambda: get(P61, "Q1", "theory", "grover_over_direct_per_call"), "{:.2f}"),
        ("PsixCThreeListenCZ", P62R, lambda: get(P62R, "circuits", "minimal_listen", "theirs", "cz_range")[0], INT),
        ("PsixCThreeListenDepth", P62R, lambda: get(P62R, "circuits", "minimal_listen", "theirs", "depth_range")[0], INT),
        ("PsixCThreeGroverCZ", P62R, lambda: get(P62R, "circuits", "grover1", "theirs", "cz_range")[0], INT),
        ("PsixCThreeGroverDepth", P62R, lambda: get(P62R, "circuits", "grover1", "theirs", "depth_range")[0], INT),
        ("PsixCThreeFourCZ", P62R, lambda: get(P62R, "circuits", "four_state", "theirs", "cz_range")[0], INT),
        ("PsixCThreeFourDepth", P62R, lambda: get(P62R, "circuits", "four_state", "theirs", "depth_range")[0], INT),
        ("PsixCThreeFullCZMin", P62R, lambda: get(P62R, "circuits", "framework", "theirs", "cz_range")[0], "{:,d}"),
        ("PsixCThreeFullCZMax", P62R, lambda: get(P62R, "circuits", "framework", "theirs", "cz_range")[1], "{:,d}"),
        ("PsixCThreeFullDepthMin", P62R, lambda: get(P62R, "circuits", "framework", "theirs", "depth_range")[0], "{:,d}"),
        ("PsixCThreeFullDepthMax", P62R, lambda: get(P62R, "circuits", "framework", "theirs", "depth_range")[1], "{:,d}"),
        ("PsixQTwoValue", P62L, lambda: get(P62L, "Q2", "value_iteration", "value_at_0.5"), "{:.2f}"),
        ("PsixQTwoThreshold", P62L, lambda: get(P62L, "Q2", "value_iteration", "open_right_when_p_tiger_right_below"), F4),
        ("PsixQTwoGreedyThreshold", P62L, lambda: get(P62L, "Q2", "greedy_thresholds", "open_right_when_p_tiger_right_below"), "{:.1f}"),
        ("PsixCFiveEntryReward", P63E, lambda: float(re.search(r"avg reward: (-?\d+\.\d+)", get(P63E, "log")[-3]).group(1)), "{:.2f}"),
        ("PsixCFiveHorizonMean", P63, lambda: get(P63, "exploratory_protocols", 2, "mean"), "{:.1f}"),
        ("PsixCFiveHorizonSD", P63, lambda: get(P63, "exploratory_protocols", 2, "sd"), "{:.1f}"),
        ("PsixCFiveOptimalMean", P63, lambda: get(P63, "exploratory_protocols", 3, "mean"), "{:.1f}"),
        ("PsixCFiveOptimalSD", P63, lambda: get(P63, "exploratory_protocols", 3, "sd"), "{:.1f}"),
        ("PsixHwBase", P64, lambda: get(P64, "mean_raw", "p_obs1_baseline"), F3),
        ("PsixHwGrover", P64, lambda: get(P64, "mean_raw", "p_obs1_grover"), F3),
        ("PsixHwAmp", P64, lambda: get(P64, "mean_raw", "amplification"), "{:.2f}"),
        ("PsixHwHellinger", P64, lambda: get(P64, "mean_raw", "posterior_hellinger"), F4),
        ("PsixHwPerOracle", P64, lambda: get(P64, "mean_raw", "grover_over_direct_per_oracle_application"), "{:.2f}"),
        ("PsixHwUsage", P64, lambda: get(P64, "usage_seconds"), INT),
    ]
    return e


LOG_CONSTANTS = [
    ("QPUSecondsPzero", 9, "research log, P0 hardware sweep: IBM dashboard reading"),
    ("QPUSecondsTotal", 110, "research log, P6.4: 63 s from dashboard readings plus 18 s (P2.6), 9 s (P2.8) and 20 s (P6.4) "
                             "reported by the jobs"),
]

# Numbers reported by the paper under study, quoted (not our results). Only those not already stored in a result file.
QUOTED_CONSTANTS = [
    ("PthreePaperHeadline", "64.1", "quoted from arXiv:2603.00785, Sec. 8.6 and Table 15 (percent of optimum)"),
    ("PthreePaperHeadlineSD", "3.3", "quoted from arXiv:2603.00785, Sec. 8.6 (percentage points, three runs)"),
    ("PthreePaperTwoQubitGates", "433--435", "quoted from arXiv:2603.00785, Sec. 8.6 and Table 4 (p = 3)"),
    ("PthreePaperSimPthree", "90.9", "quoted from arXiv:2603.00785, Sec. 8.6 (simulator quality, p = 3, percent)"),
    # version 1.1: the POMDP half of the same paper
    ("PsixPaperBase", "0.179", "quoted from arXiv:2603.00785, Sec. 8.6 and Table 15 (hardware baseline P(obs = 1))"),
    ("PsixPaperGrover", "0.907", "quoted from arXiv:2603.00785, Sec. 8.6 and Table 15 (hardware P(obs = 1) after one Grover iterate)"),
    ("PsixPaperAmp", "5.1", "quoted from arXiv:2603.00785, Sec. 8.6 (hardware amplification)"),
    ("PsixPaperTheoryBase", "0.171", "quoted from arXiv:2603.00785, Sec. 8.6 (theory baseline)"),
    ("PsixPaperTheoryGrover", "0.917", "quoted from arXiv:2603.00785, Sec. 8.6 (theory after one iterate)"),
    ("PsixPaperPass", "0.15", "quoted from arXiv:2603.00785, Sec. 2.4 and 8.6 (Hellinger pass threshold)"),
    ("PsixPaperTV", "1.1", "quoted from arXiv:2603.00785, Sec. 2.4 and 8.6 (stated total-variation equivalent, percent)"),
    ("PsixCodePass", "0.05", "quoted from github.com/neuraparse/qantis at 7c6509c, scripts/hardware (pass threshold in code)"),
    ("PsixPaperFourObsZero", "0.128", "quoted from arXiv:2603.00785, Table 15 (4-state obs 0 Hellinger)"),
    ("PsixPaperTableOne", "0.192", "quoted from arXiv:2603.00785, Table 21 (amplified P(e), G = 1)"),
    ("PsixPaperTableThree", "0.912", "quoted from arXiv:2603.00785, Table 21 (amplified P(e), G = 3)"),
    ("PsixPaperTableIterations", "3", "quoted from arXiv:2603.00785, Table 21 (stated optimal G)"),
    ("PsixPaperISAListen", "12", "quoted from arXiv:2603.00785, Sec. 8.6 (Tiger minimal circuit)"),
    ("PsixPaperISAGrover", "18", "quoted from arXiv:2603.00785, Sec. 8.6 (Grover circuit)"),
    ("PsixPaperISAFour", "162", "quoted from arXiv:2603.00785, Sec. 8.6 (4-state circuit)"),
    ("PsixPaperISAFull", "4{,}237", "quoted from arXiv:2603.00785, Sec. 5.3 and 8.6 (full 11-qubit circuit)"),
    ("PsixPaperTableSixQBRL", "18.7", "quoted from arXiv:2603.00785, Table 6 (QBRL reward)"),
    ("PsixPaperTableSixSD", "12.1", "quoted from arXiv:2603.00785, Table 6 (QBRL standard deviation)"),
    ("PsixPaperListen", "0.85", "quoted from arXiv:2603.00785, Sec. 8.6 (listening accuracy)"),
    ("PsixPaperGamma", "0.95", "quoted from arXiv:2603.00785, Sec. 8.2.1 (discount factor)"),
]


def fmt(value, spec: str) -> str:
    if spec == PCT1:
        return "%.1f\\%%" % (100 * value)
    if spec == SCI:
        mantissa, exponent = ("%.1e" % value).split("e")
        return "%s\\times10^{%d}" % (mantissa, int(exponent))              # use inside math mode
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
    lines += ["", "% Numbers reported by the paper under study (quoted, not results of this project):"]
    for name, value, note in QUOTED_CONSTANTS:
        table[name] = {"value": value, "source": note}
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
