"""Run phase 2: occupancy assignment and congestion analysis.

Run from the repository root:

    python scripts/run_classical_routing.py
    python scripts/run_congestion_analysis.py
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import pandas as pd

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRECTORY = REPOSITORY_ROOT / "src"
sys.path.insert(0, str(SOURCE_DIRECTORY))

from fire_evacuation.congestion import (  # noqa: E402
    CONGESTION_WEIGHT,
    PEOPLE_PER_CAPACITY_UNIT,
    assign_occupants_to_routes,
    choose_congestion_aware_dijkstra_routes,
    compare_routes,
    compute_edge_loads,
    compute_node_loads,
    load_room_occupancy,
)
from fire_evacuation.graph_io import (  # noqa: E402
    build_navigation_graph,
    load_graph_data,
)


from fire_evacuation.project import floorplan_paths_from_argv  # noqa: E402

FLOORPLAN = floorplan_paths_from_argv(REPOSITORY_ROOT)
NODE_CSV = FLOORPLAN.nodes_csv
EDGE_CSV = FLOORPLAN.edges_csv
OCCUPANCY_CSV = FLOORPLAN.occupancy_csv
PRIMARY_ROUTES_CSV = FLOORPLAN.output_dir / "primary_routes.csv"
OUTPUT_DIRECTORY = FLOORPLAN.output_dir


def main() -> None:
    """Execute the complete phase 2 pipeline."""
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)

    print("1. Loading the corrected navigation graph...")
    nodes, edges = load_graph_data(NODE_CSV, EDGE_CSV)
    graph = build_navigation_graph(nodes, edges)

    if not PRIMARY_ROUTES_CSV.exists():
        raise FileNotFoundError(
            "Classical outputs are missing. Run:\n\n"
            "    python scripts/run_classical_routing.py\n"
        )

    print("2. Loading occupancy data...")
    occupancy = load_room_occupancy(OCCUPANCY_CSV)

    print("3. Assigning occupants to primary Dijkstra routes...")
    primary_routes = pd.read_csv(PRIMARY_ROUTES_CSV)

    assigned = assign_occupants_to_routes(
        primary_routes,
        occupancy,
    )
    assigned.to_csv(
        OUTPUT_DIRECTORY / "classical_routes_with_occupancy.csv",
        index=False,
    )

    print("4. Counting occupants on every classical edge...")
    classical_edge_loads = compute_edge_loads(
        graph,
        assigned,
    )
    classical_edge_loads.to_csv(
        OUTPUT_DIRECTORY / "classical_edge_loads.csv",
        index=False,
    )

    print("5. Counting occupants at doors, hallways, and exits...")
    classical_node_loads = compute_node_loads(
        graph,
        assigned,
    )
    classical_node_loads.to_csv(
        OUTPUT_DIRECTORY / "classical_node_loads.csv",
        index=False,
    )

    print("6. Running repeated congestion-aware Dijkstra...")
    congestion_routes = choose_congestion_aware_dijkstra_routes(
        graph,
        occupancy,
    )
    congestion_routes.to_csv(
        OUTPUT_DIRECTORY / "congestion_aware_routes.csv",
        index=False,
    )

    congestion_assigned = congestion_routes.rename(
        columns={"selected_exit": "primary_exit"}
    )

    print("7. Counting congestion-aware edge and node loads...")
    congestion_edge_loads = compute_edge_loads(
        graph,
        congestion_assigned,
    )
    congestion_edge_loads.to_csv(
        OUTPUT_DIRECTORY / "congestion_aware_edge_loads.csv",
        index=False,
    )

    congestion_node_loads = compute_node_loads(
        graph,
        congestion_assigned,
    )
    congestion_node_loads.to_csv(
        OUTPUT_DIRECTORY / "congestion_aware_node_loads.csv",
        index=False,
    )

    print("8. Comparing both route assignments...")
    comparison = compare_routes(
        primary_routes,
        congestion_routes,
    )
    comparison.to_csv(
        OUTPUT_DIRECTORY / "route_assignment_comparison.csv",
        index=False,
    )

    summary = {
        "total_occupancy": int(
            occupancy["occupancy"].sum()
        ),
        "people_per_capacity_unit": (
            PEOPLE_PER_CAPACITY_UNIT
        ),
        "congestion_weight": CONGESTION_WEIGHT,
        "classical_congested_edges": int(
            classical_edge_loads["is_congested"].sum()
        ),
        "congestion_aware_congested_edges": int(
            congestion_edge_loads["is_congested"].sum()
        ),
        "rooms_changing_exit": int(
            comparison["exit_changed"].sum()
        ),
        "rooms_changing_path": int(
            comparison["path_changed"].sum()
        ),
        "routing_method": "repeated congestion-aware Dijkstra",
    }

    (
        OUTPUT_DIRECTORY
        / "congestion_analysis_summary.json"
    ).write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )

    print("\nPhase 2 completed successfully.\n")
    print(
        comparison[
            [
                "room_id",
                "occupancy",
                "classical_exit",
                "congestion_aware_exit",
                "exit_changed",
                "classical_distance",
                "congestion_aware_distance",
                "extra_distance",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()