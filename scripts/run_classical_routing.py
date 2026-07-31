"""Run the complete navigation-graph-to-classical-routing pipeline.

Run from the repository root:

    python scripts/run_classical_routing.py
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import subprocess

# Allow this script to import the package directly from src/ even before the
# repository has been installed with pip.
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRECTORY = REPOSITORY_ROOT / "src"
sys.path.insert(0, str(SOURCE_DIRECTORY))

from fire_evacuation.graph_io import (  # noqa: E402
    build_navigation_graph,
    load_graph_data,
    validate_graph_connectivity,
)
from fire_evacuation.routing import (  # noqa: E402
    choose_primary_routes,
    compute_all_room_exit_routes,
    expand_primary_route_nodes,
)
from fire_evacuation.visualization import draw_graph  # noqa: E402


from fire_evacuation.project import floorplan_paths_from_argv  # noqa: E402

FLOORPLAN = floorplan_paths_from_argv(REPOSITORY_ROOT)
NODE_CSV = FLOORPLAN.nodes_csv
EDGE_CSV = FLOORPLAN.edges_csv
OUTPUT_DIRECTORY = FLOORPLAN.output_dir


def main() -> None:
    """Execute each pipeline stage in a clear, reproducible order."""
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)

    print(f"1. Loading {FLOORPLAN.floorplan_id} node and edge tables...")
    nodes, edges = load_graph_data(NODE_CSV, EDGE_CSV)

    print("2. Building the weighted NetworkX graph...")
    graph = build_navigation_graph(nodes, edges)

    print("3. Validating graph connectivity...")
    validation = validate_graph_connectivity(graph)

    if not validation["all_rooms_reach_all_exits"]:
        raise RuntimeError(
            "At least one room cannot reach every exit. "
            "Review the node and edge CSV files before routing."
        )

    if not validation["all_doors_have_valid_degree"]:
        raise RuntimeError(
            "At least one doorway has an invalid graph degree. "
            "Verified doorways must have two or three straight connections."
        )

    validation_path = OUTPUT_DIRECTORY / "graph_validation.json"
    validation_path.write_text(
        json.dumps(validation, indent=2),
        encoding="utf-8",
    )

    print("4. Computing all room-to-exit routes with Dijkstra and A*...")
    all_routes = compute_all_room_exit_routes(graph)

    if not all_routes["distances_match"].all():
        raise RuntimeError(
            "A* and Dijkstra produced different minimum distances. "
            "Review the heuristic or edge weights."
        )

    all_routes.to_csv(
        OUTPUT_DIRECTORY / "all_room_exit_routes.csv",
        index=False,
    )

    print("5. Selecting the nearest exit for each room...")
    primary_routes = choose_primary_routes(all_routes)
    primary_routes.to_csv(
        OUTPUT_DIRECTORY / "primary_routes.csv",
        index=False,
    )

    print("6. Expanding each primary path into an ordered node sequence...")
    route_nodes = expand_primary_route_nodes(graph, primary_routes)
    route_nodes.to_csv(
        OUTPUT_DIRECTORY / "primary_route_nodes.csv",
        index=False,
    )

    print("7. Drawing a primary-route overview...")
    draw_graph(
        graph,
        OUTPUT_DIRECTORY / "primary_routes.png",
        primary_routes=primary_routes,
    )

    print("8. Creating the simplified presentation diagram...")
    subprocess.run(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "scripts/render_route_summary.py"),
            "--floorplan",
            FLOORPLAN.floorplan_id,
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
    )

    print("\nClassical routing completed successfully.\n")
    print(
        primary_routes[
            [
                "room_id",
                "room_name",
                "primary_exit",
                "distance",
                "hops",
            ]
        ].to_string(index=False)
    )

    print(
        "\nGenerated files are in:",
        OUTPUT_DIRECTORY,
    )


if __name__ == "__main__":
    main()
