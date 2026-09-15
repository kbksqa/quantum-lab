# P4.1 - Figures for the technical report, drawn only from committed result files.
#
#   fig1_penalty.pdf     P1: annealing success against A / A_crit (3x3, 4x4), and annealing vs QAOA at two penalty rules
#   fig2_truth.pdf       P2.1: share of scenes where the optimum equals the truth, one factor at a time (95% Wilson intervals)
#   fig3_baselines.pdf   P2.4: share of benchmark instances solved optimally, by number of targets
#   fig4_hardware.pdf    P1.5 and P2.6: simulator against readout-corrected hardware P(optimal)
#   fig5_metric.pdf      P3.2: the paper's top-10 quality for QAOA variants against uniform random sampling
#
# Usage:
#     python tools/p4_figures.py

from __future__ import annotations

import csv
import json
import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "paper" / "figures"


def load(name: str):
    return json.loads((ROOT / "results" / name).read_text(encoding="utf-8"))


def style(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.3)


def fig1():
    p12 = load("p1_2-penalty-20260914-125028.json")
    p13 = load("p1_3-annealing-20260914-125703.json")
    p14 = load("p1_4-qaoa-20260914-131628.json")
    fig, (a, b) = plt.subplots(1, 2, figsize=(8, 3.2))
    for size, marker in (("pure 3x3", "o"), ("pure 4x4", "s")):
        rows = p12["summary"][size]["by_penalty"]
        keys = [k for k in rows if k.startswith("x")]
        a.plot([rows[k]["median_A_over_Acrit"] for k in keys], [rows[k]["mean_sa_success"] for k in keys], marker=marker, label=size)
    a.set_xscale("log")
    a.set_xlabel("penalty A / A_crit")
    a.set_ylabel("annealing success per restart")
    a.legend(frameon=False)
    style(a)
    rules = ("oracle_1.5x_crit", "max_abs")
    labels = ("1.5 x A_crit", "max|c|")
    sa = [p13["part2_rules"]["pure 3x3"]["by_rule"][r]["success"] for r in rules]
    qa = [p14["results"]["pure 3x3"]["by_rule"][r]["by_depth"]["p3"]["p_optimal_mean"] for r in rules]
    x = range(len(rules))
    b.bar([i - 0.2 for i in x], sa, width=0.4, label="annealing (per restart)")
    b.bar([i + 0.2 for i in x], qa, width=0.4, label="QAOA p = 3 (per sample)")
    b.set_xticks(list(x), labels)
    b.set_ylabel("P(optimal), 3x3")
    b.legend(frameon=False, fontsize=8)
    style(b)
    fig.tight_layout()
    fig.savefig(OUT / "fig1_penalty.pdf")


def fig2():
    rows = load("p2_1-ilp-20260914-144533.json")["factor_study"]
    fig, ax = plt.subplots(figsize=(8, 3.4))
    shares = [r["share_optimum_equals_truth"] for r in rows]
    err = [[s - r["wilson95"][0] for s, r in zip(shares, rows)], [r["wilson95"][1] - s for s, r in zip(shares, rows)]]
    ax.bar(range(len(rows)), shares, yerr=err, capsize=3)
    ax.set_xticks(range(len(rows)), [r["variant"] for r in rows], rotation=25, ha="right", fontsize=8)
    ax.set_ylabel("optimum = truth (T = 3)")
    ax.set_ylim(0, 1)
    style(ax)
    fig.tight_layout()
    fig.savefig(OUT / "fig2_truth.pdf")


def fig3():
    with open(ROOT / "benchmark" / "p2" / "baselines.csv", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["feasible"] == "True"]
    targets = sorted({int(r["targets"]) for r in rows})
    fig, ax = plt.subplots(figsize=(6, 3.2))
    for method, label in (("lagrangian", "Lagrangian relaxation"), ("annealing", "simulated annealing"),
                          ("greedy", "greedy"), ("greedy_normalised", "greedy, normalised")):
        ys = []
        for t in targets:
            group = [r for r in rows if int(r["targets"]) == t]
            ys.append(sum(r[method + "_optimal"] == "True" for r in group) / len(group))
        ax.plot(targets, ys, marker="o", label=label)
    ax.set_xlabel("targets")
    ax.set_ylabel("share optimal")
    ax.set_ylim(0, 1.02)
    ax.set_xticks(targets)
    ax.legend(frameon=False, fontsize=8)
    style(ax)
    fig.tight_layout()
    fig.savefig(OUT / "fig3_baselines.pdf")


