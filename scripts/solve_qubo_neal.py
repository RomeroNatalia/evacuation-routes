"""Build and solve the floorplan evacuation QUBO with D-Wave Ocean.

This version does all of the following:

1. Reads the route, occupancy-weighted incidence, and edge-index CSV files.
2. Builds a dimod.BinaryQuadraticModel directly.
3. Exports the QUBO coefficients and dense matrix to CSV.
4. Solves the BQM with neal.SimulatedAnnealingSampler.
5. Decodes the best binary sample into one exit assignment per room.
6. Reports total route distance, edge congestion, and exit usage.

Install dependencies:

    python -m pip install numpy dimod dwave-neal

Run from the repository root:

    python scripts/solve_qubo_neal.py

Expected inputs:

    data/floorplans/FPXX/output/route_catalog.csv
    data/floorplans/FPXX/output/occupancy_weighted_edge_route_matrix.csv
    data/floorplans/FPXX/output/edge_index.csv

Generated outputs:

    data/floorplans/FPXX/output/qubo_model/qubo_variable_index.csv
    data/floorplans/FPXX/output/qubo_model/qubo_linear_coefficients.csv
    data/floorplans/FPXX/output/qubo_model/qubo_quadratic_coefficients.csv
    data/floorplans/FPXX/output/qubo_model/qubo_upper_triangular.csv
    data/floorplans/FPXX/output/qubo_model/qubo_dense_xtqx.csv
    data/floorplans/FPXX/output/qubo_neal/neal_samples.csv
    data/floorplans/FPXX/output/qubo_neal/selected_assignments.csv
    data/floorplans/FPXX/output/qubo_neal/edge_congestion_report.csv
    data/floorplans/FPXX/output/qubo_neal/exit_usage_report.csv
    data/floorplans/FPXX/output/qubo_neal/solution_summary.json
    data/floorplans/FPXX/output/qubo_neal/solution_summary.txt
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import csv
import json
import math
import sys
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

import numpy as np

try:
    import dimod
    import neal
except ImportError as exc:
    raise SystemExit(
        "\nMissing D-Wave Ocean packages.\n"
        "Install them with:\n\n"
        "    python -m pip install dimod dwave-neal\n"
    ) from exc


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from fire_evacuation.project import floorplan_paths_from_argv  # noqa: E402

FLOORPLAN = floorplan_paths_from_argv(ROOT)
INPUT_DIR = FLOORPLAN.output_dir
OUTPUT_DIR = INPUT_DIR / "qubo_neal"
MODEL_OUTPUT_DIR = INPUT_DIR / "qubo_model"

ROUTE_CATALOG_FILE = INPUT_DIR / "route_catalog.csv"
WEIGHTED_INCIDENCE_FILE = (
    INPUT_DIR / "occupancy_weighted_edge_route_matrix.csv"
)
EDGE_INDEX_FILE = INPUT_DIR / "edge_index.csv"

# Objective priorities. Each objective is normalized before these weights are
# applied, which keeps the QUBO coefficients in a much narrower range.
DISTANCE_WEIGHT = 1.0
CONGESTION_WEIGHT = 5.0
NORMALIZE_OBJECTIVES = True

# Remove only very small congestion interactions. Exact-one constraint
# interactions are added afterward and are never pruned.
QUADRATIC_PRUNE_THRESHOLD = 1e-4

# Prototype conversion previously selected for this project.
PEOPLE_PER_CAPACITY_UNIT = 10.0

# A tighter exact-one penalty is calculated from feasible one-route-per-room
# marginals instead of assuming every route is active simultaneously.
ASSIGNMENT_PENALTY_SAFETY_FACTOR = 1.5
ASSIGNMENT_PENALTY_MARGIN = 0.25
ASSIGNMENT_PENALTY_OVERRIDE = None

# This metric is reported separately so actual capacity exceedance is visible.
# It is not added as a hard constraint because an exact slack-variable encoding
# would greatly increase the logical-variable count, especially on the QPU.
OVERLOAD_REPORT_WEIGHT = 5.0

# Simulated annealing settings, used by the current benchmark workflow.
NUM_READS = 1000
NUM_SWEEPS = 5000
SEEDS = (42, 43, 44, 45)

TOLERANCE = 1e-9


def read_csv(path: Path) -> List[Dict[str, str]]:
    """Read a CSV into a list of dictionaries."""
    if not path.exists():
        raise FileNotFoundError(f"Required input file not found: {path}")

    with path.open("r", newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def write_csv(
    path: Path,
    fieldnames: Sequence[str],
    rows: Iterable[Mapping[str, object]],
) -> None:
    """Write dictionaries to a CSV file."""
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def variable_name(route: Mapping[str, str]) -> str:
    """Return the binary-variable name for one room-to-exit route."""
    return f"x_{route['room_id']}_{route['exit_node']}"


def add_bias(dictionary: Dict, key, value: float) -> None:
    """Add a coefficient while ignoring numerical zero."""
    if math.isclose(value, 0.0, abs_tol=TOLERANCE):
        return
    dictionary[key] = dictionary.get(key, 0.0) + float(value)


def load_problem_data():
    """Load and validate all QUBO input files."""
    routes = read_csv(ROUTE_CATALOG_FILE)
    weighted_rows = read_csv(WEIGHTED_INCIDENCE_FILE)
    edge_rows = read_csv(EDGE_INDEX_FILE)

    if not routes:
        raise ValueError("The route catalog is empty.")
    if not weighted_rows:
        raise ValueError("The occupancy-weighted incidence matrix is empty.")
    if not edge_rows:
        raise ValueError("The edge index is empty.")

    route_ids = [row["route_id"] for row in routes]
    weighted_route_ids = [row["route_id"] for row in weighted_rows]

    if route_ids != weighted_route_ids:
        raise ValueError(
            "The route order in the route catalog does not match the "
            "occupancy-weighted incidence matrix."
        )

    if len(route_ids) != len(set(route_ids)):
        raise ValueError("Duplicate route IDs were found.")

    edge_ids = [row["edge_id"] for row in edge_rows]
    if len(edge_ids) != len(set(edge_ids)):
        raise ValueError("Duplicate edge IDs were found.")

    missing_columns = [
        edge_id for edge_id in edge_ids
        if edge_id not in weighted_rows[0]
    ]
    if missing_columns:
        raise ValueError(
            "Weighted incidence matrix is missing edge columns: "
            + ", ".join(missing_columns[:10])
        )

    return routes, weighted_rows, edge_rows, edge_ids


def create_route_edge_arrays(
    routes: Sequence[Mapping[str, str]],
    weighted_rows: Sequence[Mapping[str, str]],
    edge_rows: Sequence[Mapping[str, str]],
    edge_ids: Sequence[str],
):
    """Create route-distance, occupancy, edge-load, and capacity arrays."""
    route_count = len(routes)
    edge_count = len(edge_ids)

    distances = np.array(
        [float(route["distance"]) for route in routes],
        dtype=float,
    )
    occupancies = np.array(
        [float(route["occupancy"]) for route in routes],
        dtype=float,
    )

    # W[i, k] is the number of people placed on edge k when route i is chosen.
    weighted_incidence = np.zeros((route_count, edge_count), dtype=float)

    for i, row in enumerate(weighted_rows):
        for k, edge_id in enumerate(edge_ids):
            weighted_incidence[i, k] = float(row[edge_id])

    capacity_by_edge = {
        row["edge_id"]:
        float(row["capacity_units"]) * PEOPLE_PER_CAPACITY_UNIT
        for row in edge_rows
    }
    capacities = np.array(
        [capacity_by_edge[edge_id] for edge_id in edge_ids],
        dtype=float,
    )

    if np.any(capacities <= 0):
        bad_edges = [
            edge_ids[k] for k, value in enumerate(capacities)
            if value <= 0
        ]
        raise ValueError(
            "All effective edge capacities must be positive. Bad edges: "
            + ", ".join(bad_edges)
        )

    normalized_load = weighted_incidence / capacities

    return distances, occupancies, weighted_incidence, capacities, normalized_load


def compute_objective_scales(
    routes: Sequence[Mapping[str, str]],
    distances: np.ndarray,
    normalized_load: np.ndarray,
) -> Dict[str, float]:
    """Return feasible upper-bound scales for distance and congestion.

    The scales assume one route is selected per room. Normalizing with these
    bounds prevents the assignment penalty from overwhelming the route-quality
    coefficients after QPU auto-scaling.
    """
    room_indices: Dict[str, List[int]] = defaultdict(list)
    for index, route in enumerate(routes):
        room_indices[route["room_id"]].append(index)

    distance_scale = sum(
        max(float(distances[index]) for index in indices)
        for indices in room_indices.values()
    )

    maximum_feasible_load = np.zeros(normalized_load.shape[1], dtype=float)
    for indices in room_indices.values():
        maximum_feasible_load += np.max(normalized_load[indices, :], axis=0)

    congestion_scale = float(np.sum(maximum_feasible_load**2))

    return {
        "distance_scale": max(float(distance_scale), 1.0),
        "congestion_scale": max(congestion_scale, 1.0),
    }


def build_base_coefficients(
    routes: Sequence[Mapping[str, str]],
    distances: np.ndarray,
    normalized_load: np.ndarray,
    objective_scales: Mapping[str, float],
):
    """Construct normalized distance and squared-congestion coefficients.

    The optimized objective is

        DISTANCE_WEIGHT * distance / distance_scale
        + CONGESTION_WEIGHT * sum_k(utilization_k**2) / congestion_scale.

    Small congestion-only interactions can be pruned before the exact-one
    constraints are added, reducing QUBO density without weakening feasibility.
    """
    names = [variable_name(route) for route in routes]
    linear: Dict[str, float] = {}
    quadratic: Dict[Tuple[str, str], float] = {}

    if NORMALIZE_OBJECTIVES:
        distance_multiplier = (
            DISTANCE_WEIGHT / float(objective_scales["distance_scale"])
        )
        congestion_multiplier = (
            CONGESTION_WEIGHT / float(objective_scales["congestion_scale"])
        )
    else:
        distance_multiplier = DISTANCE_WEIGHT
        congestion_multiplier = CONGESTION_WEIGHT

    congestion_gram = congestion_multiplier * (
        normalized_load @ normalized_load.T
    )

    for i, name in enumerate(names):
        add_bias(
            linear,
            name,
            distance_multiplier * distances[i] + congestion_gram[i, i],
        )

    pruned_interaction_count = 0
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            coefficient = 2.0 * congestion_gram[i, j]
            if abs(coefficient) < QUADRATIC_PRUNE_THRESHOLD:
                if not math.isclose(coefficient, 0.0, abs_tol=TOLERANCE):
                    pruned_interaction_count += 1
                continue
            add_bias(quadratic, (names[i], names[j]), coefficient)

    return linear, quadratic, congestion_gram, pruned_interaction_count


def choose_assignment_penalty(
    routes: Sequence[Mapping[str, str]],
    names: Sequence[str],
    base_linear: Mapping[str, float],
    base_quadratic: Mapping[Tuple[str, str], float],
) -> float:
    """Choose a tight penalty for selecting exactly one route per room.

    For each route, the bound includes its linear cost plus the largest positive
    interaction it can have with one selected route from every other room. This
    is much tighter than assuming all mutually exclusive routes are active.
    """
    if ASSIGNMENT_PENALTY_OVERRIDE is not None:
        if ASSIGNMENT_PENALTY_OVERRIDE <= 0:
            raise ValueError("ASSIGNMENT_PENALTY_OVERRIDE must be positive.")
        return float(ASSIGNMENT_PENALTY_OVERRIDE)

    room_by_name = {
        variable_name(route): route["room_id"] for route in routes
    }
    variables_by_room: Dict[str, List[str]] = defaultdict(list)
    for name in names:
        variables_by_room[room_by_name[name]].append(name)

    def interaction(u: str, v: str) -> float:
        return float(
            base_quadratic.get(
                (u, v),
                base_quadratic.get((v, u), 0.0),
            )
        )

    feasible_marginals = []
    for name in names:
        room_id = room_by_name[name]
        marginal = float(base_linear.get(name, 0.0))

        for other_room, other_variables in variables_by_room.items():
            if other_room == room_id:
                continue
            marginal += max(
                [max(0.0, interaction(name, other))
                 for other in other_variables],
                default=0.0,
            )

        feasible_marginals.append(marginal)

    worst_feasible_marginal = max(feasible_marginals, default=1.0)
    return ASSIGNMENT_PENALTY_SAFETY_FACTOR * (
        worst_feasible_marginal + ASSIGNMENT_PENALTY_MARGIN
    )


def add_exact_one_constraints(
    routes: Sequence[Mapping[str, str]],
    assignment_penalty: float,
    linear: Dict[str, float],
    quadratic: Dict[Tuple[str, str], float],
) -> Tuple[float, Dict[str, List[str]]]:
    """Add A(1 - sum_e x_room,e)^2 for every room."""
    room_variables: Dict[str, List[str]] = defaultdict(list)

    for route in routes:
        room_variables[route["room_id"]].append(variable_name(route))

    offset = 0.0

    for room_id, variables in room_variables.items():
        if not variables:
            raise ValueError(f"Room {room_id} has no candidate routes.")

        offset += assignment_penalty

        # Since x^2 = x for binary variables:
        # A(1-sum x)^2 = A - A sum x + 2A sum_(i<j) x_i*x_j
        for name in variables:
            add_bias(linear, name, -assignment_penalty)

        for i in range(len(variables)):
            for j in range(i + 1, len(variables)):
                pair = (variables[i], variables[j])
                add_bias(quadratic, pair, 2.0 * assignment_penalty)

    return offset, dict(room_variables)


def create_bqm(
    linear: Mapping[str, float],
    quadratic: Mapping[Tuple[str, str], float],
    offset: float,
):
    """Create the BinaryQuadraticModel in the current Ocean BQM style."""
    bqm = dimod.BinaryQuadraticModel("BINARY")

    for variable, coefficient in linear.items():
        bqm.add_linear(variable, coefficient)

    for (variable_u, variable_v), coefficient in quadratic.items():
        bqm.add_quadratic(variable_u, variable_v, coefficient)

    bqm.offset = float(offset)
    return bqm


def export_bqm_csvs(
    bqm,
    routes: Sequence[Mapping[str, str]],
    distances: np.ndarray,
    congestion_gram: np.ndarray,
) -> None:
    """Export variable metadata and all useful QUBO CSV representations."""
    names = [variable_name(route) for route in routes]
    index_by_name = {name: i for i, name in enumerate(names)}

    variable_rows = []
    for i, route in enumerate(routes):
        variable_rows.append(
            {
                "variable_index": i,
                "variable_name": names[i],
                "route_id": route["route_id"],
                "room_id": route["room_id"],
                "room_name": route["room_name"],
                "start_node": route["start_node"],
                "exit_node": route["exit_node"],
                "occupancy": route["occupancy"],
                "distance": distances[i],
                "self_congestion_cost": congestion_gram[i, i],
                "bqm_linear_bias": bqm.linear[names[i]],
            }
        )

    write_csv(
        MODEL_OUTPUT_DIR / "qubo_variable_index.csv",
        [
            "variable_index", "variable_name", "route_id", "room_id",
            "room_name", "start_node", "exit_node", "occupancy",
            "distance", "self_congestion_cost", "bqm_linear_bias",
        ],
        variable_rows,
    )

    linear_rows = [
        {
            "variable_index": index_by_name[name],
            "variable": name,
            "coefficient": float(bqm.linear[name]),
        }
        for name in names
    ]
    write_csv(
        MODEL_OUTPUT_DIR / "qubo_linear_coefficients.csv",
        ["variable_index", "variable", "coefficient"],
        linear_rows,
    )

    quadratic_rows = []
    for (u, v), coefficient in bqm.quadratic.items():
        i = index_by_name[u]
        j = index_by_name[v]
        if i > j:
            i, j = j, i
            u, v = v, u

        quadratic_rows.append(
            {
                "i": i,
                "j": j,
                "variable_i": u,
                "variable_j": v,
                "coefficient": float(coefficient),
            }
        )

    quadratic_rows.sort(key=lambda row: (row["i"], row["j"]))
    write_csv(
        MODEL_OUTPUT_DIR / "qubo_quadratic_coefficients.csv",
        ["i", "j", "variable_i", "variable_j", "coefficient"],
        quadratic_rows,
    )

    # Upper-triangular polynomial representation:
    # E = offset + sum_i Qii*x_i + sum_(i<j) Qij*x_i*x_j
    upper_rows = []
    for i, name in enumerate(names):
        upper_rows.append(
            {
                "i": i,
                "j": i,
                "variable_i": name,
                "variable_j": name,
                "coefficient": float(bqm.linear[name]),
            }
        )

    upper_rows.extend(quadratic_rows)
    upper_rows.sort(key=lambda row: (row["i"], row["j"]))

    write_csv(
        MODEL_OUTPUT_DIR / "qubo_upper_triangular.csv",
        ["i", "j", "variable_i", "variable_j", "coefficient"],
        upper_rows,
    )

    # Symmetric dense matrix for literal E = offset + x^T Q x.
    dense = np.zeros((len(names), len(names)), dtype=float)

    for i, name in enumerate(names):
        dense[i, i] = float(bqm.linear[name])

    for (u, v), coefficient in bqm.quadratic.items():
        i = index_by_name[u]
        j = index_by_name[v]
        dense[i, j] = float(coefficient) / 2.0
        dense[j, i] = float(coefficient) / 2.0

    dense_path = MODEL_OUTPUT_DIR / "qubo_dense_xtqx.csv"
    with dense_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["variable"] + names)
        for i, name in enumerate(names):
            writer.writerow([name] + [float(value) for value in dense[i]])


def solve_with_neal(bqm):
    """Run multiple deterministic simulated-annealing seed batches."""
    sampler = neal.SimulatedAnnealingSampler()
    seeds = tuple(int(seed) for seed in SEEDS)
    if not seeds:
        raise ValueError("SEEDS must contain at least one integer.")

    reads_per_seed = max(1, math.ceil(NUM_READS / len(seeds)))
    sample_sets = [
        sampler.sample(
            bqm,
            num_reads=reads_per_seed,
            num_sweeps=NUM_SWEEPS,
            seed=seed,
        )
        for seed in seeds
    ]

    sampleset = dimod.concatenate(sample_sets).aggregate()
    return sampleset, reads_per_seed


def export_samples(sampleset, room_variables) -> None:
    """Export samples with exact-one feasibility information."""
    sample_rows = []
    fields = ["sample", "energy", "num_occurrences"]
    has_chain_break = "chain_break_fraction" in sampleset.record.dtype.names
    if has_chain_break:
        fields.append("chain_break_fraction")

    for rank, datum in enumerate(
        sampleset.data(fields=fields, sorted_by="energy"),
        start=1,
    ):
        selected_variables = sorted(
            variable for variable, value in datum.sample.items()
            if int(value) == 1
        )
        valid, violations = exact_one_status(datum.sample, room_variables)
        row = {
            "rank": rank,
            "energy": float(datum.energy),
            "num_occurrences": int(getattr(datum, "num_occurrences", 1)),
            "valid_exactly_one_exit_per_room": valid,
            "constraint_violation_count": len(violations),
            "selected_variable_count": len(selected_variables),
            "selected_variables": " | ".join(selected_variables),
        }
        if has_chain_break:
            row["chain_break_fraction"] = float(
                getattr(datum, "chain_break_fraction", 0.0)
            )
        sample_rows.append(row)

    fieldnames = [
        "rank", "energy", "num_occurrences",
        "valid_exactly_one_exit_per_room",
        "constraint_violation_count",
    ]
    if has_chain_break:
        fieldnames.append("chain_break_fraction")
    fieldnames.extend(["selected_variable_count", "selected_variables"])

    write_csv(OUTPUT_DIR / "neal_samples.csv", fieldnames, sample_rows)


def exact_one_status(
    sample: Mapping[str, int],
    room_variables: Mapping[str, Sequence[str]],
):
    """Return whether a sample selects exactly one route for every room."""
    violations = []
    for room_id, variables in room_variables.items():
        selected = [name for name in variables if int(sample.get(name, 0)) == 1]
        if len(selected) != 1:
            violations.append(
                {
                    "room_id": room_id,
                    "selected_route_count": len(selected),
                    "selected_routes": " | ".join(selected),
                }
            )
    return not violations, violations


def select_best_valid_sample(sampleset, room_variables):
    """Select the lowest-energy valid sample and report sample feasibility."""
    fields = ["sample", "energy", "num_occurrences"]
    if "chain_break_fraction" in sampleset.record.dtype.names:
        fields.append("chain_break_fraction")

    total_occurrences = 0
    valid_occurrences = 0
    valid_unique_samples = 0
    best_valid = None

    for datum in sampleset.data(fields=fields, sorted_by="energy"):
        occurrences = int(getattr(datum, "num_occurrences", 1))
        total_occurrences += occurrences
        valid, _ = exact_one_status(datum.sample, room_variables)
        if valid:
            valid_occurrences += occurrences
            valid_unique_samples += 1
            if best_valid is None:
                best_valid = datum

    chosen = best_valid if best_valid is not None else sampleset.first
    chosen_valid, _ = exact_one_status(chosen.sample, room_variables)

    stats = {
        "total_sample_occurrences": total_occurrences,
        "valid_sample_occurrences": valid_occurrences,
        "valid_unique_samples": valid_unique_samples,
        "valid_sample_rate": (
            valid_occurrences / total_occurrences if total_occurrences else 0.0
        ),
        "selected_best_is_valid": chosen_valid,
        "fell_back_to_unconstrained_best": best_valid is None,
    }
    return chosen, stats


def decode_best_solution(
    best_sample: Mapping[str, int],
    routes: Sequence[Mapping[str, str]],
):
    """Decode active route variables into room-to-exit assignments."""
    route_by_variable = {
        variable_name(route): route for route in routes
    }

    selected = []
    by_room: Dict[str, List[Mapping[str, str]]] = defaultdict(list)

    for name, value in best_sample.items():
        if int(value) != 1:
            continue

        route = route_by_variable[name]
        selected.append(route)
        by_room[route["room_id"]].append(route)

    all_rooms = sorted({route["room_id"] for route in routes})
    violations = []

    for room_id in all_rooms:
        count = len(by_room.get(room_id, []))
        if count != 1:
            violations.append(
                {
                    "room_id": room_id,
                    "selected_route_count": count,
                    "selected_routes": " | ".join(
                        route["route_id"]
                        for route in by_room.get(room_id, [])
                    ),
                }
            )

    selected.sort(key=lambda route: route["room_id"])
    return selected, violations


def calculate_reports(
    selected_routes: Sequence[Mapping[str, str]],
    weighted_rows: Sequence[Mapping[str, str]],
    edge_rows: Sequence[Mapping[str, str]],
    edge_ids: Sequence[str],
):
    """Calculate raw distance, congestion, overload, and exit usage."""
    weighted_by_route = {
        row["route_id"]: row for row in weighted_rows
    }
    edge_row_by_id = {
        row["edge_id"]: row for row in edge_rows
    }

    total_distance = sum(
        float(route["distance"]) for route in selected_routes
    )
    total_people = sum(
        int(float(route["occupancy"])) for route in selected_routes
    )

    edge_load = {edge_id: 0.0 for edge_id in edge_ids}
    for route in selected_routes:
        row = weighted_by_route[route["route_id"]]
        for edge_id in edge_ids:
            edge_load[edge_id] += float(row[edge_id])

    edge_report = []
    congestion_objective = 0.0
    overload_objective = 0.0

    for edge_id in edge_ids:
        edge = edge_row_by_id[edge_id]
        capacity_people = (
            float(edge["capacity_units"]) * PEOPLE_PER_CAPACITY_UNIT
        )
        load_people = edge_load[edge_id]
        utilization = (
            load_people / capacity_people
            if capacity_people > 0 else math.inf
        )
        congestion_cost = CONGESTION_WEIGHT * utilization**2
        overload_ratio = max(0.0, utilization - 1.0)
        overload_cost = OVERLOAD_REPORT_WEIGHT * overload_ratio**2
        congestion_objective += congestion_cost
        overload_objective += overload_cost

        edge_report.append(
            {
                "edge_id": edge_id,
                "source": edge["source"],
                "target": edge["target"],
                "edge_type": edge["edge_type"],
                "distance": float(edge["distance"]),
                "capacity_units": float(edge["capacity_units"]),
                "effective_capacity_people": capacity_people,
                "selected_load_people": load_people,
                "utilization": utilization,
                "utilization_percent": 100.0 * utilization,
                "over_capacity": load_people > capacity_people + TOLERANCE,
                "overload_ratio": overload_ratio,
                "congestion_cost": congestion_cost,
                "overload_cost": overload_cost,
            }
        )

    edge_report.sort(
        key=lambda row: (-float(row["utilization"]), row["edge_id"])
    )

    exit_accumulator = defaultdict(
        lambda: {
            "assigned_room_count": 0,
            "assigned_people": 0,
            "room_ids": [],
            "route_ids": [],
            "total_route_distance": 0.0,
        }
    )

    for route in selected_routes:
        exit_node = route["exit_node"]
        item = exit_accumulator[exit_node]
        item["assigned_room_count"] += 1
        item["assigned_people"] += int(float(route["occupancy"]))
        item["room_ids"].append(route["room_id"])
        item["route_ids"].append(route["route_id"])
        item["total_route_distance"] += float(route["distance"])

    return (
        total_distance,
        total_people,
        congestion_objective,
        overload_objective,
        edge_report,
        exit_accumulator,
    )


def build_exit_report(
    routes: Sequence[Mapping[str, str]],
    exit_accumulator,
):
    """Include both used and unused exits in the final exit report."""
    all_exits = sorted({route["exit_node"] for route in routes})
    report = []

    for exit_node in all_exits:
        item = exit_accumulator.get(
            exit_node,
            {
                "assigned_room_count": 0,
                "assigned_people": 0,
                "room_ids": [],
                "route_ids": [],
                "total_route_distance": 0.0,
            },
        )

        room_count = int(item["assigned_room_count"])
        report.append(
            {
                "exit_node": exit_node,
                "assigned_room_count": room_count,
                "assigned_people": int(item["assigned_people"]),
                "room_ids": " | ".join(sorted(item["room_ids"])),
                "route_ids": " | ".join(sorted(item["route_ids"])),
                "total_route_distance": float(
                    item["total_route_distance"]
                ),
                "average_route_distance": (
                    float(item["total_route_distance"]) / room_count
                    if room_count else 0.0
                ),
            }
        )

    return report


def write_solution_outputs(
    bqm,
    sampleset,
    routes,
    selected_routes,
    violations,
    total_distance,
    total_people,
    congestion_objective,
    overload_objective,
    edge_report,
    exit_report,
    assignment_penalty,
    objective_scales,
    pruned_interaction_count,
    best,
    sample_stats,
    reads_per_seed,
):
    """Write decoded assignments and multi-seed annealing metrics."""
    assignment_rows = [
        {
            "room_id": route["room_id"],
            "room_name": route["room_name"],
            "occupancy": int(float(route["occupancy"])),
            "selected_exit": route["exit_node"],
            "route_id": route["route_id"],
            "distance": float(route["distance"]),
            "edge_count": int(float(route["edge_count"])),
            "path": route["path"],
            "edge_ids": route["edge_ids"],
        }
        for route in selected_routes
    ]

    write_csv(
        OUTPUT_DIR / "selected_assignments.csv",
        [
            "room_id", "room_name", "occupancy", "selected_exit",
            "route_id", "distance", "edge_count", "path", "edge_ids",
        ],
        assignment_rows,
    )

    write_csv(
        OUTPUT_DIR / "edge_congestion_report.csv",
        [
            "edge_id", "source", "target", "edge_type", "distance",
            "capacity_units", "effective_capacity_people",
            "selected_load_people", "utilization", "utilization_percent",
            "over_capacity", "overload_ratio", "congestion_cost",
            "overload_cost",
        ],
        edge_report,
    )

    write_csv(
        OUTPUT_DIR / "exit_usage_report.csv",
        [
            "exit_node", "assigned_room_count", "assigned_people",
            "room_ids", "route_ids", "total_route_distance",
            "average_route_distance",
        ],
        exit_report,
    )

    overloaded_edges = [row for row in edge_report if bool(row["over_capacity"])]
    used_edges = [
        row for row in edge_report if float(row["selected_load_people"]) > 0
    ]

    direct_bqm_energy = float(bqm.energy(best.sample))
    if NORMALIZE_OBJECTIVES:
        normalized_distance_component = (
            DISTANCE_WEIGHT * total_distance / objective_scales["distance_scale"]
        )
        normalized_congestion_component = (
            congestion_objective / objective_scales["congestion_scale"]
        )
    else:
        normalized_distance_component = DISTANCE_WEIGHT * total_distance
        normalized_congestion_component = congestion_objective

    normalized_objective_without_penalty = (
        normalized_distance_component + normalized_congestion_component
    )

    summary = {
        "solver": "neal.SimulatedAnnealingSampler",
        "formulation_version": "normalized_tight_penalty_v2",
        "requested_total_reads": NUM_READS,
        "reads_per_seed": reads_per_seed,
        "num_sweeps": NUM_SWEEPS,
        "seeds": list(SEEDS),
        "variable_count": bqm.num_variables,
        "interaction_count": bqm.num_interactions,
        "pruned_congestion_interaction_count": pruned_interaction_count,
        "best_energy": float(best.energy),
        "recalculated_bqm_energy": direct_bqm_energy,
        "best_num_occurrences": int(getattr(best, "num_occurrences", 1)),
        **sample_stats,
        "valid_exactly_one_exit_per_room": not violations,
        "constraint_violations": violations,
        "selected_route_count": len(selected_routes),
        "total_evacuated_people": total_people,
        "total_evacuation_distance": total_distance,
        "edge_congestion_objective": congestion_objective,
        "overload_only_report_objective": overload_objective,
        "normalized_distance_component": normalized_distance_component,
        "normalized_congestion_component": normalized_congestion_component,
        "normalized_objective_without_penalty": normalized_objective_without_penalty,
        "distance_normalization_scale": objective_scales["distance_scale"],
        "congestion_normalization_scale": objective_scales["congestion_scale"],
        "used_edge_count": len(used_edges),
        "overloaded_edge_count": len(overloaded_edges),
        "maximum_edge_utilization": max(
            (float(row["utilization"]) for row in edge_report), default=0.0
        ),
        "assignment_penalty": assignment_penalty,
        "assignment_penalty_safety_factor": ASSIGNMENT_PENALTY_SAFETY_FACTOR,
        "distance_weight": DISTANCE_WEIGHT,
        "congestion_weight": CONGESTION_WEIGHT,
        "people_per_capacity_unit": PEOPLE_PER_CAPACITY_UNIT,
        "bqm_offset": float(bqm.offset),
    }
    solver_text = "Solver: neal.SimulatedAnnealingSampler (multiple seeds)"

    summary_path = OUTPUT_DIR / "solution_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    lines = [
        "OFFICE EVACUATION QUBO RESULT",
        "=" * 36,
        solver_text,
        f"Variables: {bqm.num_variables}",
        f"Interactions: {bqm.num_interactions}",
        f"Best valid energy: {float(best.energy):.6f}",
        f"Valid one-exit-per-room solution: {not violations}",
        f"Valid sample rate: {100.0 * sample_stats['valid_sample_rate']:.2f}%",
        f"Assignment penalty: {assignment_penalty:.6f}",
        f"Normalized route objective: {normalized_objective_without_penalty:.6f}",
        f"Total evacuated people: {total_people}",
        f"Total evacuation distance: {total_distance:.6f}",
        f"Raw congestion objective: {congestion_objective:.6f}",
        f"Overload-only report objective: {overload_objective:.6f}",
        f"Used physical edges: {len(used_edges)}",
        f"Overloaded physical edges: {len(overloaded_edges)}",
        (
            "Maximum edge utilization: "
            f"{100.0 * summary['maximum_edge_utilization']:.2f}%"
        ),
        "",
        "ROOM ASSIGNMENTS",
        "-" * 36,
    ]

    for route in selected_routes:
        lines.append(
            f"{route['room_id']} ({route['occupancy']} people) -> "
            f"{route['exit_node']} | distance={float(route['distance']):.3f}"
        )

    lines.extend(["", "EXIT USAGE", "-" * 36])
    for row in exit_report:
        lines.append(
            f"{row['exit_node']}: {row['assigned_room_count']} rooms, "
            f"{row['assigned_people']} people"
        )

    lines.extend(["", "MOST UTILIZED EDGES", "-" * 36])
    for row in edge_report[:10]:
        lines.append(
            f"{row['edge_id']}: {row['selected_load_people']:.0f}/"
            f"{row['effective_capacity_people']:.0f} people "
            f"({row['utilization_percent']:.2f}%)"
        )

    if violations:
        lines.extend(["", "CONSTRAINT VIOLATIONS", "-" * 36])
        for violation in violations:
            lines.append(
                f"{violation['room_id']}: "
                f"{violation['selected_route_count']} routes selected"
            )

    (OUTPUT_DIR / "solution_summary.txt").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    routes, weighted_rows, edge_rows, edge_ids = load_problem_data()

    (
        distances,
        occupancies,
        weighted_incidence,
        capacities,
        normalized_load,
    ) = create_route_edge_arrays(
        routes,
        weighted_rows,
        edge_rows,
        edge_ids,
    )

    objective_scales = compute_objective_scales(
        routes,
        distances,
        normalized_load,
    )

    (
        base_linear,
        base_quadratic,
        congestion_gram,
        pruned_interaction_count,
    ) = build_base_coefficients(
        routes,
        distances,
        normalized_load,
        objective_scales,
    )

    names = [variable_name(route) for route in routes]
    assignment_penalty = choose_assignment_penalty(
        routes,
        names,
        base_linear,
        base_quadratic,
    )

    # Copy the dictionaries because the constraint function mutates them.
    linear = dict(base_linear)
    quadratic = dict(base_quadratic)

    offset, room_variables = add_exact_one_constraints(
        routes,
        assignment_penalty,
        linear,
        quadratic,
    )

    bqm = create_bqm(linear, quadratic, offset)

    export_bqm_csvs(
        bqm,
        routes,
        distances,
        congestion_gram,
    )

    sampleset, reads_per_seed = solve_with_neal(bqm)
    export_samples(sampleset, room_variables)
    best, sample_stats = select_best_valid_sample(sampleset, room_variables)

    selected_routes, violations = decode_best_solution(best.sample, routes)

    (
        total_distance,
        total_people,
        congestion_objective,
        overload_objective,
        edge_report,
        exit_accumulator,
    ) = calculate_reports(
        selected_routes,
        weighted_rows,
        edge_rows,
        edge_ids,
    )

    exit_report = build_exit_report(routes, exit_accumulator)

    summary = write_solution_outputs(
        bqm,
        sampleset,
        routes,
        selected_routes,
        violations,
        total_distance,
        total_people,
        congestion_objective,
        overload_objective,
        edge_report,
        exit_report,
        assignment_penalty,
        objective_scales,
        pruned_interaction_count,
        best,
        sample_stats,
        reads_per_seed,
    )

    print("\nOFFICE EVACUATION QUBO COMPLETE")
    print("=" * 40)
    print(f"BQM variables:          {bqm.num_variables}")
    print(f"BQM interactions:       {bqm.num_interactions}")
    print(f"Assignment penalty:     {assignment_penalty:.6f}")
    print(f"Best valid energy:      {float(best.energy):.6f}")
    print(
        "Valid one-exit solution: "
        f"{summary['valid_exactly_one_exit_per_room']}"
    )
    print(f"Total route distance:   {total_distance:.6f}")
    print(f"Congestion objective:   {congestion_objective:.6f}")
    print(f"Valid sample rate:      {100.0 * sample_stats['valid_sample_rate']:.2f}%")
    print(f"Overloaded edges:       {summary['overloaded_edge_count']}")
    print(f"Output directory:       {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
