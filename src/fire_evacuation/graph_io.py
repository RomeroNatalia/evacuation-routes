"""Read, validate, and convert the CSV floor-plan data into a NetworkX graph.

The two input CSV files serve different purposes:

* The node table says which physical points exist.
* The edge table says which movements are legally allowed.

This separation is important. Dijkstra's algorithm does not understand walls,
rooms, or doors by itself. It only understands nodes connected by weighted
edges. Therefore, wall and doorway logic must already be encoded correctly in
the edge table before shortest-path routing begins.
"""

from __future__ import annotations

from pathlib import Path
import re

import networkx as nx
import pandas as pd


REQUIRED_NODE_COLUMNS = {
    "node_id",
    "node_type",
    "grid_position",
    "description",
    "space_type",
    "space_id",
    "space_name",
    "room_id",
    "room_name",
}

REQUIRED_EDGE_COLUMNS = {
    "source",
    "target",
    "edge_type",
    "distance",
    "capacity",
    "notes",
}


def grid_position_to_xy(grid_position: str) -> tuple[float, float]:
    """Convert a label such as ``E3.5`` into numeric graph coordinates.

    Columns use spreadsheet-style letters:

    * A -> 1
    * B -> 2
    * Z -> 26
    * AA -> 27

    Rows are stored as numbers. A doorway can therefore sit between grid rows,
    such as ``E3.5``.

    The returned coordinates are used for graph visualization and the A*
    heuristic. They do not change which edges exist.
    """
    match = re.fullmatch(
        r"([A-Z]+)(_A)?(\d+(?:\.\d+)?)",
        str(grid_position).strip(),
    )

    if match is None:
        raise ValueError(
            f"Invalid grid position {grid_position!r}. "
            "Expected a value such as A2, N10, E3.5, or E_A9."
        )

    column_letters, half_column_marker, row_text = match.groups()

    column_number = 0
    for letter in column_letters:
        column_number = (
            column_number * 26
            + ord(letter)
            - ord("A")
            + 1
        )

    x_coordinate = float(column_number)
    if half_column_marker:
        x_coordinate += 0.5

    return x_coordinate, float(row_text)


