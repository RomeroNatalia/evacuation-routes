"""Compare classical Dijkstra routes with congestion-aware routes.

Run from the repository root after generating both routing stages:

    python scripts/run_classical_routing.py
    python scripts/run_congestion_analysis.py
    python scripts/render_dijkstra_vs_congestion.py

Output:

    data/floorplans/FPXX/output/dijkstra_vs_congestion_routes.png

The visualization uses one floor-plan-aligned graph:

- Gray edges: legal navigation network
- Blue solid edges: used only by classical Dijkstra routes
- Orange dashed edges: used only by congestion-aware routes
- Purple solid edges: used by both route sets
- Red rings: rooms whose assigned exit changed
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import re
import sys

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import networkx as nx
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
COMPARISON_CSV = FLOORPLAN.output_dir / "route_assignment_comparison.csv"
OUTPUT_IMAGE = FLOORPLAN.output_dir / "dijkstra_vs_congestion_routes.png"


def spreadsheet_column_to_number(column_letters: str) -> int:
    """Convert spreadsheet-style letters such as A or AA into numbers."""
    value = 0

    for letter in column_letters:
        value = value * 26 + ord(letter) - ord("A") + 1

    return value


def parse_grid_position(grid_position: str) -> tuple[float, float]:
    """Convert a grid label such as E3.5 into drawing coordinates."""
    match = re.fullmatch(
        r"([A-Z]+)(_A)?(\d+(?:\.\d+)?)",
        str(grid_position).strip(),
    )

    if match is None:
        raise ValueError(
            f"Invalid grid position: {grid_position!r}"
        )

    column_letters, half_column_marker, row_text = match.groups()

    x_coordinate = float(spreadsheet_column_to_number(column_letters))
    if half_column_marker:
        x_coordinate += 0.5

    return (
        x_coordinate,
        float(row_text),
    )


def build_positions(
    nodes: pd.DataFrame,
) -> dict[str, tuple[float, float]]:
    """Build an exact floor-plan coordinate for every node."""
    return {
        str(row.node_id): parse_grid_position(row.grid_position)
        for row in nodes.itertuples(index=False)
    }


def path_text_to_edges(path_text: str) -> list[tuple[str, str]]:
    """Convert a saved route string into normalized undirected edges."""
    nodes = [
        node_id.strip()
        for node_id in str(path_text).split("->")
        if node_id.strip()
    ]

    return [
        tuple(sorted((source, target)))
        for source, target in zip(nodes[:-1], nodes[1:])
    ]


def count_route_usage(
    routes: pd.DataFrame,
    path_column: str,
) -> Counter:
    """Count how many room routes use each graph edge."""
    usage: Counter = Counter()

    for path_text in routes[path_column]:
        for edge in path_text_to_edges(path_text):
            usage[edge] += 1

    return usage


def nodes_of_type(graph: nx.Graph, node_type: str) -> list[str]:
    """Return all nodes belonging to one graph category."""
    return [
        node_id
        for node_id, attributes in graph.nodes(data=True)
        if attributes.get("node_type") == node_type
    ]


def draw_nodes(
    graph: nx.Graph,
    positions: dict[str, tuple[float, float]],
    axis,
) -> None:
    """Draw navigation, room, door, and exit nodes."""
    nx.draw_networkx_nodes(
        graph,
        positions,
        nodelist=nodes_of_type(graph, "navigation"),
        node_size=18,
        node_color="lightgray",
        edgecolors="black",
        linewidths=0.2,
        alpha=0.55,
        ax=axis,
    )

    nx.draw_networkx_nodes(
        graph,
        positions,
        nodelist=nodes_of_type(graph, "room_start"),
        node_shape="o",
        node_size=120,
        node_color="white",
        edgecolors="black",
        linewidths=0.9,
        ax=axis,
    )

    nx.draw_networkx_nodes(
        graph,
        positions,
        nodelist=nodes_of_type(graph, "door"),
        node_shape="s",
        node_size=90,
        node_color="white",
        edgecolors="black",
        linewidths=0.8,
        ax=axis,
    )

    nx.draw_networkx_nodes(
        graph,
        positions,
        nodelist=nodes_of_type(graph, "exit"),
        node_shape="D",
        node_size=120,
        node_color="white",
        edgecolors="black",
        linewidths=1.0,
        ax=axis,
    )


def draw_edge_group(
    graph: nx.Graph,
    positions: dict[str, tuple[float, float]],
    axis,
    edges: set[tuple[str, str]],
    usage: Counter,
    color: str,
    style: str,
    base_width: float,
    alpha: float,
) -> None:
    """Draw route edges with thickness based on the number of users."""
    if not edges:
        return

    maximum_usage = max(usage[edge] for edge in edges)

    for count in range(1, maximum_usage + 1):
        matching_edges = [
            edge
            for edge in edges
            if usage[edge] == count
        ]

        if not matching_edges:
            continue

        nx.draw_networkx_edges(
            graph,
            positions,
            edgelist=matching_edges,
            width=base_width + 0.45 * count,
            edge_color=color,
            style=style,
            alpha=alpha,
            ax=axis,
        )


def label_rooms_and_exits(
    graph: nx.Graph,
    positions: dict[str, tuple[float, float]],
    comparison: pd.DataFrame,
    axis,
) -> None:
    """Label rooms, changed assignments, and exits."""
    comparison_lookup = comparison.set_index("room_id")

    for node_id, attributes in graph.nodes(data=True):
        node_type = attributes.get("node_type")
        x_position, y_position = positions[node_id]

        if node_type == "room_start":
            room_id = str(attributes.get("room_id", ""))
            room_name = str(attributes.get("room_name", ""))
            row = comparison_lookup.loc[room_id]

            if bool(row["exit_changed"]):
                assignment = (
                    f"{room_id}: {room_name}\n"
                    f"Dijkstra {row['classical_exit']} -> "
                    f"Congestion {row['congestion_aware_exit']}"
                )
                facecolor = "mistyrose"
                linewidth = 1.2
            else:
                assignment = f"{room_id}\n{room_name}"
                facecolor = "white"
                linewidth = 0.4

            axis.annotate(
                assignment,
                xy=(x_position, y_position),
                xytext=(0, 14),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=7,
                fontweight="bold",
                bbox={
                    "boxstyle": "round,pad=0.18",
                    "facecolor": facecolor,
                    "alpha": 0.9,
                    "linewidth": linewidth,
                },
                zorder=20,
            )

        elif node_type == "exit":
            axis.annotate(
                node_id,
                xy=(x_position, y_position),
                xytext=(0, 12),
                textcoords="offset points",
                ha="center",
                va="bottom",
                fontsize=8,
                fontweight="bold",
                bbox={
                    "boxstyle": "round,pad=0.16",
                    "facecolor": "white",
                    "alpha": 0.9,
                    "linewidth": 0.5,
                },
                zorder=20,
            )


def highlight_changed_rooms(
    graph: nx.Graph,
    positions: dict[str, tuple[float, float]],
    comparison: pd.DataFrame,
    axis,
) -> None:
    """Draw a red ring around rooms whose selected exit changed."""
    changed_rooms = set(
        comparison.loc[
            comparison["exit_changed"].astype(bool),
            "room_id",
        ]
    )

    changed_start_nodes = [
        node_id
        for node_id, attributes in graph.nodes(data=True)
        if attributes.get("node_type") == "room_start"
        and attributes.get("room_id") in changed_rooms
    ]

    if changed_start_nodes:
        nx.draw_networkx_nodes(
            graph,
            positions,
            nodelist=changed_start_nodes,
            node_shape="o",
            node_size=240,
            node_color="none",
            edgecolors="red",
            linewidths=2.0,
            ax=axis,
        )


def configure_axes(
    axis,
    positions: dict[str, tuple[float, float]],
) -> None:
    """Match the orientation of the original floor-plan grid."""
    x_values = [x for x, _ in positions.values()]
    y_values = [y for _, y in positions.values()]
    margin = 0.8

    axis.set_xlim(min(x_values) - margin, max(x_values) + margin)
    axis.set_ylim(max(y_values) + margin, min(y_values) - margin)
    axis.set_aspect("equal", adjustable="box")
    axis.set_xlabel("Grid column")
    axis.set_ylabel("Grid row")
    axis.set_title(
        "Dijkstra Routes vs. Congestion-Aware Routes\n"
        "Shared segments, route changes, and changed exit assignments",
        fontsize=18,
        pad=20,
    )
    axis.grid(False)


def main() -> None:
    """Create the route-comparison visualization."""
    if not COMPARISON_CSV.exists():
        raise FileNotFoundError(
            "Missing route comparison output. Run:\n\n"
            "    python scripts/run_classical_routing.py\n"
            "    python scripts/run_congestion_analysis.py\n"
        )

    nodes, edges = load_graph_data(NODE_CSV, EDGE_CSV)
    graph = build_navigation_graph(nodes, edges)
    positions = build_positions(nodes)
    comparison = pd.read_csv(COMPARISON_CSV)

    classical_usage = count_route_usage(
        comparison,
        "classical_path",
    )
    congestion_usage = count_route_usage(
        comparison,
        "congestion_aware_path",
    )

    classical_edges = set(classical_usage)
    congestion_edges = set(congestion_usage)

    shared_edges = classical_edges & congestion_edges
    classical_only_edges = classical_edges - congestion_edges
    congestion_only_edges = congestion_edges - classical_edges

    shared_usage: Counter = Counter()
    for edge in shared_edges:
        shared_usage[edge] = max(
            classical_usage[edge],
            congestion_usage[edge],
        )

    figure, axis = plt.subplots(figsize=(34, 23))

    nx.draw_networkx_edges(
        graph,
        positions,
        width=0.6,
        edge_color="lightgray",
        alpha=0.35,
        ax=axis,
    )

    draw_nodes(graph, positions, axis)

    draw_edge_group(
        graph,
        positions,
        axis,
        shared_edges,
        shared_usage,
        color="purple",
        style="solid",
        base_width=1.2,
        alpha=0.75,
    )

    draw_edge_group(
        graph,
        positions,
        axis,
        classical_only_edges,
        classical_usage,
        color="royalblue",
        style="solid",
        base_width=1.5,
        alpha=0.95,
    )

    draw_edge_group(
        graph,
        positions,
        axis,
        congestion_only_edges,
        congestion_usage,
        color="darkorange",
        style="dashed",
        base_width=1.7,
        alpha=0.95,
    )

    highlight_changed_rooms(
        graph,
        positions,
        comparison,
        axis,
    )

    label_rooms_and_exits(
        graph,
        positions,
        comparison,
        axis,
    )

    configure_axes(axis, positions)

    legend_items = [
        Line2D(
            [0],
            [0],
            color="lightgray",
            linewidth=1.5,
            label="Verified legal graph edge",
        ),
        Line2D(
            [0],
            [0],
            color="purple",
            linewidth=3,
            label="Used by both route sets",
        ),
        Line2D(
            [0],
            [0],
            color="royalblue",
            linewidth=3,
            label="Dijkstra only",
        ),
        Line2D(
            [0],
            [0],
            color="darkorange",
            linewidth=3,
            linestyle="--",
            label="Congestion-aware only",
        ),
        Line2D(
            [0],
            [0],
            marker="o",
            markersize=10,
            markerfacecolor="none",
            markeredgecolor="red",
            linewidth=0,
            label="Room changed exits",
        ),
    ]

    axis.legend(
        handles=legend_items,
        loc="upper left",
        fontsize=9,
        frameon=True,
    )

    OUTPUT_IMAGE.parent.mkdir(parents=True, exist_ok=True)
    figure.tight_layout()
    figure.savefig(
        OUTPUT_IMAGE,
        dpi=300,
        bbox_inches="tight",
    )
    plt.close(figure)

    changed = comparison.loc[
        comparison["exit_changed"].astype(bool),
        [
            "room_id",
            "classical_exit",
            "congestion_aware_exit",
        ],
    ]

    print(f"Saved comparison visual to: {OUTPUT_IMAGE}")
    print("\nRooms with changed exit assignments:")
    print(changed.to_string(index=False))


if __name__ == "__main__":
    main()
