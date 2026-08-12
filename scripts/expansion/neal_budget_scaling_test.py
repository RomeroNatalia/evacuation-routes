"""Test whether FP02/FP03's large optimality gap is a fixed-budget artifact.

The paper uses NUM_READS=1000, NUM_SWEEPS=5000 for every floorplan, from the
16-variable FP04 up to the 264-variable FP02. Structural metrics (branching
factor, assignment-penalty magnitude A) don't cleanly track the measured
optimality gap (see docs/EXPANSION_ROOT_CAUSE_FP02_FP03.md), but problem SIZE
does, almost monotonically. This script tests the direct causal hypothesis:
does the gap shrink toward zero if Neal is simply given more sweeps on the
*same* penalized BQM the paper already built and benchmarked?

This reuses the exact same BQM construction as solve_qubo_neal.py (same
build_base_coefficients, same choose_assignment_penalty, same
add_exact_one_constraints) -- the only thing varied is num_sweeps. If the gap
closes with more sweeps, this is a compute-budget problem, not a
fundamentally different problem structure for FP02/FP03.

Usage:

    python scripts/expansion/neal_budget_scaling_test.py FP02 --sweeps 5000 25000 100000 500000
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Mapping, Sequence, Tuple

import numpy as np
import dimod
import neal

ROOT = Path(__file__).resolve().parents[2]

DISTANCE_WEIGHT = 1.0
CONGESTION_WEIGHT = 5.0
PEOPLE_PER_CAPACITY_UNIT = 10.0
QUADRATIC_PRUNE_THRESHOLD = 1e-4
ASSIGNMENT_PENALTY_SAFETY_FACTOR = 1.5
ASSIGNMENT_PENALTY_MARGIN = 0.25
TOLERANCE = 1e-9


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def variable_name(route: Mapping[str, str]) -> str:
    return f"x_{route['room_id']}_{route['exit_node']}"


def add_bias(d: Dict, key, value: float) -> None:
    if math.isclose(value, 0.0, abs_tol=TOLERANCE):
        return
    d[key] = d.get(key, 0.0) + float(value)


def load_and_build_bqm(input_dir: Path):
    """Exact port of solve_qubo_neal.py's BQM construction (kept in sync by hand;
    see that file for the annotated original)."""
    routes = read_csv(input_dir / "route_catalog.csv")
    weighted_rows = read_csv(input_dir / "occupancy_weighted_edge_route_matrix.csv")
    edge_rows = read_csv(input_dir / "edge_index.csv")
    edge_ids = [r["edge_id"] for r in edge_rows]

    distances = np.array([float(r["distance"]) for r in routes], dtype=float)
    weighted_incidence = np.zeros((len(routes), len(edge_ids)), dtype=float)
    for i, row in enumerate(weighted_rows):
        for k, edge_id in enumerate(edge_ids):
            weighted_incidence[i, k] = float(row[edge_id])
    capacity_by_edge = {r["edge_id"]: float(r["capacity_units"]) * PEOPLE_PER_CAPACITY_UNIT for r in edge_rows}
    capacities = np.array([capacity_by_edge[e] for e in edge_ids], dtype=float)
    normalized_load = weighted_incidence / capacities

    room_indices: Dict[str, List[int]] = defaultdict(list)
    for i, r in enumerate(routes):
        room_indices[r["room_id"]].append(i)

    distance_scale = sum(max(float(distances[i]) for i in idxs) for idxs in room_indices.values())
    maximum_feasible_load = np.zeros(normalized_load.shape[1], dtype=float)
    for idxs in room_indices.values():
        maximum_feasible_load += np.max(normalized_load[idxs, :], axis=0)
    congestion_scale = float(np.sum(maximum_feasible_load ** 2))
    distance_scale = max(float(distance_scale), 1.0)
    congestion_scale = max(congestion_scale, 1.0)

    distance_multiplier = DISTANCE_WEIGHT / distance_scale
    congestion_multiplier = CONGESTION_WEIGHT / congestion_scale
    congestion_gram = congestion_multiplier * (normalized_load @ normalized_load.T)

    names = [variable_name(r) for r in routes]
    linear: Dict[str, float] = {}
    quadratic: Dict[Tuple[str, str], float] = {}
    for i, name in enumerate(names):
        add_bias(linear, name, distance_multiplier * distances[i] + congestion_gram[i, i])
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            coeff = 2.0 * congestion_gram[i, j]
            if abs(coeff) < QUADRATIC_PRUNE_THRESHOLD:
                continue
            add_bias(quadratic, (names[i], names[j]), coeff)

    room_by_name = {variable_name(r): r["room_id"] for r in routes}
    variables_by_room: Dict[str, List[str]] = defaultdict(list)
    for name in names:
        variables_by_room[room_by_name[name]].append(name)

    def interaction(u, v):
        return float(quadratic.get((u, v), quadratic.get((v, u), 0.0)))

    feasible_marginals = []
    for name in names:
        room_id = room_by_name[name]
        marginal = float(linear.get(name, 0.0))
        for other_room, other_vars in variables_by_room.items():
            if other_room == room_id:
                continue
            marginal += max([max(0.0, interaction(name, o)) for o in other_vars], default=0.0)
        feasible_marginals.append(marginal)
    assignment_penalty = ASSIGNMENT_PENALTY_SAFETY_FACTOR * (
        max(feasible_marginals, default=1.0) + ASSIGNMENT_PENALTY_MARGIN
    )

    room_variables: Dict[str, List[str]] = defaultdict(list)
    for r in routes:
        room_variables[r["room_id"]].append(variable_name(r))
    offset = 0.0
    for room_id, variables in room_variables.items():
        offset += assignment_penalty
        for name in variables:
            add_bias(linear, name, -assignment_penalty)
        for i in range(len(variables)):
            for j in range(i + 1, len(variables)):
                add_bias(quadratic, (variables[i], variables[j]), 2.0 * assignment_penalty)

    bqm = dimod.BinaryQuadraticModel("BINARY")
    for v, c in linear.items():
        bqm.add_linear(v, c)
    for (u, v), c in quadratic.items():
        bqm.add_quadratic(u, v, c)
    bqm.offset = offset

    return bqm, routes, room_variables


def exact_one_status(sample, room_variables):
    for room_id, variables in room_variables.items():
        if sum(int(sample.get(v, 0)) for v in variables) != 1:
            return False
    return True


def best_valid_energy(sampleset, room_variables):
    for datum in sampleset.data(fields=["sample", "energy"], sorted_by="energy"):
        if exact_one_status(datum.sample, room_variables):
            return float(datum.energy)
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("floorplan")
    parser.add_argument("--sweeps", type=int, nargs="+", default=[5000, 25000, 100000, 500000])
    parser.add_argument("--reads", type=int, default=200)
    parser.add_argument("--seeds", type=int, nargs="+", default=[42, 43, 44, 45])
    args = parser.parse_args()

    input_dir = ROOT / "data" / "floorplans" / args.floorplan / "output"
    bqm, routes, room_variables = load_and_build_bqm(input_dir)

    milp_path = input_dir / "milp_gap" / "milp_solution_summary.json"
    milp_optimum = json.loads(milp_path.read_text())["energy"] if milp_path.exists() else None

    print(f"{args.floorplan}: {bqm.num_variables} variables, {bqm.num_interactions} interactions")
    if milp_optimum is not None:
        print(f"Certified MILP optimum: {milp_optimum:.6f}")
    print(f"{'sweeps':>10}{'reads_per_seed':>16}{'best_valid_energy':>20}{'gap_pct':>12}{'wall_clock_s':>14}")

    sampler = neal.SimulatedAnnealingSampler()
    results = []
    for sweeps in args.sweeps:
        reads_per_seed = max(1, math.ceil(args.reads / len(args.seeds)))
        start = time.perf_counter()
        sample_sets = [
            sampler.sample(bqm, num_reads=reads_per_seed, num_sweeps=sweeps, seed=seed)
            for seed in args.seeds
        ]
        sampleset = dimod.concatenate(sample_sets).aggregate()
        elapsed = time.perf_counter() - start

        best = best_valid_energy(sampleset, room_variables)
        gap_pct = 100.0 * (best - milp_optimum) / milp_optimum if (best is not None and milp_optimum) else None
        gap_str = f"{gap_pct:.2f}%" if gap_pct is not None else "n/a"
        print(f"{sweeps:>10}{reads_per_seed:>16}{best:>20.6f}{gap_str:>12}{elapsed:>14.2f}")
        results.append({
            "sweeps": sweeps,
            "reads_per_seed": reads_per_seed,
            "total_reads": reads_per_seed * len(args.seeds),
            "best_valid_energy": best,
            "gap_pct": gap_pct,
            "wall_clock_seconds": elapsed,
        })

    out_dir = input_dir / "budget_scaling"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "neal_budget_scaling.json"
    out_path.write_text(json.dumps({
        "floorplan": args.floorplan,
        "milp_optimum": milp_optimum,
        "baseline_paper_sweeps": 5000,
        "baseline_paper_reads": 1000,
        "results": results,
    }, indent=2), encoding="utf-8")
    print(f"\nWritten to {out_path}")


if __name__ == "__main__":
    main()
