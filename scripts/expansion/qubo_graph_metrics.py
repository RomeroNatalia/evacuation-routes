"""Logical QUBO-interaction-graph metrics (plan_9.22.26.md item 4).

The review's central complaint in this area: the paper's structural analysis
(geometry_bottleneck_analysis.py) characterizes the raw navigation graph, but
"the annealer doesn't see the navigation graph. It sees H(x) = sum h_i x_i +
sum J_ij x_i x_j." This computes metrics directly on that logical BQM,
reusing load_and_build_bqm() from neal_budget_scaling_test.py (the exact same
BQM construction solve_qubo_neal.py and the paper's benchmark runs use), for
every route-pair variable in the problem.

Scope, deliberately smaller than the review's full wishlist (treewidth,
spectral properties, frustration, degeneracy are out of scope for this pass
-- see plan_9.22.26.md item 4's note): degree (mean/max), interaction
density, nonzero-J count, and coefficient dynamic range. Two variants are
reported for each:

  - "full" -- the complete penalized BQM as the solvers actually search it,
    including the exactly-one assignment-penalty terms (Equation 6/7). These
    dominate degree/density trivially as a function of exits-per-room (every
    pair of a room's own routes gets a penalty edge), not of corridor
    topology.
  - "congestion" -- the congestion-only Gram-matrix interactions (Equation 5)
    before the assignment penalty is added, pruned at the same 1e-4
    threshold the paper's BQM construction uses. This isolates the
    structural coupling that plausibly varies with corridor topology, since
    the assignment-penalty term's structure is fixed by room/exit counts
    alone.

Usage:
    python scripts/expansion/qubo_graph_metrics.py FP01 FP02 ... SYN_LIN_10_S1_V2 ...
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "expansion"))
from neal_budget_scaling_test import (  # noqa: E402
    read_csv, variable_name, QUADRATIC_PRUNE_THRESHOLD, load_and_build_bqm,
)


def congestion_only_interactions(input_dir: Path) -> Tuple[List[str], Dict[Tuple[str, str], float]]:
    """Mirrors load_and_build_bqm's congestion_gram construction, stopping
    before the assignment penalty (Eq. 6/7) is added, so degree/density here
    reflect only the corridor-driven coupling term (Eq. 5)."""
    routes = read_csv(input_dir / "route_catalog.csv")
    weighted_rows = read_csv(input_dir / "occupancy_weighted_edge_route_matrix.csv")
    edge_rows = read_csv(input_dir / "edge_index.csv")
    edge_ids = [r["edge_id"] for r in edge_rows]

    weighted_incidence = np.zeros((len(routes), len(edge_ids)), dtype=float)
    for i, row in enumerate(weighted_rows):
        for k, edge_id in enumerate(edge_ids):
            weighted_incidence[i, k] = float(row[edge_id])
    capacity_by_edge = {r["edge_id"]: float(r["capacity_units"]) * 10.0 for r in edge_rows}
    capacities = np.array([capacity_by_edge[e] for e in edge_ids], dtype=float)
    normalized_load = weighted_incidence / capacities

    room_indices: Dict[str, List[int]] = defaultdict(list)
    for i, r in enumerate(routes):
        room_indices[r["room_id"]].append(i)
    maximum_feasible_load = np.zeros(normalized_load.shape[1], dtype=float)
    for idxs in room_indices.values():
        maximum_feasible_load += np.max(normalized_load[idxs, :], axis=0)
    congestion_scale = max(float(np.sum(maximum_feasible_load ** 2)), 1.0)
    congestion_multiplier = 5.0 / congestion_scale
    congestion_gram = congestion_multiplier * (normalized_load @ normalized_load.T)

    names = [variable_name(r) for r in routes]
    quadratic: Dict[Tuple[str, str], float] = {}
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            coeff = 2.0 * congestion_gram[i, j]
            if abs(coeff) < QUADRATIC_PRUNE_THRESHOLD:
                continue
            quadratic[(names[i], names[j])] = coeff
    return names, quadratic


def graph_stats(n_vars: int, quadratic: Dict[Tuple[str, str], float]) -> Dict[str, float]:
    degree: Dict[str, int] = defaultdict(int)
    for (u, v) in quadratic:
        degree[u] += 1
        degree[v] += 1
    degrees = list(degree.values())
    abs_j = [abs(c) for c in quadratic.values() if c != 0]
    max_possible = n_vars * (n_vars - 1) / 2
    return {
        "n_interactions": len(quadratic),
        "density": len(quadratic) / max_possible if max_possible > 0 else 0.0,
        "degree_mean": float(np.mean(degrees)) if degrees else 0.0,
        "degree_max": int(max(degrees)) if degrees else 0,
        "coefficient_dynamic_range": (max(abs_j) / min(abs_j)) if abs_j and min(abs_j) > 0 else None,
        "coefficient_abs_max": max(abs_j) if abs_j else None,
        "coefficient_abs_min": min(abs_j) if abs_j else None,
    }


def analyze(fp: str) -> Dict[str, object]:
    input_dir = ROOT / "data" / "floorplans" / fp / "output"
    bqm, routes, room_variables = load_and_build_bqm(input_dir)

    full_interactions = {}
    for (u, v), c in bqm.quadratic.items():
        full_interactions[(u, v)] = c

    names, congestion_quadratic = congestion_only_interactions(input_dir)
    n_vars = len(names)

    result = {"floorplan": fp, "n_variables": n_vars}
    result["full"] = graph_stats(n_vars, full_interactions)
    result["congestion"] = graph_stats(n_vars, congestion_quadratic)
    return result


def main() -> None:
    floorplans = sys.argv[1:]
    results = [analyze(fp) for fp in floorplans]

    out_path = ROOT / "docs" / "expansion_qubo_graph_metrics_raw.json"
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

    print(f"{'floorplan':20}{'N':>5}{'full_deg_mean':>15}{'full_dens':>11}{'cong_deg_mean':>15}{'cong_dens':>11}{'cong_dyn_range':>16}")
    for r in results:
        f, c = r["full"], r["congestion"]
        dr = f"{c['coefficient_dynamic_range']:.1f}" if c["coefficient_dynamic_range"] else "n/a"
        print(
            f"{r['floorplan']:20}{r['n_variables']:5}"
            f"{f['degree_mean']:15.2f}{f['density']:11.4f}"
            f"{c['degree_mean']:15.2f}{c['density']:11.4f}{dr:>16}"
        )
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
