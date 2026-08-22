"""CP-SAT integer-scaling stability check.

A referee objection to the paper's optimality-gap claim (Section 6.3 /
Limitations) is that CP-SAT's OPTIMAL certificate applies to the
*integer-scaled* proxy objective, not the original unrounded float64
objective, and that coefficient rounding could in principle change which
assignment is selected as optimal.

This script re-solves the same per-edge CP-SAT formulation as
milp_optimality_gap.py across several independent (LOAD_SCALE, OBJ_SCALE)
settings -- each an order of magnitude apart -- for the two floorplans with
the largest reported gaps (FP02, FP03), and checks whether:

    (a) the selected assignment (set of x_{r,e}=1 routes) is identical
        across all scales, and
    (b) the recomputed true (unpruned, float64) energy is identical.

If both hold across a wide range of scales, coefficient rounding is not
plausibly responsible for the reported gap -- the same optimum is being
recovered regardless of solve-time precision. This does not *prove*
order-preservation as a theorem, but it is strong empirical evidence against
the rounding-artifact objection, using the same infrastructure already in
the repo (milp_optimality_gap.py) rather than a new formulation.

Usage:

    python scripts/expansion/scaling_stability_check.py FP02 FP03
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Dict, List

import numpy as np
from ortools.sat.python import cp_model

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "expansion"))

from milp_optimality_gap import (  # noqa: E402
    DISTANCE_WEIGHT,
    CONGESTION_WEIGHT,
    build_arrays,
    compute_objective_scales,
    load_problem_data,
    true_energy,
    variable_name,
)

# Each (LOAD_SCALE, OBJ_SCALE) pair is solved independently and compared.
# The paper's reported results use LOAD_SCALE=1_000, OBJ_SCALE=10**12 (the
# middle setting here). Two orders of magnitude coarser and two orders finer
# bracket it on both sides.
SCALE_SETTINGS = [
    (10, 10 ** 10),
    (100, 10 ** 11),
    (1_000, 10 ** 12),   # paper's reported setting
    (10_000, 10 ** 13),
    (100_000, 10 ** 14),
]


def build_and_solve_at_scale(routes, weighted_rows, edge_rows, edge_ids, load_scale: int, obj_scale: int, time_limit_seconds: float):
    distances, weighted_incidence, capacities, normalized_load = build_arrays(
        routes, weighted_rows, edge_rows, edge_ids
    )
    scales = compute_objective_scales(routes, distances, normalized_load)
    distance_multiplier = DISTANCE_WEIGHT / scales["distance_scale"]
    congestion_multiplier = CONGESTION_WEIGHT / scales["congestion_scale"]

    model = cp_model.CpModel()
    names = [variable_name(r) for r in routes]
    x = [model.NewBoolVar(name) for name in names]

    room_indices: Dict[str, List[int]] = {}
    for i, route in enumerate(routes):
        room_indices.setdefault(route["room_id"], []).append(i)

    for room_id, indices in room_indices.items():
        model.Add(sum(x[i] for i in indices) == 1)

    objective_terms = []

    for i in range(len(routes)):
        coeff = round(distance_multiplier * distances[i] * obj_scale)
        if coeff != 0:
            objective_terms.append(coeff * x[i])

    scaled_load = np.rint(normalized_load * load_scale).astype(np.int64)
    for k in range(len(edge_ids)):
        column = scaled_load[:, k]
        contributing = np.nonzero(column)[0]
        if contributing.size == 0:
            continue

        contributing_set = set(contributing)
        max_load = int(
            sum(
                max((column[i] for i in room_indices[room_id] if i in contributing_set), default=0)
                for room_id in room_indices
            )
        )
        max_load = max(max_load, int(column[contributing].clip(min=0).sum()))
        if max_load <= 0:
            continue

        load_var = model.NewIntVar(0, int(max_load), f"load_{k}")
        model.Add(load_var == sum(int(column[i]) * x[i] for i in contributing))

        sq_var = model.NewIntVar(0, int(max_load) * int(max_load), f"sq_{k}")
        model.AddMultiplicationEquality(sq_var, [load_var, load_var])

        coeff = round(congestion_multiplier / (load_scale ** 2) * obj_scale)
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
    assignment = None
    energy = None
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        x_values = np.array([solver.Value(x[i]) for i in range(len(routes))], dtype=float)
        assignment = frozenset(names[i] for i in range(len(routes)) if x_values[i] > 0.5)
        energy = true_energy(routes, distances, normalized_load, scales, x_values)

    return {
        "load_scale": load_scale,
        "obj_scale": obj_scale,
        "status": status_name,
        "proven_optimal": status == cp_model.OPTIMAL,
        "wall_clock_seconds": elapsed,
        "assignment": assignment,
        "energy": energy["energy"] if energy else None,
    }


def run_floorplan(floorplan: str, time_limit_seconds: float) -> Dict:
    input_dir = ROOT / "data" / "floorplans" / floorplan / "output"
    routes, weighted_rows, edge_rows, edge_ids = load_problem_data(input_dir)

    print(f"\n{floorplan}: {len(routes)} route variables, {len(edge_ids)} edges")
    runs = []
    for load_scale, obj_scale in SCALE_SETTINGS:
        result = build_and_solve_at_scale(
            routes, weighted_rows, edge_rows, edge_ids, load_scale, obj_scale, time_limit_seconds
        )
        print(
            f"  LOAD_SCALE={load_scale:<8} OBJ_SCALE={obj_scale:<15.0e} "
            f"status={result['status']:<10} energy={result['energy']:.10f} "
            f"time={result['wall_clock_seconds']:.2f}s"
        )
        runs.append(result)

    reference_assignment = runs[0]["assignment"]
    reference_energy = runs[0]["energy"]
    assignment_stable = all(r["assignment"] == reference_assignment for r in runs)
    max_energy_delta = max(abs(r["energy"] - reference_energy) for r in runs)

    print(f"  --> assignment identical across all {len(runs)} scales: {assignment_stable}")
    print(f"  --> max energy delta across scales: {max_energy_delta:.2e}")

    return {
        "floorplan": floorplan,
        "assignment_stable_across_scales": assignment_stable,
        "max_energy_delta_across_scales": max_energy_delta,
        "runs": [
            {
                "load_scale": r["load_scale"],
                "obj_scale": r["obj_scale"],
                "status": r["status"],
                "proven_optimal": r["proven_optimal"],
                "wall_clock_seconds": r["wall_clock_seconds"],
                "energy": r["energy"],
                "assignment_matches_baseline": r["assignment"] == reference_assignment,
            }
            for r in runs
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("floorplans", nargs="+", help="Floorplan IDs, e.g. FP02 FP03")
    parser.add_argument("--time-limit", type=float, default=120.0)
    args = parser.parse_args()

    all_results = [run_floorplan(fp, args.time_limit) for fp in args.floorplans]

    output_path = ROOT / "docs" / "expansion_cpsat_scaling_stability_raw.json"
    output_path.write_text(json.dumps(all_results, indent=2), encoding="utf-8")
    print(f"\nWrote {output_path}")


if __name__ == "__main__":
    main()
