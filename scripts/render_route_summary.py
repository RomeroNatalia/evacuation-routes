"""Create a clean visual summary of the primary Dijkstra routes.

The detailed graph contains many navigation nodes. This presentation diagram
contracts those intermediate nodes and shows the important route structure:

    room start -> door transition -> assigned exit
"""

from __future__ import annotations

from pathlib import Path
import sys

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import pandas as pd

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRECTORY = REPOSITORY_ROOT / "src"
sys.path.insert(0, str(SOURCE_DIRECTORY))

from fire_evacuation.graph_io import (  # noqa: E402
    build_navigation_graph,
    load_graph_data,
)

from fire_evacuation.project import floorplan_paths_from_argv  # noqa: E402

FLOORPLAN = floorplan_paths_from_argv(REPOSITORY_ROOT)
NODE_CSV = FLOORPLAN.nodes_csv
EDGE_CSV = FLOORPLAN.edges_csv
PRIMARY_ROUTES_CSV = FLOORPLAN.output_dir / "primary_routes.csv"
OUTPUT_IMAGE = FLOORPLAN.output_dir / "primary_route_summary.png"


def special_nodes_from_path(graph, path_text: str) -> list[str]:
    """Keep only room-start, door, and exit nodes from one full path."""
    full_path = path_text.split(" -> ")
    important_types = {"room_start", "door", "exit"}

    return [
        node_id
        for node_id in full_path
        if graph.nodes[node_id]["node_type"] in important_types
    ]


def centered_column(
    node_ids: list[str],
    x_position: float,
    spacing: float = 1.35,
) -> dict[str, tuple[float, float]]:
    """Place one node category in a vertically centered column."""
    positions = {}

    if not node_ids:
        return positions

    total_height = spacing * (len(node_ids) - 1)
    first_y = total_height / 2

    for index, node_id in enumerate(node_ids):
        positions[node_id] = (
            x_position,
            first_y - index * spacing,
        )

    return positions


def readable_label(graph, node_id: str) -> str:
    """Create a readable label for rooms, doors, and exits."""
    attributes = graph.nodes[node_id]

    if attributes["node_type"] == "room_start":
        return (
            f'{attributes.get("room_id", "")}\n'
            f'{attributes.get("room_name", "")}'
        )

    return node_id.replace("_", " ")


def draw_box(axis, center, label: str, node_type: str) -> None:
    """Draw one rounded box styled by node type."""
    x_position, y_position = center

    if node_type == "room_start":
        width, height = 3.0, 0.82
        facecolor = "#E9E8FF"
        edgecolor = "#7770E8"
        textcolor = "#37358F"
        fontsize = 9
    elif node_type == "door":
        width, height = 2.0, 0.72
        facecolor = "#F0EEE9"
        edgecolor = "#AAA69D"
        textcolor = "#3E3E3E"
        fontsize = 10
    else:
        width, height = 2.0, 0.72
        facecolor = "#DDF4ED"
        edgecolor = "#67B9A4"
        textcolor = "#0C5548"
        fontsize = 10

    rectangle = FancyBboxPatch(
        (x_position - width / 2, y_position - height / 2),
        width,
        height,
        boxstyle="round,pad=0.08,rounding_size=0.18",
        linewidth=1.0,
        edgecolor=edgecolor,
        facecolor=facecolor,
        zorder=3,
    )
    axis.add_patch(rectangle)

    axis.text(
        x_position,
        y_position,
        label,
        ha="center",
        va="center",
        fontsize=fontsize,
        fontweight="semibold",
        color=textcolor,
        zorder=4,
    )


def main() -> None:
    """Build and save the conceptual route diagram."""
    nodes, edges = load_graph_data(NODE_CSV, EDGE_CSV)
    graph = build_navigation_graph(nodes, edges)

    if not PRIMARY_ROUTES_CSV.exists():
        raise FileNotFoundError(
            "Run python scripts/run_classical_routing.py first."
        )

    primary_routes = pd.read_csv(PRIMARY_ROUTES_CSV)

    summary_nodes: set[str] = set()
    summary_edges: set[tuple[str, str]] = set()

    for route in primary_routes.itertuples(index=False):
        important_path = special_nodes_from_path(
            graph,
            str(route.path),
        )

        summary_nodes.update(important_path)

        for source, target in zip(
            important_path[:-1],
            important_path[1:],
        ):
            summary_edges.add((source, target))

    room_nodes = sorted(
        node_id
        for node_id in summary_nodes
        if graph.nodes[node_id]["node_type"] == "room_start"
    )
    door_nodes = sorted(
        node_id
        for node_id in summary_nodes
        if graph.nodes[node_id]["node_type"] == "door"
    )
    exit_nodes = sorted(
        node_id
        for node_id in summary_nodes
        if graph.nodes[node_id]["node_type"] == "exit"
    )

    positions = {}
    positions.update(centered_column(room_nodes, 0.0))
    positions.update(centered_column(door_nodes, 4.5))
    positions.update(centered_column(exit_nodes, 9.0))

    figure_height = max(10, len(room_nodes) * 0.9)
    figure, axis = plt.subplots(figsize=(16, figure_height))

    # Draw connecting lines first so the boxes cover their endpoints.
    for source, target in summary_edges:
        source_x, source_y = positions[source]
        target_x, target_y = positions[target]

        axis.plot(
            [source_x, target_x],
            [source_y, target_y],
            linewidth=1.4,
            color="#8A8A84",
            zorder=1,
        )

    for node_id in summary_nodes:
        draw_box(
            axis,
            positions[node_id],
            readable_label(graph, node_id),
            graph.nodes[node_id]["node_type"],
        )

    axis.set_title(
        "Primary Dijkstra evacuation routes",
        fontsize=18,
        fontweight="bold",
        pad=24,
    )

    axis.text(
        0.0, 1.01, "Rooms",
        transform=axis.transAxes,
        ha="left",
        fontsize=11,
        fontweight="bold",
        color="#37358F",
    )
    axis.text(
        0.5, 1.01, "Door transitions",
        transform=axis.transAxes,
        ha="center",
        fontsize=11,
        fontweight="bold",
        color="#3E3E3E",
    )
    axis.text(
        1.0, 1.01, "Assigned exits",
        transform=axis.transAxes,
        ha="right",
        fontsize=11,
        fontweight="bold",
        color="#0C5548",
    )

    y_values = [y for _, y in positions.values()]
    axis.set_xlim(-2.0, 11.0)
    axis.set_ylim(min(y_values) - 1.0, max(y_values) + 1.0)
    axis.axis("off")

    figure.tight_layout()
    figure.savefig(
        OUTPUT_IMAGE,
        dpi=300,
        bbox_inches="tight",
    )
    plt.close(figure)

    print(f"Saved visual route summary to: {OUTPUT_IMAGE}")


if __name__ == "__main__":
    main()
