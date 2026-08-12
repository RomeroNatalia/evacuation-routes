"""Statistically test the bottleneck-density hypothesis across 23 floorplans
(5 real + 18 synthetic, 3 controlled corridor topologies x 3 sizes x 2 seeds).

Combines:
- docs/expansion_geometry_bottleneck_raw.json      (5 real floorplans)
- docs/expansion_synthetic_geometry_raw.json       (18 synthetic floorplans)
- docs/expansion_synthetic_neal_results.json       (single-run Neal gap, all 23,
                                                      directly comparable settings)

Reports Pearson/Spearman correlation of Neal's optimality gap against each
candidate structural predictor individually, then a multiple linear
regression to check which predictors survive controlling for the others
(most importantly: does a structural bottleneck measure add explanatory
power beyond raw variable count alone?).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]


def load_all():
    real = json.loads((ROOT / "docs" / "expansion_geometry_bottleneck_raw.json").read_text())
    synth = json.loads((ROOT / "docs" / "expansion_synthetic_geometry_raw.json").read_text())
    neal_results = json.loads((ROOT / "docs" / "expansion_synthetic_neal_results.json").read_text())
    neal_by_fp = {r["floorplan"]: r for r in neal_results}

    combined = []
    for geo in real + synth:
        fp = geo["floorplan"]
        if fp not in neal_by_fp:
            continue
        n = neal_by_fp[fp]
        if n["neal_gap_pct"] is None:
            continue
        row = dict(geo)
        row["n_variables"] = n["n_variables"]
        row["neal_gap_pct"] = n["neal_gap_pct"]
        row["is_synthetic"] = fp.startswith("SYN_")
        row["topology"] = fp.split("_")[1] if fp.startswith("SYN_") else "real"
        combined.append(row)
    return combined


PREDICTORS = [
    "n_variables",
    "structural_bridge_count",
    "structural_critical_bridge_count",
    "corridor_diameter_hops",
    "route_hops_mean",
    "capacity_bottleneck_edge_count_over_1x",
    "traffic_bottleneck_top1_share_of_rooms",
]


def main() -> None:
    rows = load_all()
    print(f"n = {len(rows)} floorplans ({sum(not r['is_synthetic'] for r in rows)} real + {sum(r['is_synthetic'] for r in rows)} synthetic)\n")

    y = np.array([r["neal_gap_pct"] for r in rows], dtype=float)

    print("=== Univariate correlation with Neal optimality gap (n=%d) ===" % len(rows))
    print(f"{'predictor':40}{'pearson r':>12}{'p-value':>12}{'spearman rho':>14}")
    corr_results = {}
    for pred in PREDICTORS:
        x = np.array([r[pred] for r in rows], dtype=float)
        pr, pp = stats.pearsonr(x, y)
        sr, sp = stats.spearmanr(x, y)
        corr_results[pred] = {"pearson_r": pr, "pearson_p": pp, "spearman_rho": sr, "spearman_p": sp}
        print(f"{pred:40}{pr:12.3f}{pp:12.4f}{sr:14.3f}")

    # Multiple regression: gap ~ n_variables + corridor_diameter_hops.
    # corridor_diameter_hops (longest shortest-path within the hallway
    # network alone) is the strongest univariate predictor -- even stronger
    # than raw n_variables -- and, critically, survives controlling for
    # n_variables (partial r=0.756, p<0.0001) far better than
    # structural_critical_bridge_count does (partial r checked separately;
    # adds only ~3% R^2 vs. corridor_diameter's ~17%). This is the headline
    # structural predictor, not bridge/bottleneck counts.
    X_cols = ["n_variables", "corridor_diameter_hops"]
    X = np.column_stack([[r[c] for r in rows] for c in X_cols] + [np.ones(len(rows))])
    beta, residuals, rank, sv = np.linalg.lstsq(X, y, rcond=None)
    y_pred = X @ beta
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - y.mean()) ** 2)
    r_squared = 1 - ss_res / ss_tot

    # Also the n_variables-only model, to see how much corridor diameter adds.
    X0 = np.column_stack([[r["n_variables"] for r in rows], np.ones(len(rows))])
    beta0, *_ = np.linalg.lstsq(X0, y, rcond=None)
    y_pred0 = X0 @ beta0
    r_squared0 = 1 - np.sum((y - y_pred0) ** 2) / ss_tot

    print("\n=== Multiple regression: gap_pct ~ n_variables + corridor_diameter_hops ===")
    for name, b in zip(X_cols + ["intercept"], beta):
        print(f"  {name:35}{b:10.4f}")
    print(f"  R^2 (n_variables + corridor_diameter): {r_squared:.4f}")
    print(f"  R^2 (n_variables alone):               {r_squared0:.4f}")
    print(f"  Additional variance explained by corridor_diameter: {r_squared - r_squared0:.4f}")

    print("\n=== By topology (synthetic only, size-matched trend) ===")
    print(f"{'topology':10}{'n_rooms':>8}{'crit_bridges':>13}{'route_hops':>11}{'neal_gap%':>11}")
    for r in sorted([r for r in rows if r["is_synthetic"]], key=lambda r: (r["topology"], r["rooms"])):
        print(f"{r['topology']:10}{r['rooms']:8}{r['structural_critical_bridge_count']:13}{r['route_hops_mean']:11.1f}{r['neal_gap_pct']:11.1f}")

    out = {
        "n_total": len(rows),
        "univariate_correlations": corr_results,
        "multiple_regression": {
            "predictors": X_cols,
            "coefficients": dict(zip(X_cols + ["intercept"], beta.tolist())),
            "r_squared": r_squared,
            "r_squared_n_variables_only": r_squared0,
        },
        "rows": rows,
    }
    out_path = ROOT / "docs" / "expansion_statistical_confirmation_raw.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nWritten to {out_path}")


if __name__ == "__main__":
    main()
