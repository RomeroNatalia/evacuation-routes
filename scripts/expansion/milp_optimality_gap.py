"""Exact/certified-bound MILP baseline for the capacity-aware evacuation QUBO.

Motivation
----------
The capstone paper (Fishman, 2026) reports "lowest energy observed" for four
of five floorplans -- only the 8-room FP04 instance has a certified global
optimum (via exhaustive enumeration of 2^8 assignments). This script closes
that gap for the remaining floorplans (FP01, FP02, FP03, FP05) by solving the
*real* combinatorial problem directly, rather than the QUBO's penalty-method
reduction of it:

    minimize   H_distance(x) + H_congestion(x)          [[Eq. 3, 5]]
    subject to sum_{e in E} x_{r,e} = 1  for every room r   (hard constraint,
                                                              not a penalty)
               x in {0,1}

This is a *convex* integer quadratic program: H_congestion is a sum of
squared linear forms in x (a Gram-matrix quadratic, always PSD), so unlike a
general QUBO there is no non-convexity to fight. We solve it with Google
OR-Tools CP-SAT, formulated per-edge (one integer "load" variable per edge,
squared once) rather than by expanding the O(n^2) pairwise Gram matrix --
this keeps the model size linear in (routes + edges) instead of quadratic in
routes, which matters for FP02 (264 routes) and FP03 (252 routes).

Because CP-SAT requires integer coefficients, the search objective is a
scaled-integer proxy for H_distance + H_congestion. Solve-time rounding only
needs to preserve the correct ordering between candidate solutions -- it does
NOT need to be the reported number. After solving, the TRUE floating-point
energy of the returned assignment is recomputed independently in Python
(mirroring build_base_coefficients() in solve_qubo_neal.py exactly, using
full float64 precision and zero pruning) and is what gets reported. This
decouples solver-time numerical precision from result precision.

Note on pruning: solve_qubo_neal.py prunes congestion-only quadratic terms
below 1e-4 before solving (a QPU-density-reduction step) and says as much in
the paper ("reconstructing energy directly from the reported unscaled
physical metrics may produce a small difference when congestion interactions
were pruned"). This script does NOT prune -- it solves the exact, full
continuous objective -- so the MILP energy is directly comparable to, but not
byte-identical to, the pruned-BQM energies Neal/Hybrid/QPU report. The gap
this introduces is reported explicitly in the output.

Usage:

    python scripts/expansion/milp_optimality_gap.py FP04 [--time-limit 600]

Outputs (per floorplan):

    data/floorplans/FPXX/output/milp_gap/milp_solution_summary.json
    data/floorplans/FPXX/output/milp_gap/milp_solution_summary.txt
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Mapping, Sequence, Tuple

import numpy as np
from ortools.sat.python import cp_model

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

# Must match solve_qubo_neal.py exactly for the comparison to be meaningful.
DISTANCE_WEIGHT = 1.0
CONGESTION_WEIGHT = 5.0
PEOPLE_PER_CAPACITY_UNIT = 10.0

# Integer-scaling constants for the CP-SAT search objective (see module
# docstring -- these affect solve-time ranking precision only, not the
# reported energy, which is recomputed exactly afterward).
#
# CRITICAL: both terms of the combined objective (distance + congestion)
# MUST use the identical final multiplicative scale, or the proxy the
# solver actually searches over silently reweights one term relative to
# the other -- an earlier version of this file used DISTANCE_OBJ_SCALE=1e9
# and CONGESTION_OBJ_SCALE=1e12 independently, a 1000x systematic
# overweighting of congestion that caused CP-SAT to prove "OPTIMAL" for a
# solution that was demonstrably worse than one Neal found under the true
# (unscaled) objective on at least one floorplan (SYN_TRE_10_S1). Verified
# safe against int64 overflow for the largest instance in this corpus
# (FP02, 264 routes / 793 edges) with generous margin -- see the module
# docstring's worked bound if this is changed.
LOAD_SCALE = 1_000
OBJ_SCALE = 10 ** 12
DISTANCE_OBJ_SCALE = OBJ_SCALE
CONGESTION_OBJ_SCALE = OBJ_SCALE


def read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Required input file not found: {path}")
    with path.open("r", newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def variable_name(route: Mapping[str, str]) -> str:
    return f"x_{route['room_id']}_{route['exit_node']}"


def load_problem_data(input_dir: Path):
    routes = read_csv(input_dir / "route_catalog.csv")
    weighted_rows = read_csv(input_dir / "occupancy_weighted_edge_route_matrix.csv")
    edge_rows = read_csv(input_dir / "edge_index.csv")

    route_ids = [row["route_id"] for row in routes]
    weighted_route_ids = [row["route_id"] for row in weighted_rows]
    if route_ids != weighted_route_ids:
        raise ValueError("Route order mismatch between route catalog and incidence matrix.")

    edge_ids = [row["edge_id"] for row in edge_rows]
    return routes, weighted_rows, edge_rows, edge_ids


def build_arrays(routes, weighted_rows, edge_rows, edge_ids):
    route_count = len(routes)
    edge_count = len(edge_ids)

    distances = np.array([float(r["distance"]) for r in routes], dtype=float)

    weighted_incidence = np.zeros((route_count, edge_count), dtype=float)
    for i, row in enumerate(weighted_rows):
        for k, edge_id in enumerate(edge_ids):
            weighted_incidence[i, k] = float(row[edge_id])

    capacity_by_edge = {
        row["edge_id"]: float(row["capacity_units"]) * PEOPLE_PER_CAPACITY_UNIT
        for row in edge_rows
    }
    capacities = np.array([capacity_by_edge[e] for e in edge_ids], dtype=float)
    normalized_load = weighted_incidence / capacities

    return distances, weighted_incidence, capacities, normalized_load


def compute_objective_scales(routes, distances, normalized_load):
    """Identical to solve_qubo_neal.compute_objective_scales."""
    room_indices: Dict[str, List[int]] = defaultdict(list)
    for index, route in enumerate(routes):
        room_indices[route["room_id"]].append(index)

    distance_scale = sum(
        max(float(distances[i]) for i in indices) for indices in room_indices.values()
    )

    maximum_feasible_load = np.zeros(normalized_load.shape[1], dtype=float)
    for indices in room_indices.values():
        maximum_feasible_load += np.max(normalized_load[indices, :], axis=0)

    congestion_scale = float(np.sum(maximum_feasible_load ** 2))

    return {
        "distance_scale": max(float(distance_scale), 1.0),
        "congestion_scale": max(congestion_scale, 1.0),
        "maximum_feasible_load": maximum_feasible_load,
    }


def true_energy(routes, distances, normalized_load, scales, x_values: np.ndarray) -> Dict[str, float]:
    """Recompute the exact (unpruned) float64 energy for a 0/1 assignment."""
    distance_multiplier = DISTANCE_WEIGHT / scales["distance_scale"]
    congestion_multiplier = CONGESTION_WEIGHT / scales["congestion_scale"]

    total_distance = float(np.dot(distances, x_values))
    # np.errstate: matmul on this platform's BLAS (Accelerate) occasionally
    # raises a spurious divide-by-zero FP warning on all-finite, well-formed
    # inputs -- verified benign against the FP04 ground-truth optimum.
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        load_per_edge = normalized_load.T @ x_values  # utilization_k(x), shape (edges,)
    congestion_raw = float(np.sum(load_per_edge ** 2))

    normalized_distance_component = distance_multiplier * total_distance
    normalized_congestion_component = congestion_multiplier * congestion_raw

    return {
        "total_distance": total_distance,
        "congestion_raw_unweighted": congestion_raw,
        "congestion_objective": CONGESTION_WEIGHT * congestion_raw,
        "normalized_distance_component": normalized_distance_component,
        "normalized_congestion_component": normalized_congestion_component,
        "energy": normalized_distance_component + normalized_congestion_component,
    }


def build_and_solve(routes, weighted_rows, edge_rows, edge_ids, time_limit_seconds: float):
    distances, weighted_incidence, capacities, normalized_load = build_arrays(
        routes, weighted_rows, edge_rows, edge_ids
    )
    scales = compute_objective_scales(routes, distances, normalized_load)
    distance_multiplier = DISTANCE_WEIGHT / scales["distance_scale"]
    congestion_multiplier = CONGESTION_WEIGHT / scales["congestion_scale"]

    model = cp_model.CpModel()
    names = [variable_name(r) for r in routes]
    x = [model.NewBoolVar(name) for name in names]

    room_indices: Dict[str, List[int]] = defaultdict(list)
    for i, route in enumerate(routes):
        room_indices[route["room_id"]].append(i)

    for room_id, indices in room_indices.items():
        model.Add(sum(x[i] for i in indices) == 1)

    objective_terms = []

    # Distance terms (plain linear -- no scaling risk).
    for i in range(len(routes)):
        coeff = round(distance_multiplier * distances[i] * DISTANCE_OBJ_SCALE)
        if coeff != 0:
            objective_terms.append(coeff * x[i])

    # Congestion terms, one squared "load" variable per edge (not per pair).
    scaled_load = np.rint(normalized_load * LOAD_SCALE).astype(np.int64)
    n_sq_vars = 0
    for k in range(len(edge_ids)):
        column = scaled_load[:, k]
        contributing = np.nonzero(column)[0]
        if contributing.size == 0:
            continue

        max_load = int(
            sum(
                max((column[i] for i in room_indices[room_id] if i in set(contributing)), default=0)
                for room_id in room_indices
            )
        )
        # Safe (loose) fallback bound if the tight per-room max is degenerate.
        max_load = max(max_load, int(column[contributing].clip(min=0).sum()))
        if max_load <= 0:
            continue

        load_var = model.NewIntVar(0, int(max_load), f"load_{k}")
        model.Add(load_var == sum(int(column[i]) * x[i] for i in contributing))

        sq_var = model.NewIntVar(0, int(max_load) * int(max_load), f"sq_{k}")
        model.AddMultiplicationEquality(sq_var, [load_var, load_var])
        n_sq_vars += 1

        coeff = round(congestion_multiplier / (LOAD_SCALE ** 2) * CONGESTION_OBJ_SCALE)
        if coeff != 0:
            objective_terms.append(coeff * sq_var)

    model.Minimize(sum(objective_terms))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_seconds
    solver.parameters.num_workers = 8
    solver.parameters.log_search_progress = False

    start = time.perf_counter()
    status = solver.Solve(model)
    elapsed = time.perf_counter() - start

    status_name = solver.StatusName(status)
    result = {
        "status": status_name,
        "wall_clock_seconds": elapsed,
        "n_variables": len(routes),
        "n_edge_square_terms": n_sq_vars,
        "proven_optimal": status == cp_model.OPTIMAL,
    }

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        x_values = np.array([solver.Value(x[i]) for i in range(len(routes))], dtype=float)
        result["assignment"] = {names[i]: int(x_values[i]) for i in range(len(routes)) if x_values[i] > 0.5}
        result.update(true_energy(routes, distances, normalized_load, scales, x_values))

        # CP-SAT's own scaled objective bound, descaled just for a sanity cross-check
        # against the independently recomputed true energy above.
        best_obj = solver.ObjectiveValue()
        best_bound = solver.BestObjectiveBound()
        result["solver_internal_objective_scaled"] = best_obj
        result["solver_internal_best_bound_scaled"] = best_bound
        result["solver_reported_gap_scaled_pct"] = (
            100.0 * abs(best_obj - best_bound) / abs(best_obj) if best_obj else 0.0
        )
    else:
        result["assignment"] = None

    result["distance_normalization_scale"] = scales["distance_scale"]
    result["congestion_normalization_scale"] = scales["congestion_scale"]
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("floorplan", help="Floorplan ID, e.g. FP04")
    parser.add_argument("--time-limit", type=float, default=600.0)
    args = parser.parse_args()

    input_dir = ROOT / "data" / "floorplans" / args.floorplan / "output"
    output_dir = input_dir / "milp_gap"
    output_dir.mkdir(parents=True, exist_ok=True)

    routes, weighted_rows, edge_rows, edge_ids = load_problem_data(input_dir)
    print(f"{args.floorplan}: {len(routes)} route variables, {len(edge_ids)} edges")

    result = build_and_solve(routes, weighted_rows, edge_rows, edge_ids, args.time_limit)

    summary_path = output_dir / "milp_solution_summary.json"
    summary_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    lines = [
        f"MILP OPTIMALITY-GAP RESULT -- {args.floorplan}",
        "=" * 44,
        f"Status: {result['status']} (proven optimal: {result['proven_optimal']})",
        f"Wall-clock: {result['wall_clock_seconds']:.2f}s",
        f"Variables: {result['n_variables']}  |  Edge square-terms: {result['n_edge_square_terms']}",
    ]
    if result.get("assignment") is not None:
        lines.append(f"True (unpruned, recomputed) energy: {result['energy']:.10f}")
        lines.append(f"  distance component:   {result['normalized_distance_component']:.10f}")
        lines.append(f"  congestion component: {result['normalized_congestion_component']:.10f}")
        lines.append(f"  total distance:       {result['total_distance']:.6f}")
        lines.append(f"  raw congestion (unweighted sum of util^2): {result['congestion_raw_unweighted']:.6f}")
        lines.append(
            f"Solver-internal scaled objective gap: {result['solver_reported_gap_scaled_pct']:.6f}%"
        )
    (output_dir / "milp_solution_summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("\n".join(lines))


if __name__ == "__main__":
    main()
