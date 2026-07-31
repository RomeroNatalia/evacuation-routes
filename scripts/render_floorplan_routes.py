"""Render the verified building graph and Dijkstra routes on its real layout.

Run this file from the repository root with:

    python scripts/render_floorplan_routes.py

Before running it, make sure the classical routing output exists:

    python scripts/run_classical_routing.py

This script produces two images:

    data/floorplans/FPXX/output/navigation_graph_verified.png
    data/floorplans/FPXX/output/primary_routes_floorplan.png

The first image shows the complete verified graph with exact node IDs.

The second image uses the same building-aligned coordinates, but highlights
the selected primary Dijkstra route for every room.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import math
import re
import sys

import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd


# =====================================================================
# Repository paths
# =====================================================================

# This script is stored in:
#
#     fire-evacuation-routing/scripts/render_floorplan_routes.py
#
# Therefore, parents[1] is the repository root.
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]

# The reusable Python package is stored under src/.
SOURCE_DIRECTORY = REPOSITORY_ROOT / "src"

# Add src/ to Python's module search path so the package can be imported
# without requiring a separate installation first.
sys.path.insert(0, str(SOURCE_DIRECTORY))

from fire_evacuation.graph_io import (  # noqa: E402
    build_navigation_graph,
    load_graph_data,
)


from fire_evacuation.project import floorplan_paths_from_argv  # noqa: E402

FLOORPLAN = floorplan_paths_from_argv(REPOSITORY_ROOT)
FLOORPLAN_NAME = str(pd.read_csv(FLOORPLAN.metadata_csv).iloc[0]["floorplan_name"])
NODE_CSV = FLOORPLAN.nodes_csv
EDGE_CSV = FLOORPLAN.edges_csv
PRIMARY_ROUTES_CSV = FLOORPLAN.output_dir / "primary_routes.csv"
OUTPUT_DIRECTORY = FLOORPLAN.output_dir
VERIFIED_GRAPH_IMAGE = OUTPUT_DIRECTORY / "navigation_graph_verified.png"
PRIMARY_ROUTES_IMAGE = OUTPUT_DIRECTORY / "primary_routes_floorplan.png"


# =====================================================================
# Position helpers
# =====================================================================

def spreadsheet_column_to_number(column_letters: str) -> int:
    """Convert spreadsheet-style letters to a numeric x-coordinate.

    Examples:

        A  -> 1
        B  -> 2
        Z  -> 26
        AA -> 27

    The node CSV uses labels such as E3.5 and N10. This conversion allows
    Matplotlib and NetworkX to place the graph in the same geometric layout
    as the original building grid.
    """
    column_number = 0

    for letter in column_letters:
        column_number = (
            column_number * 26
            + ord(letter)
            - ord("A")
            + 1
        )

    return column_number


def parse_grid_position(grid_position: str) -> tuple[float, float]:
    """Convert a grid label such as E3.5 into numeric coordinates.

    The letters become the x-coordinate and the number becomes the
    y-coordinate.

    Door nodes may use half-grid positions, such as E3.5, because they are
    located between two regular grid rows.
    """
    match = re.fullmatch(
        r"([A-Z]+)(_A)?(\d+(?:\.\d+)?)",
        str(grid_position).strip(),
    )

    if match is None:
        raise ValueError(
            f"Invalid grid position: {grid_position!r}. "
            "Expected a label such as A2, E3.5, E_A9, or N10."
        )

    column_letters, half_column_marker, row_text = match.groups()

    x_coordinate = float(spreadsheet_column_to_number(column_letters))
    if half_column_marker:
        x_coordinate += 0.5

    return (
        x_coordinate,
        float(row_text),
    )


def build_position_dictionary(
    nodes: pd.DataFrame,
) -> dict[str, tuple[float, float]]:
    """Create drawing coordinates for every graph node.

    Most nodes use their exact grid location. If multiple nodes occupy the
    same grid position, such as a door node and a navigation node, the nodes
    are given tiny deterministic display offsets so the categories remain
    visible in the rendered image. The underlying graph geometry is not
    changed; this affects drawing only.
    """
    rows = list(nodes.itertuples(index=False))

    base_positions = {
        str(row.node_id): parse_grid_position(row.grid_position)
        for row in rows
    }

    groups: dict[tuple[float, float], list[tuple[str, str]]] = {}
    for row in rows:
        node_id = str(row.node_id)
        node_type = str(row.node_type)
        base_position = base_positions[node_id]
        groups.setdefault(base_position, []).append((node_id, node_type))

    type_priority = {
        "door": 0,
        "exit": 1,
        "room_start": 2,
        "navigation": 3,
    }

    offset_templates = [
        (0.0, 0.0),
        (0.18, 0.0),
        (-0.18, 0.0),
        (0.0, 0.18),
        (0.0, -0.18),
        (0.14, 0.14),
        (-0.14, 0.14),
        (0.14, -0.14),
        (-0.14, -0.14),
    ]

    positions: dict[str, tuple[float, float]] = {}

    for base_position, members in groups.items():
        if len(members) == 1:
            node_id, _ = members[0]
            positions[node_id] = base_position
            continue

        ordered_members = sorted(
            members,
            key=lambda item: (type_priority.get(item[1], 99), item[0]),
        )

        for index, (node_id, _) in enumerate(ordered_members):
            if index < len(offset_templates):
                dx, dy = offset_templates[index]
            else:
                angle = 2.0 * math.pi * index / len(ordered_members)
                dx = 0.2 * math.cos(angle)
                dy = 0.2 * math.sin(angle)

            positions[node_id] = (
                base_position[0] + dx,
                base_position[1] + dy,
            )

    return positions


def build_exact_graph_positions(
    graph: nx.Graph,
) -> dict[str, tuple[float, float]]:
    """Return unshifted coordinates for drawing physically straight edges.

    Node markers may receive tiny display offsets when multiple graph nodes share
    one coordinate. Edges must still follow the exact underlying grid geometry,
    so they are always drawn using these unshifted coordinates.
    """
    return {
        str(node_id): parse_grid_position(str(attributes["grid_position"]))
        for node_id, attributes in graph.nodes(data=True)
    }


# =====================================================================
# Graph-node helpers
# =====================================================================

def nodes_of_type(
    graph: nx.Graph,
    node_type: str,
) -> list[str]:
    """Return all graph nodes belonging to one node category."""
    return sorted(
        node_id
        for node_id, attributes in graph.nodes(data=True)
        if attributes.get("node_type") == node_type
    )


def full_special_node_label(
    graph: nx.Graph,
    node_id: str,
) -> str:
    """Create a readable label for a room start, door, or exit."""
    attributes = graph.nodes[node_id]
    node_type = attributes.get("node_type")

    if node_type == "room_start":
        room_id = attributes.get("room_id", "")
        room_name = attributes.get("room_name", "")

        return f"{room_id}\n{room_name}"

    return node_id


def route_path_to_edges(path_text: str) -> list[tuple[str, str]]:
    """Convert a saved route string into ordered graph edges.

    Example input:

        START_R01 -> R01 -> DOOR_01 -> E4 -> EXIT_A

    Example output:

        [
            ("START_R01", "R01"),
            ("R01", "DOOR_01"),
            ("DOOR_01", "E4"),
            ("E4", "EXIT_A"),
        ]
    """
    path_nodes = [
        node_id.strip()
        for node_id in str(path_text).split("->")
        if node_id.strip()
    ]

    return list(zip(path_nodes[:-1], path_nodes[1:]))


# =====================================================================
# Shared drawing helpers
# =====================================================================

def configure_building_axes(
    axis,
    positions: dict[str, tuple[float, float]],
    title: str,
) -> None:
    """Make the graph orientation match the physical floor-plan layout."""
    x_values = [x for x, _ in positions.values()]
    y_values = [y for _, y in positions.values()]

    margin = 0.8

    axis.set_xlim(
        min(x_values) - margin,
        max(x_values) + margin,
    )

    # The floor-plan grid uses row 1 at the top.
    #
    # Matplotlib normally increases y upward, so reversing the limits places
    # row 1 above row 2, row 2 above row 3, and so on.
    axis.set_ylim(
        max(y_values) + margin,
        min(y_values) - margin,
    )

    axis.set_aspect("equal", adjustable="box")
    axis.set_xlabel("Grid column")
    axis.set_ylabel("Grid row")
    axis.set_title(title, fontsize=18, pad=20)
    axis.grid(False)


def draw_node_categories(
    graph: nx.Graph,
    positions: dict[str, tuple[float, float]],
    axis,
    navigation_alpha: float = 0.85,
) -> None:
    """Draw each node category with a different shape and size.

    Shapes are used so the visualization remains understandable even if it
    is printed without color.
    """
    navigation_nodes = nodes_of_type(graph, "navigation")
    room_start_nodes = nodes_of_type(graph, "room_start")
    door_nodes = nodes_of_type(graph, "door")
    exit_nodes = nodes_of_type(graph, "exit")

    nx.draw_networkx_nodes(
        graph,
        positions,
        nodelist=navigation_nodes,
        node_shape="o",
        node_size=22,
        alpha=navigation_alpha,
        linewidths=0.3,
        edgecolors="black",
        ax=axis,
        label="Navigation node",
    )

    nx.draw_networkx_nodes(
        graph,
        positions,
        nodelist=room_start_nodes,
        node_shape="o",
        node_size=130,
        linewidths=0.8,
        edgecolors="black",
        ax=axis,
        label="Room-start node",
    )

    nx.draw_networkx_nodes(
        graph,
        positions,
        nodelist=door_nodes,
        node_shape="s",
        node_size=105,
        linewidths=0.8,
        edgecolors="black",
        ax=axis,
        label="Door node",
    )

    nx.draw_networkx_nodes(
        graph,
        positions,
        nodelist=exit_nodes,
        node_shape="D",
        node_size=125,
        linewidths=0.8,
        edgecolors="black",
        ax=axis,
        label="Exit node",
    )


# =====================================================================
# Image 1: fully labeled verified graph
# =====================================================================

def draw_verified_navigation_graph(
    graph: nx.Graph,
    positions: dict[str, tuple[float, float]],
    output_path: Path,
) -> None:
    """Draw the complete verified graph with exact node IDs.

    This is the technical validation image. Every legal edge is shown and
    every graph node is labeled with the exact ID found in the CSV files.
    """
    figure, axis = plt.subplots(figsize=(34, 23))

    # Draw all verified legal connections.
    nx.draw_networkx_edges(
        graph,
        build_exact_graph_positions(graph),
        width=0.75,
        alpha=0.55,
        ax=axis,
    )

    draw_node_categories(
        graph,
        positions,
        axis,
        navigation_alpha=0.95,
    )

    # Label every node with its exact node ID.
    #
    # The font is intentionally small because the graph contains many
    # navigation nodes.
    nx.draw_networkx_labels(
        graph,
        positions,
        labels={
            node_id: node_id
            for node_id in graph.nodes
        },
        font_size=4.2,
        verticalalignment="bottom",
        ax=axis,
    )

    configure_building_axes(
        axis,
        positions,
        (
            f"Verified {FLOORPLAN_NAME} Evacuation Network\n"
            "Exact node IDs and source-target connections"
        ),
    )

    axis.legend(
        loc="upper left",
        fontsize=8,
        frameon=True,
    )

    figure.tight_layout()
    figure.savefig(
        output_path,
        dpi=300,
        bbox_inches="tight",
    )
    plt.close(figure)


# =====================================================================
# Image 2: floor-plan-aligned Dijkstra routes
# =====================================================================

def count_route_edge_usage(
    primary_routes: pd.DataFrame,
) -> Counter:
    """Count how many selected room routes use each graph edge.

    An undirected graph edge can be written in either direction, such as:

        (A, B)
        (B, A)

    Sorting each pair gives one consistent representation.
    """
    edge_usage: Counter = Counter()

    for route in primary_routes.itertuples(index=False):
        for source, target in route_path_to_edges(str(route.path)):
            normalized_edge = tuple(sorted((source, target)))
            edge_usage[normalized_edge] += 1

    return edge_usage


def draw_route_edge_usage(
    graph: nx.Graph,
    positions: dict[str, tuple[float, float]],
    primary_routes: pd.DataFrame,
    axis,
) -> None:
    """Overlay the selected Dijkstra routes on the verified graph.

    Edges used by multiple room routes are drawn thicker. This allows the
    image to reveal shared hallway segments before occupancy is added.
    """
    edge_usage = count_route_edge_usage(primary_routes)

    if not edge_usage:
        return

    maximum_usage = max(edge_usage.values())

    # Draw one usage group at a time so shared edges can have thicker lines.
    for usage_count in range(1, maximum_usage + 1):
        matching_edges = [
            edge
            for edge, count in edge_usage.items()
            if count == usage_count
        ]

        if not matching_edges:
            continue

        # A small base width keeps single-room paths visible.
        #
        # Shared routes become progressively thicker.
        route_width = 1.4 + 0.65 * usage_count

        nx.draw_networkx_edges(
            graph,
            build_exact_graph_positions(graph),
            edgelist=matching_edges,
            width=route_width,
            alpha=0.9,
            ax=axis,
        )


def label_special_nodes(
    graph: nx.Graph,
    positions: dict[str, tuple[float, float]],
    axis,
) -> None:
    """Label rooms, doors, and exits without crowding navigation nodes."""
    for node_id, attributes in graph.nodes(data=True):
        node_type = attributes.get("node_type")

        if node_type == "navigation":
            continue

        x_position, y_position = positions[node_id]

        # Room labels need more vertical space than short door and exit IDs.
        if node_type == "room_start":
            offset = (0, 12)
            font_size = 7.5
        elif node_type == "door":
            offset = (0, -12)
            font_size = 6.8
        else:
            offset = (0, 11)
            font_size = 7.2

        axis.annotate(
            full_special_node_label(graph, node_id),
            xy=(x_position, y_position),
            xytext=offset,
            textcoords="offset points",
            ha="center",
            va="center",
            fontsize=font_size,
            fontweight="bold",
            bbox={
                "boxstyle": "round,pad=0.16",
                "facecolor": "white",
                "alpha": 0.88,
                "linewidth": 0.4,
            },
            zorder=10,
        )


def label_primary_exit_assignments(
    graph: nx.Graph,
    positions: dict[str, tuple[float, float]],
    primary_routes: pd.DataFrame,
    axis,
) -> None:
    """Place the assigned exit beside each room-start node."""
    for route in primary_routes.itertuples(index=False):
        start_node = str(route.start_node)
        primary_exit = str(route.primary_exit)
        distance = float(route.distance)

        x_position, y_position = positions[start_node]

        assignment_text = (
            f"Primary: {primary_exit}\n"
            f"Distance: {distance:.2f}"
        )

        axis.annotate(
            assignment_text,
            xy=(x_position, y_position),
            xytext=(42, 0),
            textcoords="offset points",
            ha="left",
            va="center",
            fontsize=6.3,
            bbox={
                "boxstyle": "round,pad=0.14",
                "facecolor": "white",
                "alpha": 0.82,
                "linewidth": 0.35,
            },
            zorder=9,
        )


def draw_primary_routes_floorplan(
    graph: nx.Graph,
    positions: dict[str, tuple[float, float]],
    primary_routes: pd.DataFrame,
    output_path: Path,
) -> None:
    """Draw all selected Dijkstra routes over the real graph geometry."""
    figure, axis = plt.subplots(figsize=(34, 23))

    # First draw the complete navigation network lightly.
    nx.draw_networkx_edges(
        graph,
        build_exact_graph_positions(graph),
        width=0.65,
        alpha=0.20,
        ax=axis,
    )

    # Draw ordinary navigation points lightly so the route overlay remains
    # the main focus.
    draw_node_categories(
        graph,
        positions,
        axis,
        navigation_alpha=0.35,
    )

    # Overlay the selected Dijkstra paths.
    draw_route_edge_usage(
        graph,
        positions,
        primary_routes,
        axis,
    )

    # Label only physically important nodes.
    label_special_nodes(
        graph,
        positions,
        axis,
    )

    # Add the selected exit and route distance near each room.
    label_primary_exit_assignments(
        graph,
        positions,
        primary_routes,
        axis,
    )

    configure_building_axes(
        axis,
        positions,
        (
            f"{FLOORPLAN_NAME}: Primary Dijkstra Evacuation Routes\n"
            "Routes follow the verified room, door, and hallway network"
        ),
    )

    axis.legend(
        loc="upper left",
        fontsize=8,
        frameon=True,
    )

    figure.tight_layout()
    figure.savefig(
        output_path,
        dpi=300,
        bbox_inches="tight",
    )
    plt.close(figure)


# =====================================================================
# Main program
# =====================================================================

def main() -> None:
    """Load the graph and create both floor-plan-aligned images."""
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)

    print("1. Loading the verified node and edge CSV files...")
    nodes, edges = load_graph_data(
        NODE_CSV,
        EDGE_CSV,
    )

    print("2. Building the weighted navigation graph...")
    graph = build_navigation_graph(
        nodes,
        edges,
    )

    print("3. Converting grid labels into exact drawing coordinates...")
    positions = build_position_dictionary(nodes)

    print("4. Drawing the fully labeled verified graph...")
    draw_verified_navigation_graph(
        graph,
        positions,
        VERIFIED_GRAPH_IMAGE,
    )

    if not PRIMARY_ROUTES_CSV.exists():
        raise FileNotFoundError(
            "\nThe primary route CSV does not exist yet.\n"
            "Run this command first:\n\n"
            "    python scripts/run_classical_routing.py\n"
        )

    print("5. Loading the primary Dijkstra routes...")
    primary_routes = pd.read_csv(PRIMARY_ROUTES_CSV)

    required_route_columns = {
        "room_id",
        "room_name",
        "start_node",
        "primary_exit",
        "distance",
        "hops",
        "path",
    }

    missing_columns = (
        required_route_columns
        - set(primary_routes.columns)
    )

    if missing_columns:
        raise ValueError(
            "primary_routes.csv is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )

    print("6. Drawing Dijkstra routes on the building layout...")
    draw_primary_routes_floorplan(
        graph,
        positions,
        primary_routes,
        PRIMARY_ROUTES_IMAGE,
    )

    print("\nFinished successfully.")
    print(f"Verified graph: {VERIFIED_GRAPH_IMAGE}")
    print(f"Route overlay:  {PRIMARY_ROUTES_IMAGE}")


if __name__ == "__main__":
    main()