def fig4():
    p15 = load("p1_5-hardware-20260914-133130.json")["summary"]
    p26 = load("p2_6-hardware-20260914-163413.json")["experiments"]
    bars = [("P1.5 2x2 p=1\nibm_kingston", p15["pure 2x2 p1"]["simulator_p_optimal"], p15["pure 2x2 p1"]["hardware_corrected_p_optimal"]),
            ("P1.5 2x2 p=2\nibm_kingston", p15["pure 2x2 p2"]["simulator_p_optimal"], p15["pure 2x2 p2"]["hardware_corrected_p_optimal"]),
            ("P2.6 2x2 p=2\nibm_fez", p26["A"]["summary"]["simulator_p_optimal"], p26["A"]["summary"]["hardware_corrected_p_optimal"]),
            ("P1.5 3x3 p=1\nibm_kingston", p15["pure 3x3 p1"]["simulator_p_optimal"], p15["pure 3x3 p1"]["hardware_corrected_p_optimal"]),
            ("P2.6 3D p=1\nibm_kingston", p26["B"]["summary"]["simulator_p_optimal"], p26["B"]["summary"]["hardware_corrected_p_optimal"])]
    fig, ax = plt.subplots(figsize=(8, 3.2))
    x = range(len(bars))
    ax.bar([i - 0.2 for i in x], [s for _, s, _ in bars], width=0.4, label="simulator")
    ax.bar([i + 0.2 for i in x], [h for _, _, h in bars], width=0.4, label="hardware (readout-corrected)")
    ax.set_xticks(list(x), [n for n, _, _ in bars], fontsize=8)
    ax.set_yscale("log")
    ax.set_ylim(0.01, 1)                                               # three labelled decades
    ax.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())  # major decades only; minor labels crowded the axis
    ax.set_ylabel("P(optimal)")
    ax.legend(frameon=False, fontsize=8)
    style(ax)
    fig.tight_layout()
    fig.savefig(OUT / "fig4_hardware.pdf")


def fig5():
    d = load("p3_2-qaoa-20260914-190507.json")
    q1 = d["Q1_random_baseline"]
    methods = [("A paper FPC", "A: paper FPC"), ("B public code", "B: public code"),
               ("C initial, correct", "C: initial, correct"), ("D initial, as bound", "D: initial, as bound")]
    fig, ax = plt.subplots(figsize=(7, 3.2))
    ax.axhspan(q1["p5"], q1["p95"], color="grey", alpha=0.2, label="uniform random, 5th-95th percentile")
    ax.axhline(q1["mean"], color="grey", lw=1, label="uniform random, mean")
    ax.axhline(0.641, color="black", ls="--", lw=1, label="paper's hardware headline 0.641")
    for i, (key, label) in enumerate(methods):
        m = d["methods"][key]["p3"]
        ax.errorbar(i, m["quality_top10_mean"], yerr=m["quality_top10_sd"], fmt="o", capsize=3)
    ax.set_xticks(range(len(methods)), [l for _, l in methods], fontsize=8)
    ax.set_ylabel("top-10 quality, p = 3")
    ax.set_ylim(0, 1.05)
    ax.legend(frameon=False, fontsize=7, loc="lower right")
    style(ax)
    fig.tight_layout()
    fig.savefig(OUT / "fig5_metric.pdf")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.size": 9, "pdf.fonttype": 42})
    for fn in (fig1, fig2, fig3, fig4, fig5):
        fn()
        print("wrote", fn.__name__)


if __name__ == "__main__":
    main()
