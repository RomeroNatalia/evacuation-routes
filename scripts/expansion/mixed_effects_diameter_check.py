"""Mixed-effects check for the statistical-unit problem (plan_9.22.26.md item 5).

The 18-floorplan synthetic corpus contains only 9 unique topology/size graph
structures, each evaluated under two independently-drawn occupancy/capacity
seeds (documented as a limitation in both papers). Pooling all 23 floorplans
(5 unique benchmark layouts + 18 synthetic = 14 unique structures) as if they
were 23 independent observations inflates the effective sample size behind
Table 5's correlation and regression p-values.

This fits the exact model the review's Section 6 proposes:

    gap_ij = beta_0 + beta_1 * diameter_i + beta_2 * n_variables_i + u_i + eps_ij

with u_i a random intercept per unique graph structure i (14 groups: 5
benchmark floorplans, each its own unique structure, plus 9 synthetic
topology/size structures each with 2 seeds j). A likelihood-ratio test
compares this model against the reduced model without diameter, isolating
whether diameter adds explanatory power beyond n_variables once the repeated-
structure clustering is properly accounted for (not just pooled-n=23 partial
correlation, which was already reported separately -- see item 4's partial
correlations in qubo_graph_metrics.py's companion analysis).

Requires statsmodels (not a project dependency prior to this script; install
with `pip install statsmodels` if missing).

Usage:
    python scripts/expansion/mixed_effects_diameter_check.py
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]


def cluster_id(floorplan: str) -> str:
    if floorplan.startswith("FP"):
        return floorplan  # each benchmark floorplan is its own unique structure
    parts = floorplan.split("_")
    return f"{parts[1]}_{parts[2]}"  # SYN_<TOPOLOGY>_<SIZE>_S<seed>_V2 -> topology+size


def main() -> None:
    combined = json.loads((ROOT / "docs" / "expansion_v2_combined_23instance_raw.json").read_text())
    rows = [
        {
            "floorplan": r["floorplan"],
            "cluster": cluster_id(r["floorplan"]),
            "diameter": r["corridor_diameter_hops"],
            "n_variables": r["n_variables"],
            "neal_gap": r["neal_gap_pct"],
            "hybrid_gap": r["hybrid_gap_pct"],
        }
        for r in combined
    ]
    df = pd.DataFrame(rows)
    n_clusters = df["cluster"].nunique()
    print(f"{len(df)} observations across {n_clusters} unique graph structures\n")

    results = {}
    for label, col in [("neal", "neal_gap"), ("hybrid", "hybrid_gap")]:
        reduced = smf.mixedlm(f"{col} ~ n_variables", df, groups=df["cluster"]).fit(reml=False)
        full = smf.mixedlm(f"{col} ~ diameter + n_variables", df, groups=df["cluster"]).fit(reml=False)
        lr_stat = 2 * (full.llf - reduced.llf)
        p_lr = float(stats.chi2.sf(lr_stat, df=1))

        print(f"=== {label.capitalize()} ===")
        print(full.summary().tables[1])
        print(f"Likelihood-ratio test (diameter added vs. n_variables-only): "
              f"stat={lr_stat:.3f}, p={p_lr:.4f}\n")

        results[label] = {
            "diameter_coef": float(full.params["diameter"]),
            "diameter_p": float(full.pvalues["diameter"]),
            "n_variables_coef": float(full.params["n_variables"]),
            "n_variables_p": float(full.pvalues["n_variables"]),
            "group_var": float(full.cov_re.iloc[0, 0]),
            "lr_stat_diameter": lr_stat,
            "lr_p_diameter": p_lr,
        }

    out = {"n_observations": len(df), "n_clusters": n_clusters, **results}
    out_path = ROOT / "docs" / "expansion_mixed_effects_raw.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