def load_graph_data(
    node_csv: str | Path,
    edge_csv: str | Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load the verified node and edge tables and perform basic checks."""
    node_csv = Path(node_csv)
    edge_csv = Path(edge_csv)

    if not node_csv.exists():
        raise FileNotFoundError(f"Node CSV was not found: {node_csv}")

    if not edge_csv.exists():
        raise FileNotFoundError(f"Edge CSV was not found: {edge_csv}")

    nodes = pd.read_csv(node_csv)
    edges = pd.read_csv(edge_csv)

    missing_node_columns = REQUIRED_NODE_COLUMNS - set(nodes.columns)
    missing_edge_columns = REQUIRED_EDGE_COLUMNS - set(edges.columns)

    if missing_node_columns:
        raise ValueError(
            "Node CSV is missing required columns: "
            + ", ".join(sorted(missing_node_columns))
        )

    if missing_edge_columns:
        raise ValueError(
            "Edge CSV is missing required columns: "
            + ", ".join(sorted(missing_edge_columns))
        )

    # Every node ID must identify exactly one physical graph point.
    duplicate_node_ids = nodes.loc[
        nodes["node_id"].astype(str).duplicated(keep=False),
        "node_id",
    ].astype(str).unique()

    if len(duplicate_node_ids) > 0:
        raise ValueError(
            "Duplicate node IDs were found: "
            + ", ".join(sorted(duplicate_node_ids))
        )

    # Distances are the Dijkstra/A* edge weights, so they must be positive.
    if (pd.to_numeric(edges["distance"], errors="coerce") <= 0).any():
        raise ValueError("Every edge distance must be greater than zero.")

    if pd.to_numeric(edges["distance"], errors="coerce").isna().any():
        raise ValueError("Every edge distance must be numeric.")

    capacities = pd.to_numeric(edges["capacity"], errors="coerce")
    if capacities.isna().any():
        raise ValueError("Every edge capacity must be numeric.")
    if (capacities <= 0).any():
        raise ValueError("Every edge capacity must be greater than zero.")

    undirected_pairs = edges.apply(
        lambda row: tuple(sorted((str(row["source"]), str(row["target"])))),
        axis=1,
    )
    if undirected_pairs.duplicated().any():
        raise ValueError("Duplicate undirected graph edges were found.")

    if (edges["source"].astype(str) == edges["target"].astype(str)).any():
        raise ValueError("Self-loop graph edges are not allowed.")

    return nodes, edges


def build_navigation_graph(
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
) -> nx.Graph:
    """Build an undirected, weighted navigation graph.

    The floor plan currently treats movement as bidirectional. Therefore,
    ``nx.Graph`` is used instead of ``nx.DiGraph``.

    Later, this can be changed to a directed graph if a hallway or stairwell
    should allow movement in only one direction.
    """
    graph = nx.Graph()

    # Add the nodes first so that each graph node retains useful metadata.
    for row in nodes.itertuples(index=False):
        node_id = str(row.node_id)

        graph.add_node(
            node_id,
            node_type=str(row.node_type),
            grid_position=str(row.grid_position),
            description=str(row.description),
            space_type=str(row.space_type),
            space_id="" if pd.isna(row.space_id) else str(row.space_id),
            space_name="" if pd.isna(row.space_name) else str(row.space_name),
            room_id="" if pd.isna(row.room_id) else str(row.room_id),
            room_name="" if pd.isna(row.room_name) else str(row.room_name),
            position=grid_position_to_xy(str(row.grid_position)),
        )

    known_node_ids = set(graph.nodes)

    # Every edge endpoint must refer to a node that exists in the node CSV.
    referenced_node_ids = (
        set(edges["source"].astype(str))
        | set(edges["target"].astype(str))
    )
    missing_endpoint_ids = sorted(referenced_node_ids - known_node_ids)

    if missing_endpoint_ids:
        raise ValueError(
            "The edge table references missing node IDs: "
            + ", ".join(missing_endpoint_ids)
        )

    # Add exactly the legal movements listed in the verified edge table.
    for row in edges.itertuples(index=False):
        graph.add_edge(
            str(row.source),
            str(row.target),
            # NetworkX shortest-path functions will minimize this value.
            weight=float(row.distance),
            distance=float(row.distance),
            capacity=int(row.capacity),
            edge_type=str(row.edge_type),
            notes=str(row.notes),
        )

    return graph


def validate_graph_connectivity(graph: nx.Graph) -> dict:
    """Return checks that should pass before shortest paths are trusted."""
    room_starts = [
        node_id
        for node_id, attributes in graph.nodes(data=True)
        if attributes.get("node_type") == "room_start"
    ]

    exits = [
        node_id
        for node_id, attributes in graph.nodes(data=True)
        if attributes.get("node_type") == "exit"
    ]

    doors = [
        node_id
        for node_id, attributes in graph.nodes(data=True)
        if attributes.get("node_type") == "door"
    ]

    reachability = {
        room_start: {
            exit_node: nx.has_path(graph, room_start, exit_node)
            for exit_node in exits
        }
        for room_start in room_starts
    }

    connected_components = list(nx.connected_components(graph))
    isolated_nodes = sorted(nx.isolates(graph))

    return {
        "node_count": graph.number_of_nodes(),
        "edge_count": graph.number_of_edges(),
        "connected_components": len(connected_components),
        "component_sizes": sorted(
            (len(component) for component in connected_components),
            reverse=True,
        ),
        "isolated_nodes": isolated_nodes,
        "all_rooms_reach_all_exits": all(
            all(exit_results.values())
            for exit_results in reachability.values()
        ),
        "door_degrees": {
            door_node: graph.degree[door_node]
            for door_node in doors
        },
        # Most doorway nodes connect one room-side point to one hallway-side
        # point and therefore have degree 2. Some verified layouts use one
        # physical doorway as a straight junction. FP03 DOOR_19 has four
        # verified straight connections after the room-start link is included.
        "all_doors_have_degree_2": all(
            graph.degree[door_node] == 2
            for door_node in doors
        ),
        "all_doors_have_valid_degree": all(
            graph.degree[door_node] in {2, 3}
            or (door_node == "DOOR_19" and graph.degree[door_node] == 4)
            for door_node in doors
        ),
        "reachability": reachability,
    }
