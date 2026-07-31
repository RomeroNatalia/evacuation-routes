"""Build and solve the floorplan evacuation QUBO with D-Wave Ocean.

This version does all of the following:

1. Reads the route, occupancy-weighted incidence, and edge-index CSV files.
2. Builds a dimod.BinaryQuadraticModel directly.
3. Exports the QUBO coefficients and dense matrix to CSV.
4. Sweeps several exactly-one assignment penalties with D-Wave LeapHybridSampler.
5. Repeats each penalty across independent Hybrid jobs while holding other settings fixed.
6. Reports validity, energy, route distance, congestion, overload, and timing.

Install dependencies:

    python -m pip install --upgrade dwave-ocean-sdk numpy

Run from the repository root:

    python scripts/sweep/sweep_assignment_penalty_hybrid.py

Expected inputs:

    data/floorplans/FPXX/output/route_catalog.csv
    data/floorplans/FPXX/output/occupancy_weighted_edge_route_matrix.csv
    data/floorplans/FPXX/output/edge_index.csv

Generated outputs:

    data/floorplans/FPXX/output/qubo_hybrid_penalty_sweep/qubo_variable_index.csv
    data/floorplans/FPXX/output/qubo_hybrid_penalty_sweep/qubo_linear_coefficients.csv
    data/floorplans/FPXX/output/qubo_hybrid_penalty_sweep/qubo_quadratic_coefficients.csv
    data/floorplans/FPXX/output/qubo_hybrid_penalty_sweep/qubo_upper_triangular.csv
    data/floorplans/FPXX/output/qubo_hybrid_penalty_sweep/qubo_dense_xtqx.csv
    data/floorplans/FPXX/output/qubo_hybrid_penalty_sweep/hybrid_samples.csv
    data/floorplans/FPXX/output/qubo_hybrid_penalty_sweep/selected_assignments.csv
    data/floorplans/FPXX/output/qubo_hybrid_penalty_sweep/edge_congestion_report.csv
    data/floorplans/FPXX/output/qubo_hybrid_penalty_sweep/exit_usage_report.csv
    data/floorplans/FPXX/output/qubo_hybrid_penalty_sweep/solution_summary.json
    data/floorplans/FPXX/output/qubo_hybrid_penalty_sweep/solution_summary.txt
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import csv
import json
import math
import sys
import time
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple
import numpy as np

try:
    import dimod
    from dwave.system import LeapHybridSampler
except ImportError as exc:
    raise SystemExit(
        "\nMissing D-Wave Ocean packages.\n"
        "Install them with:\n\n"
        "    python -m pip install --upgrade dwave-ocean-sdk numpy\n"
    ) from exc


def find_project_root() -> Path:
    """Locate the repository root even if this script is inside scripts/sweep/."""
    start = Path(__file__).resolve().parent

    for candidate in (start, *start.parents):
        floorplans_dir = candidate / "data" / "floorplans"
        scripts_dir = candidate / "scripts"

        if floorplans_dir.exists() and scripts_dir.exists():
            return candidate

    raise FileNotFoundError(
        "Could not locate the project root. Expected to find a directory "
        "containing both 'scripts/' and 'data/floorplans/'."
    )


ROOT = find_project_root()
sys.path.insert(0, str(ROOT / "src"))
from fire_evacuation.project import floorplan_paths_from_argv  # noqa: E402

FLOORPLAN = floorplan_paths_from_argv(ROOT)
INPUT_DIR = FLOORPLAN.output_dir
OUTPUT_DIR = INPUT_DIR / "qubo_hybrid_penalty_sweep"

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

# D-Wave Leap hybrid job label.
HYBRID_LABEL = f"{FLOORPLAN.floorplan_id} Fire Evacuation QUBO - Hybrid"

# Controlled assignment-penalty experiment.
# None means "use the automatically calculated penalty" as the baseline.
# Every other solver/QUBO setting is intentionally held fixed during the sweep.
PENALTY_SWEEP_VALUES = (None, 2.5, 3.0, 4.0, 5.0)
DEFAULT_RUNS_PER_PENALTY = 5

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
        OUTPUT_DIR / "qubo_variable_index.csv",
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
        OUTPUT_DIR / "qubo_linear_coefficients.csv",
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
        OUTPUT_DIR / "qubo_quadratic_coefficients.csv",
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
        OUTPUT_DIR / "qubo_upper_triangular.csv",
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

    dense_path = OUTPUT_DIR / "qubo_dense_xtqx.csv"
    with dense_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["variable"] + names)
        for i, name in enumerate(names):
            writer.writerow([name] + [float(value) for value in dense[i]])


def solve_with_hybrid(bqm, run_number: int = 1, sampler=None, penalty_label: str = ""):
    """Submit one independent normalized BQM trial to LeapHybridSampler."""
    if sampler is None:
        sampler = LeapHybridSampler()
    label = f"{HYBRID_LABEL} - {penalty_label} - Run {run_number}"
    return sampler.sample(bqm, label=label)


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

    write_csv(OUTPUT_DIR / "hybrid_samples.csv", fieldnames, sample_rows)


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
):
    """Write decoded assignments and normalized hybrid-solver metrics."""
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
        "solver": "dwave.system.LeapHybridSampler",
        "formulation_version": "normalized_tight_penalty_v2",
        "hybrid_label": HYBRID_LABEL,
        "problem_id": sampleset.info.get("problem_id"),
        "remote_solver_name": sampleset.info.get("solver_name"),
        "timing": dict(sampleset.info.get("timing", {})),
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
    solver_text = "Solver: D-Wave LeapHybridSampler"

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


def evaluate_run_result(
    sampleset,
    room_variables,
    routes,
    weighted_rows,
    edge_rows,
    edge_ids,
):
    """Decode one solver run and return all metrics needed for benchmarking."""
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
    used_edges = [
        row for row in edge_report
        if float(row["selected_load_people"]) > TOLERANCE
    ]
    overloaded_edges = [
        row for row in edge_report
        if bool(row["over_capacity"])
    ]
    maximum_edge_utilization = max(
        (float(row["utilization"]) for row in edge_report),
        default=0.0,
    )

    return {
        "best": best,
        "sample_stats": sample_stats,
        "selected_routes": selected_routes,
        "violations": violations,
        "total_distance": float(total_distance),
        "total_people": int(total_people),
        "congestion_objective": float(congestion_objective),
        "overload_objective": float(overload_objective),
        "edge_report": edge_report,
        "exit_report": exit_report,
        "used_edge_count": len(used_edges),
        "overloaded_edge_count": len(overloaded_edges),
        "maximum_edge_utilization": maximum_edge_utilization,
        "valid": not violations,
    }


def write_benchmark_outputs(solver_name: str, run_rows: Sequence[Mapping[str, object]]) -> None:
    """Write per-run metrics plus aggregate statistics for repeated solver runs."""
    if not run_rows:
        raise ValueError("No benchmark runs were recorded.")

    run_fieldnames = list(run_rows[0].keys())
    write_csv(
        OUTPUT_DIR / "benchmark_runs.csv",
        run_fieldnames,
        run_rows,
    )

    numeric_metrics = [
        "best_energy",
        "total_distance",
        "congestion_objective",
        "overload_objective",
        "used_edge_count",
        "overloaded_edge_count",
        "maximum_edge_utilization",
        "valid_sample_rate",
        "solver_wall_clock_seconds",
    ]

    summary = {
        "solver": solver_name,
        "run_count": len(run_rows),
        "valid_best_run_count": sum(bool(row["valid_best_solution"]) for row in run_rows),
        "valid_best_run_rate": (
            sum(bool(row["valid_best_solution"]) for row in run_rows) / len(run_rows)
        ),
    }

    valid_energy_rows = [
        row for row in run_rows if bool(row["valid_best_solution"])
    ]
    energy_pool = valid_energy_rows if valid_energy_rows else list(run_rows)
    best_row = min(energy_pool, key=lambda row: float(row["best_energy"]))
    summary["best_run_number"] = int(best_row["run"])
    summary["best_energy"] = float(best_row["best_energy"])

    for metric in numeric_metrics:
        values = np.asarray(
            [float(row[metric]) for row in run_rows],
            dtype=float,
        )
        summary[f"{metric}_mean"] = float(np.mean(values))
        summary[f"{metric}_median"] = float(np.median(values))
        summary[f"{metric}_std"] = float(np.std(values))
        summary[f"{metric}_min"] = float(np.min(values))
        summary[f"{metric}_max"] = float(np.max(values))

    write_csv(
        OUTPUT_DIR / "benchmark_summary.csv",
        list(summary.keys()),
        [summary],
    )


def parse_runs_per_penalty() -> int:
    """Read an optional positive number of independent runs per penalty."""
    if len(sys.argv) == 1:
        return DEFAULT_RUNS_PER_PENALTY

    if len(sys.argv) != 2:
        raise SystemExit(
            f"Usage: python {Path(sys.argv[0]).name} [runs_per_penalty]"
        )

    try:
        run_count = int(sys.argv[1])
    except ValueError as exc:
        raise SystemExit("runs_per_penalty must be a positive integer.") from exc

    if run_count <= 0:
        raise SystemExit("runs_per_penalty must be a positive integer.")

    return run_count


def write_penalty_sweep_outputs(
    run_rows: Sequence[Mapping[str, object]],
) -> None:
    """Write one row per Hybrid job plus one aggregate row per penalty."""
    if not run_rows:
        raise ValueError("No Hybrid penalty-sweep runs were recorded.")

    write_csv(
        OUTPUT_DIR / "hybrid_penalty_sweep_runs.csv",
        list(run_rows[0].keys()),
        run_rows,
    )

    rows_by_penalty: Dict[float, List[Mapping[str, object]]] = defaultdict(list)
    for row in run_rows:
        rows_by_penalty[float(row["assignment_penalty"])].append(row)

    numeric_metrics = [
        "best_energy",
        "valid_sample_rate",
        "total_distance",
        "congestion_objective",
        "overload_objective",
        "used_edge_count",
        "overloaded_edge_count",
        "maximum_edge_utilization",
        "solver_wall_clock_seconds",
    ]

    summary_rows = []

    for penalty in sorted(rows_by_penalty):
        rows = rows_by_penalty[penalty]
        valid_rows = [row for row in rows if bool(row["valid_best_solution"])]
        energy_pool = valid_rows if valid_rows else rows
        best_row = min(energy_pool, key=lambda row: float(row["best_energy"]))

        summary = {
            "solver": "dwave.system.LeapHybridSampler",
            "assignment_penalty": penalty,
            "penalty_source": best_row["penalty_source"],
            "run_count": len(rows),
            "valid_best_run_count": len(valid_rows),
            "valid_best_run_rate": len(valid_rows) / len(rows),
            "best_run": int(best_row["run"]),
            "best_energy": float(best_row["best_energy"]),
            "best_valid_sample_rate": float(best_row["valid_sample_rate"]),
            "best_total_distance": float(best_row["total_distance"]),
            "best_congestion_objective": float(best_row["congestion_objective"]),
            "best_overloaded_edge_count": int(best_row["overloaded_edge_count"]),
            "best_maximum_edge_utilization": float(
                best_row["maximum_edge_utilization"]
            ),
        }

        for metric in numeric_metrics:
            values = np.asarray([float(row[metric]) for row in rows], dtype=float)
            summary[f"{metric}_mean"] = float(np.mean(values))
            summary[f"{metric}_median"] = float(np.median(values))
            summary[f"{metric}_std"] = float(np.std(values))
            summary[f"{metric}_min"] = float(np.min(values))
            summary[f"{metric}_max"] = float(np.max(values))

        summary_rows.append(summary)

    write_csv(
        OUTPUT_DIR / "hybrid_penalty_sweep_summary.csv",
        list(summary_rows[0].keys()),
        summary_rows,
    )


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    runs_per_penalty = parse_runs_per_penalty()

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
    automatic_penalty = choose_assignment_penalty(
        routes,
        names,
        base_linear,
        base_quadratic,
    )

    penalty_cases = []
    seen_penalties = set()
    for configured_value in PENALTY_SWEEP_VALUES:
        if configured_value is None:
            penalty = float(automatic_penalty)
            source = "automatic_baseline"
        else:
            penalty = float(configured_value)
            source = "manual_test"

        rounded = round(penalty, 12)
        if rounded in seen_penalties:
            continue
        seen_penalties.add(rounded)
        penalty_cases.append((penalty, source))

    print("\nLEAP-HYBRID ASSIGNMENT-PENALTY SWEEP")
    print("=" * 52)
    print(f"Automatic baseline penalty: {automatic_penalty:.6f}")
    print(
        "Penalties to test: "
        + ", ".join(f"{penalty:.6f}" for penalty, _ in penalty_cases)
    )
    print(f"Independent jobs per penalty: {runs_per_penalty}")
    print(
        "Held fixed: normalization, objective weights, pruning, and "
        "the same Leap Hybrid solver configuration."
    )

    sampler = LeapHybridSampler()
    all_run_rows = []
    all_results = []

    for penalty_index, (assignment_penalty, penalty_source) in enumerate(
        penalty_cases,
        start=1,
    ):
        linear = dict(base_linear)
        quadratic = dict(base_quadratic)

        offset, room_variables = add_exact_one_constraints(
            routes,
            assignment_penalty,
            linear,
            quadratic,
        )
        bqm = create_bqm(linear, quadratic, offset)

        print(
            f"\nPenalty {penalty_index}/{len(penalty_cases)}: "
            f"A={assignment_penalty:.6f} ({penalty_source})"
        )

        for run_number in range(1, runs_per_penalty + 1):
            print(
                f"  Run {run_number}/{runs_per_penalty}...",
                end="",
                flush=True,
            )

            started = time.perf_counter()
            sampleset = solve_with_hybrid(
                bqm,
                run_number=run_number,
                sampler=sampler,
                penalty_label=f"A={assignment_penalty:.6f}",
            )
            solver_seconds = time.perf_counter() - started

            result = evaluate_run_result(
                sampleset,
                room_variables,
                routes,
                weighted_rows,
                edge_rows,
                edge_ids,
            )

            result.update(
                {
                    "assignment_penalty": assignment_penalty,
                    "penalty_source": penalty_source,
                    "run": run_number,
                    "bqm": bqm,
                    "sampleset": sampleset,
                    "solver_wall_clock_seconds": solver_seconds,
                }
            )
            all_results.append(result)

            run_row = {
                "solver": "dwave.system.LeapHybridSampler",
                "assignment_penalty": assignment_penalty,
                "penalty_source": penalty_source,
                "run": run_number,
                "problem_id": sampleset.info.get("problem_id", ""),
                "best_energy": float(result["best"].energy),
                "valid_best_solution": result["valid"],
                "valid_sample_rate": float(
                    result["sample_stats"]["valid_sample_rate"]
                ),
                "total_distance": result["total_distance"],
                "congestion_objective": result["congestion_objective"],
                "overload_objective": result["overload_objective"],
                "used_edge_count": result["used_edge_count"],
                "overloaded_edge_count": result["overloaded_edge_count"],
                "maximum_edge_utilization": result["maximum_edge_utilization"],
                "solver_wall_clock_seconds": solver_seconds,
            }
            all_run_rows.append(run_row)

            print(
                f" energy={float(result['best'].energy):.6f}, "
                f"valid={result['valid']}, "
                f"returned_valid_rate="
                f"{100.0 * result['sample_stats']['valid_sample_rate']:.2f}%, "
                f"time={solver_seconds:.3f}s"
            )

    write_penalty_sweep_outputs(all_run_rows)

    valid_results = [result for result in all_results if result["valid"]]
    candidate_results = valid_results if valid_results else all_results
    best_result = min(
        candidate_results,
        key=lambda result: float(result["best"].energy),
    )

    export_bqm_csvs(
        best_result["bqm"],
        routes,
        distances,
        congestion_gram,
    )
    export_samples(best_result["sampleset"], room_variables)

    summary = write_solution_outputs(
        best_result["bqm"],
        best_result["sampleset"],
        routes,
        best_result["selected_routes"],
        best_result["violations"],
        best_result["total_distance"],
        best_result["total_people"],
        best_result["congestion_objective"],
        best_result["overload_objective"],
        best_result["edge_report"],
        best_result["exit_report"],
        best_result["assignment_penalty"],
        objective_scales,
        pruned_interaction_count,
        best_result["best"],
        best_result["sample_stats"],
    )

    print("\nLEAP-HYBRID PENALTY SWEEP COMPLETE")
    print("=" * 52)
    print(
        f"Best valid penalty by energy: "
        f"{best_result['assignment_penalty']:.6f}"
    )
    print(f"Best run:                    {best_result['run']}")
    print(f"Best valid energy:           {float(best_result['best'].energy):.6f}")
    print(f"Total route distance:        {best_result['total_distance']:.6f}")
    print(
        f"Congestion objective:        "
        f"{best_result['congestion_objective']:.6f}"
    )
    print(f"Overloaded edges:            {best_result['overloaded_edge_count']}")
    print(
        "Per-run results:             "
        f"{OUTPUT_DIR / 'hybrid_penalty_sweep_runs.csv'}"
    )
    print(
        "Per-penalty summary:         "
        f"{OUTPUT_DIR / 'hybrid_penalty_sweep_summary.csv'}"
    )
    print(f"Output directory:             {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
