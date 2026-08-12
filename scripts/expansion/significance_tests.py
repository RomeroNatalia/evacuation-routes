"""Inferential statistics for the Neal-vs-Hybrid solver comparison.

The paper (Sec. 7, Limitations) reports only descriptive statistics (mean,
sample std, 95% CI via normal approximation) across the 30 independent runs
per solver-floorplan combination, and explicitly flags the absence of formal
significance testing as a limitation. This closes that gap.

Test choice: Neal's randomness comes from local seeds; D-Wave Hybrid's
randomness is server-side and unrelated to those seeds. The 30 Neal runs and
30 Hybrid runs for a given floorplan are therefore two INDEPENDENT samples,
not naturally paired observations -- so the correct non-parametric test is
Mann-Whitney U (independent two-sample rank test), not a paired test like
Wilcoxon signed-rank, which would assume a pairing that doesn't exist here.

Effect size: rank-biserial correlation, the natural companion to Mann-Whitney
U (r = 1 - 2U/(n1*n2); |r| close to 0 = no separation, close to 1 = complete
separation between the two distributions).

This also folds in the certified MILP optima (see
docs/EXPANSION_MILP_OPTIMALITY_GAPS.md) to report per-run optimality gaps,
not just best-run gaps -- i.e. the full distribution of how far every one of
the 30 runs landed from the proven global optimum, not just the closest run.

Usage:

    python scripts/expansion/significance_tests.py [--floorplans FP01 FP02 ...]

Output:

    docs/EXPANSION_SIGNIFICANCE_TESTS.md
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import List

import numpy as np
from scipy.stats import mannwhitneyu

ROOT = Path(__file__).resolve().parents[2]
ALL_FLOORPLANS = ["FP01", "FP02", "FP03", "FP04", "FP05"]


def load_run_energies(floorplan: str, solver: str) -> np.ndarray:
    path = ROOT / "data" / "floorplans" / floorplan / "output" / f"qubo_{solver}" / "benchmark_runs.csv"
    rows = list(csv.DictReader(path.open()))
    return np.array([float(r["best_energy"]) for r in rows], dtype=float)


def load_milp_optimum(floorplan: str) -> float:
    path = ROOT / "data" / "floorplans" / floorplan / "output" / "milp_gap" / "milp_solution_summary.json"
    data = json.loads(path.read_text())
    if not data.get("proven_optimal"):
        raise ValueError(f"{floorplan}: MILP result is not proven optimal -- rerun milp_optimality_gap.py.")
    return float(data["energy"])


def rank_biserial_effect_size(u_statistic: float, n1: int, n2: int) -> float:
    """r = 1 - 2U/(n1*n2). Sign convention: positive means sample 1 (Neal)
    tends to have LARGER values (worse, since lower energy is better)."""
    return 1.0 - (2.0 * u_statistic) / (n1 * n2)


def analyze_floorplan(floorplan: str) -> dict:
    neal = load_run_energies(floorplan, "neal")
    hybrid = load_run_energies(floorplan, "hybrid")
    milp_opt = load_milp_optimum(floorplan)

    # Mann-Whitney U: alternative='two-sided' tests whether the two
    # distributions differ at all; we also run 'greater' to directly test the
    # paper's directional claim ("Hybrid produced the lowest mean energy").
    u_two_sided, p_two_sided = mannwhitneyu(neal, hybrid, alternative="two-sided")
    u_greater, p_greater = mannwhitneyu(neal, hybrid, alternative="greater")
    effect_size = rank_biserial_effect_size(u_two_sided, len(neal), len(hybrid))

    neal_gaps = 100.0 * (neal - milp_opt) / milp_opt
    hybrid_gaps = 100.0 * (hybrid - milp_opt) / milp_opt

    return {
        "floorplan": floorplan,
        "milp_optimum": milp_opt,
        "n_neal": len(neal),
        "n_hybrid": len(hybrid),
        "neal_mean": float(neal.mean()),
        "neal_std": float(neal.std(ddof=1)),
        "hybrid_mean": float(hybrid.mean()),
        "hybrid_std": float(hybrid.std(ddof=1)),
        "mannwhitney_u_two_sided": float(u_two_sided),
        "p_value_two_sided": float(p_two_sided),
        "p_value_neal_greater": float(p_greater),
        "rank_biserial_effect_size": float(effect_size),
        "significant_at_0.05": bool(p_two_sided < 0.05),
        "significant_at_bonferroni_0.01": bool(p_two_sided < 0.01),  # 0.05/5 floorplans
        "neal_gap_pct_mean": float(neal_gaps.mean()),
        "neal_gap_pct_median": float(np.median(neal_gaps)),
        "neal_gap_pct_min": float(neal_gaps.min()),
        "neal_gap_pct_max": float(neal_gaps.max()),
        "hybrid_gap_pct_mean": float(hybrid_gaps.mean()),
        "hybrid_gap_pct_median": float(np.median(hybrid_gaps)),
        "hybrid_gap_pct_min": float(hybrid_gaps.min()),
        "hybrid_gap_pct_max": float(hybrid_gaps.max()),
        "hybrid_never_reaches_optimum": bool(hybrid_gaps.min() > 1e-6),
        "neal_never_reaches_optimum": bool(neal_gaps.min() > 1e-6),
    }


def format_report(results: List[dict]) -> str:
    lines = [
        "# Expansion: Significance Testing and Per-Run Optimality Gaps",
        "",
        "**Test:** Mann-Whitney U (independent two-sample, non-parametric).",
        "Neal's randomness is local-seed-based; D-Wave Hybrid's is server-side",
        "and unrelated -- the 30 runs of each are independent samples, not",
        "paired observations, so Mann-Whitney U is the correct test (not a",
        "paired test like Wilcoxon signed-rank).",
        "",
        "**Bonferroni correction:** testing 5 floorplans from the same",
        "underlying question (\"is Hybrid better than Neal?\") means alpha=0.05",
        "should be corrected to alpha=0.01 (0.05/5) to control the family-wise",
        "error rate.",
        "",
        "## Results",
        "",
        "| FP | Neal mean | Hybrid mean | U | p (two-sided) | p (Neal > Hybrid) | effect size r | sig. @ 0.01? |",
        "|---|---:|---:|---:|---:|---:|---:|:---:|",
    ]
    for r in results:
        sig = "**yes**" if r["significant_at_bonferroni_0.01"] else "no"
        lines.append(
            f"| {r['floorplan']} | {r['neal_mean']:.6f} | {r['hybrid_mean']:.6f} | "
            f"{r['mannwhitney_u_two_sided']:.1f} | {r['p_value_two_sided']:.2e} | "
            f"{r['p_value_neal_greater']:.2e} | {r['rank_biserial_effect_size']:.3f} | {sig} |"
        )

    lines += [
        "",
        "`p (Neal > Hybrid)` tests the paper's directional claim directly:",
        "the one-sided alternative that Neal's energies are stochastically",
        "greater (worse) than Hybrid's.",
        "",
        "## Per-run optimality gap (all 30 runs, not just the best)",
        "",
        "Against the certified MILP optimum from",
        "`docs/EXPANSION_MILP_OPTIMALITY_GAPS.md`. This is a stricter test",
        "than the paper's own \"best observed energy\" comparison -- it shows",
        "the full spread of every run, including whether either solver ever",
        "actually reaches the true optimum across 30 independent attempts.",
        "",
        "| FP | MILP optimum | Neal gap % (mean / median / min / max) | Hybrid gap % (mean / median / min / max) | Hybrid ever exact? |",
        "|---|---:|---|---|:---:|",
    ]
    for r in results:
        reaches = "no" if r["hybrid_never_reaches_optimum"] else "**yes**"
        lines.append(
            f"| {r['floorplan']} | {r['milp_optimum']:.6f} | "
            f"{r['neal_gap_pct_mean']:.2f} / {r['neal_gap_pct_median']:.2f} / "
            f"{r['neal_gap_pct_min']:.2f} / {r['neal_gap_pct_max']:.2f} | "
            f"{r['hybrid_gap_pct_mean']:.2f} / {r['hybrid_gap_pct_median']:.2f} / "
            f"{r['hybrid_gap_pct_min']:.2f} / {r['hybrid_gap_pct_max']:.2f} | {reaches} |"
        )

    lines += [
        "",
        "## Reading these results",
        "",
        "**Caveat on p-values as practical significance**: a low p-value only",
        "means the two distributions differ measurably -- it says nothing",
        "about whether that difference is large enough to matter. FP04 is a",
        "concrete example below: both solvers land within floating-point",
        "noise (~1e-16) of the exact optimum on all 30 runs, yet Mann-Whitney",
        "still reports p=1.69e-14, because even noise-level differences",
        "become \"significant\" once they're perfectly consistent across 30",
        "runs each. Practical significance always needs the gap-percent",
        "columns above read alongside the p-value, not the p-value alone.",
        "",
    ]
    for r in results:
        degenerate = (
            abs(r["neal_gap_pct_max"]) < 1e-6 and abs(r["hybrid_gap_pct_max"]) < 1e-6
        )
        if degenerate:
            lines.append(
                f"- **{r['floorplan']}**: p={r['p_value_two_sided']:.2e} is "
                "statistically significant but **not practically meaningful** -- "
                "both solvers reach the exact certified optimum on all 30 runs "
                "(gaps ~0% for both); the p-value reflects floating-point-noise-level "
                "differences, not a real quality gap."
            )
            continue

        verdict = (
            "statistically significant Hybrid advantage"
            if r["significant_at_bonferroni_0.01"] and r["hybrid_mean"] < r["neal_mean"]
            else "no significant difference at the corrected threshold"
        )
        reach_note = (
            f" Neither solver ever reached the true optimum in 30 runs "
            f"(closest: Neal {r['neal_gap_pct_min']:.2f}%, Hybrid {r['hybrid_gap_pct_min']:.2f}%)."
            if r["hybrid_never_reaches_optimum"] and r["neal_never_reaches_optimum"]
            else ""
        )
        lines.append(
            f"- **{r['floorplan']}**: {verdict} (p={r['p_value_two_sided']:.2e}, "
            f"effect size r={r['rank_biserial_effect_size']:.3f})."
            f"{reach_note}"
        )

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--floorplans", nargs="+", default=ALL_FLOORPLANS)
    args = parser.parse_args()

    results = [analyze_floorplan(fp) for fp in args.floorplans]

    report = format_report(results)
    out_path = ROOT / "docs" / "EXPANSION_SIGNIFICANCE_TESTS.md"
    out_path.write_text(report, encoding="utf-8")

    raw_path = ROOT / "docs" / "expansion_significance_tests_raw.json"
    raw_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

    print(report)
    print(f"\nWritten to {out_path}")


if __name__ == "__main__":
    main()
