"""Mann-Whitney significance test for Neal vs. Hybrid across all 23
floorplans (5 real + 18 synthetic), using the repeated-run data from
docs/expansion_repeated_comparison_raw.json (10 Neal + 10 Hybrid runs each).

Same test choice as the original Tier 1 analysis
(scripts/expansion/significance_tests.py): Mann-Whitney U, not paired
Wilcoxon, because Neal's local seeds and Hybrid's server-side randomness
aren't paired observations.

Also folds in the geometry data to check whether the corridor-diameter
finding from EXPANSION_STATISTICAL_CONFIRMATION.md (Neal-only) replicates
under Hybrid.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.stats import mannwhitneyu, pearsonr

ROOT = Path(__file__).resolve().parents[2]


def load_geometry():
    real = json.loads((ROOT / "docs" / "expansion_geometry_bottleneck_raw.json").read_text())
    synth = json.loads((ROOT / "docs" / "expansion_synthetic_geometry_raw.json").read_text())
    return {r["floorplan"]: r for r in real + synth}


def rank_biserial(u, n1, n2):
    return 1.0 - (2.0 * u) / (n1 * n2)


def main() -> None:
    data = json.loads((ROOT / "docs" / "expansion_repeated_comparison_raw.json").read_text())
    geometry = load_geometry()

    rows = []
    for r in data:
        fp = r["floorplan"]
        milp = r["milp_optimum"]
        neal = np.array(r["neal_energies"], dtype=float)
        hybrid = np.array(r["hybrid_energies"], dtype=float)

        u, p = mannwhitneyu(neal, hybrid, alternative="two-sided")
        effect = rank_biserial(u, len(neal), len(hybrid))

        neal_gap = 100 * (neal - milp) / milp
        hybrid_gap = 100 * (hybrid - milp) / milp

        rows.append({
            "floorplan": fp,
            "n_variables": r["n_variables"],
            "is_synthetic": fp.startswith("SYN_"),
            "neal_mean": float(neal.mean()),
            "hybrid_mean": float(hybrid.mean()),
            "neal_gap_mean": float(neal_gap.mean()),
            "hybrid_gap_mean": float(hybrid_gap.mean()),
            "hybrid_gap_min": float(hybrid_gap.min()),
            "neal_gap_min": float(neal_gap.min()),
            "mannwhitney_u": float(u),
            "p_value": float(p),
            "effect_size_r": float(effect),
            "significant_bonferroni_0.002": bool(p < 0.05 / 23),  # 23 tests this time
        })

    print(f"{'FP':20}{'vars':>6}{'Neal gap%':>11}{'Hybrid gap%':>13}{'p-value':>12}{'effect r':>10}{'sig?':>6}")
    for r in rows:
        sig = "yes" if r["significant_bonferroni_0.002"] else "no"
        print(f"{r['floorplan']:20}{r['n_variables']:6}{r['neal_gap_mean']:11.2f}{r['hybrid_gap_mean']:13.2f}"
              f"{r['p_value']:12.2e}{r['effect_size_r']:10.3f}{sig:>6}")

    n_sig = sum(r["significant_bonferroni_0.002"] for r in rows)
    n_hybrid_better = sum(r["hybrid_gap_mean"] < r["neal_gap_mean"] for r in rows)
    print(f"\nHybrid significantly different from Neal (Bonferroni-corrected, 23 tests): {n_sig}/23")
    print(f"Hybrid mean gap smaller than Neal's: {n_hybrid_better}/23")

    # Does corridor diameter also predict Hybrid's gap, not just Neal's?
    y_hybrid = np.array([r["hybrid_gap_mean"] for r in rows])
    y_neal = np.array([r["neal_gap_mean"] for r in rows])
    x_diam = np.array([geometry[r["floorplan"]]["corridor_diameter_hops"] for r in rows], dtype=float)
    x_nvars = np.array([r["n_variables"] for r in rows], dtype=float)

    r_diam_hybrid, p_diam_hybrid = pearsonr(x_diam, y_hybrid)
    r_diam_neal, p_diam_neal = pearsonr(x_diam, y_neal)
    r_nvars_hybrid, p_nvars_hybrid = pearsonr(x_nvars, y_hybrid)

    print(f"\ncorridor_diameter vs Hybrid gap:  r={r_diam_hybrid:.3f}  p={p_diam_hybrid:.2e}")
    print(f"corridor_diameter vs Neal gap:    r={r_diam_neal:.3f}  p={p_diam_neal:.2e}  (Neal-only 10-repeat version)")
    print(f"n_variables vs Hybrid gap:        r={r_nvars_hybrid:.3f}  p={p_nvars_hybrid:.2e}")

    out = {
        "rows": rows,
        "n_significant_bonferroni": n_sig,
        "n_hybrid_better": n_hybrid_better,
        "corridor_diameter_vs_hybrid_gap": {"r": r_diam_hybrid, "p": p_diam_hybrid},
        "corridor_diameter_vs_neal_gap": {"r": r_diam_neal, "p": p_diam_neal},
        "n_variables_vs_hybrid_gap": {"r": r_nvars_hybrid, "p": p_nvars_hybrid},
    }
    out_path = ROOT / "docs" / "expansion_hybrid_significance_raw.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nWritten to {out_path}")


if __name__ == "__main__":
    main()
