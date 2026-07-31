"""Classical shortest-path routing with Dijkstra and A*."""

from __future__ import annotations

import math

import networkx as nx
import pandas as pd


def euclidean_heuristic(
    graph: nx.Graph,
    current_node: str,
    goal_node: str,
) -> float:
    """Return an admissible straight-line A* estimate.

    Some floorplans use schematic grid coordinates whose geometric spacing is
    larger than the stored travel-distance units. Raw Euclidean distance can
    therefore overestimate the true path cost. To keep A* admissible for every
    included dataset, the straight-line distance is multiplied by the smallest
    edge-cost-to-geometric-length ratio in the graph.
    """
    scale = graph.graph.get("astar_distance_scale")
    if scale is None:
        ratios: list[float] = []
        for source, target, attributes in graph.edges(data=True):
            source_x, source_y = graph.nodes[source]["position"]
            target_x, target_y = graph.nodes[target]["position"]
            geometric_length = math.hypot(
                source_x - target_x,
                source_y - target_y,
            )
            if geometric_length > 0:
                edge_cost = float(
                    attributes.get("weight", attributes.get("distance", 1.0))
                )
                ratios.append(edge_cost / geometric_length)

        scale = min(ratios, default=0.0)
        # A tiny downward tolerance avoids floating-point overestimation.
        scale = max(0.0, float(scale) * (1.0 - 1e-12))
        graph.graph["astar_distance_scale"] = scale

    current_x, current_y = graph.nodes[current_node]["position"]
    goal_x, goal_y = graph.nodes[goal_node]["position"]
    return float(scale) * math.hypot(
        current_x - goal_x,
        current_y - goal_y,
    )


def _room_start_nodes(graph: nx.Graph) -> list[str]:
    """Return room-start IDs in a stable, human-readable order."""
    return sorted(
        node_id
        for node_id, attributes in graph.nodes(data=True)
        if attributes.get("node_type") == "room_start"
    )


def _exit_nodes(graph: nx.Graph) -> list[str]:
    """Return exit IDs in a stable order."""
    return sorted(
        node_id
        for node_id, attributes in graph.nodes(data=True)
        if attributes.get("node_type") == "exit"
    )


def compute_all_room_exit_routes(graph: nx.Graph) -> pd.DataFrame:
    """Compute Dijkstra and A* routes for every room-to-exit pair.

    Dijkstra is used as the classical baseline because it guarantees the
    shortest path when edge weights are nonnegative.

    A* is also computed as a verification and as preparation for larger
    graphs. A* should return the same minimum distance, though it may choose
    a different equally short path when ties exist.
    """
    result_rows: list[dict] = []

    for start_node in _room_start_nodes(graph):
        start_attributes = graph.nodes[start_node]

        for exit_node in _exit_nodes(graph):
            # Dijkstra explores the weighted graph without a heuristic.
            dijkstra_path = nx.dijkstra_path(
                graph,
                source=start_node,
                target=exit_node,
                weight="weight",
            )
            dijkstra_distance = nx.dijkstra_path_length(
                graph,
                source=start_node,
                target=exit_node,
                weight="weight",
            )

            # A* uses the same edge weights plus the straight-line estimate.
            astar_path = nx.astar_path(
                graph,
                source=start_node,
                target=exit_node,
                heuristic=lambda current, goal: euclidean_heuristic(
                    graph,
                    current,
                    goal,
                ),
                weight="weight",
            )
            astar_distance = nx.path_weight(
                graph,
                astar_path,
                weight="weight",
            )

            # Floating-point numbers should be compared with a tolerance,
            # not the == operator.
            distances_match = math.isclose(
                dijkstra_distance,
                astar_distance,
                rel_tol=1e-9,
                abs_tol=1e-9,
            )

            result_rows.append(
                {
                    "room_id": start_attributes.get("room_id", ""),
                    "room_name": start_attributes.get("room_name", ""),
                    "start_node": start_node,
                    "exit_node": exit_node,
                    "dijkstra_distance": dijkstra_distance,
                    "astar_distance": astar_distance,
                    "distances_match": distances_match,
                    "same_exact_path": dijkstra_path == astar_path,
                    "dijkstra_hops": len(dijkstra_path) - 1,
                    "astar_hops": len(astar_path) - 1,
                    "dijkstra_path": " -> ".join(dijkstra_path),
                    "astar_path": " -> ".join(astar_path),
                }
            )

    return pd.DataFrame(result_rows)


def choose_primary_routes(
    all_routes: pd.DataFrame,
) -> pd.DataFrame:
    """Choose the nearest exit for each room using Dijkstra distance.

    A deterministic tie-break is necessary for reproducible repository
    output. If two exits have the same weighted distance, the exit with the
    alphabetically earlier ID is selected.

    This is only the uncongested classical baseline. Later optimization
    stages may deliberately choose a longer route to reduce crowding.
    """
    required_columns = {
        "room_id",
        "room_name",
        "start_node",
        "exit_node",
        "dijkstra_distance",
        "dijkstra_hops",
        "dijkstra_path",
        "distances_match",
        "same_exact_path",
    }

    missing_columns = required_columns - set(all_routes.columns)
    if missing_columns:
        raise ValueError(
            "Route table is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )

    sorted_routes = all_routes.sort_values(
        by=["room_id", "dijkstra_distance", "exit_node"],
        ascending=[True, True, True],
    )

    primary = (
        sorted_routes
        .groupby("room_id", as_index=False)
        .first()
        .rename(
            columns={
                "exit_node": "primary_exit",
                "dijkstra_distance": "distance",
                "dijkstra_hops": "hops",
                "dijkstra_path": "path",
                "distances_match": "astar_matches_distance",
                "same_exact_path": "astar_same_exact_path",
            }
        )
    )

    return primary[
        [
            "room_id",
            "room_name",
            "start_node",
            "primary_exit",
            "distance",
            "hops",
            "path",
            "astar_matches_distance",
            "astar_same_exact_path",
        ]
    ]


def expand_primary_route_nodes(
    graph: nx.Graph,
    primary_routes: pd.DataFrame,
) -> pd.DataFrame:
    """Expand each route string into one row per ordered node.

    This format is easier to use later for:
    * animation,
    * congestion counting,
    * time-expanded graphs,
    * QUBO variable construction.
    """
    rows: list[dict] = []

    for route in primary_routes.itertuples(index=False):
        path_nodes = str(route.path).split(" -> ")

        for sequence_index, node_id in enumerate(path_nodes):
            node_attributes = graph.nodes[node_id]

            rows.append(
                {
                    "room_id": route.room_id,
                    "room_name": route.room_name,
                    "primary_exit": route.primary_exit,
                    "sequence_index": sequence_index,
                    "node_id": node_id,
                    "node_type": node_attributes.get("node_type", ""),
                    "grid_position": node_attributes.get(
                        "grid_position",
                        "",
                    ),
                }
            )

    return pd.DataFrame(rows)
