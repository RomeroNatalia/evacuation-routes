"""Static occupancy and congestion analysis for the evacuation graph.

This phase builds directly on the classical Dijkstra results.

Current capacity assumption
---------------------------
Edge capacities in the graph are relative values. For this first model:

    1 capacity unit = 10 people per evacuation wave

This is deliberately configurable and should later be replaced with
measured people-per-second values when doorway and hallway dimensions are
available.
"""

from __future__ import annotations

from collections import Counter
import math

import networkx as nx
import pandas as pd


PEOPLE_PER_CAPACITY_UNIT = 10.0
CONGESTION_WEIGHT = 5.0


def path_text_to_nodes(path_text: str) -> list[str]:
    """Convert ``A -> B -> C`` into ``["A", "B", "C"]``."""
    return [
        node_id.strip()
        for node_id in str(path_text).split("->")
        if node_id.strip()
    ]


def path_nodes_to_edges(
    path_nodes: list[str],
) -> list[tuple[str, str]]:
    """Convert an ordered path into normalized undirected edges."""
    return [
        tuple(sorted((source, target)))
        for source, target in zip(
            path_nodes[:-1],
            path_nodes[1:],
        )
    ]


def load_room_occupancy(
    occupancy_csv: str,
) -> pd.DataFrame:
    """Load and validate the occupancy table."""
    occupancy = pd.read_csv(occupancy_csv)

    required = {
        "room_id",
        "room_name",
        "capacity",
        "occupancy",
    }
    missing = required - set(occupancy.columns)

    if missing:
        raise ValueError(
            "Occupancy CSV is missing columns: "
            + ", ".join(sorted(missing))
        )

    if occupancy["room_id"].duplicated().any():
        raise ValueError("Each room must appear exactly once.")

    if (occupancy["occupancy"] < 0).any():
        raise ValueError("Occupancy cannot be negative.")

    if (occupancy["capacity"] <= 0).any():
        raise ValueError("Capacity must be positive.")

    if (occupancy["occupancy"] > occupancy["capacity"]).any():
        raise ValueError(
            "At least one room occupancy exceeds room capacity."
        )

    return occupancy


def assign_occupants_to_routes(
    routes: pd.DataFrame,
    occupancy: pd.DataFrame,
) -> pd.DataFrame:
    """Attach each room's occupancy to its selected route."""
    assigned = routes.merge(
        occupancy[["room_id", "capacity", "occupancy"]],
        on="room_id",
        how="left",
        validate="one_to_one",
    )

    if assigned["occupancy"].isna().any():
        missing_rooms = assigned.loc[
            assigned["occupancy"].isna(),
            "room_id",
        ].tolist()

        raise ValueError(
            "Missing occupancy for rooms: "
            + ", ".join(missing_rooms)
        )

    return assigned


def compute_edge_loads(
    graph: nx.Graph,
    assigned_routes: pd.DataFrame,
    people_per_capacity_unit: float = PEOPLE_PER_CAPACITY_UNIT,
) -> pd.DataFrame:
    """Count occupants using every edge and calculate utilization."""
    edge_loads: Counter = Counter()
    room_counts: Counter = Counter()

    for route in assigned_routes.itertuples(index=False):
        occupants = int(route.occupancy)
        path_nodes = path_text_to_nodes(str(route.path))

        for edge in path_nodes_to_edges(path_nodes):
            edge_loads[edge] += occupants
            room_counts[edge] += 1

    rows = []

    for source, target, attributes in graph.edges(data=True):
        edge = tuple(sorted((source, target)))
        occupants = int(edge_loads.get(edge, 0))
        capacity_units = float(attributes.get("capacity", 1))
        effective_capacity = (
            capacity_units * people_per_capacity_unit
        )
        utilization = (
            occupants / effective_capacity
            if effective_capacity > 0
            else math.inf
        )

        rows.append(
            {
                "source": source,
                "target": target,
                "edge_type": attributes.get("edge_type", ""),
                "distance": float(attributes.get("distance", 0.0)),
                "capacity_units": capacity_units,
                "effective_capacity_people": effective_capacity,
                "occupants_using_edge": occupants,
                "rooms_using_edge": int(room_counts.get(edge, 0)),
                "utilization_ratio": utilization,
                "utilization_percent": utilization * 100.0,
                "is_congested": utilization > 1.0,
            }
        )

    return pd.DataFrame(rows).sort_values(
        ["is_congested", "utilization_ratio"],
        ascending=[False, False],
    )


def compute_node_loads(
    graph: nx.Graph,
    assigned_routes: pd.DataFrame,
    people_per_capacity_unit: float = PEOPLE_PER_CAPACITY_UNIT,
) -> pd.DataFrame:
    """Count occupants passing through doors, hallways, and exits."""
    node_loads: Counter = Counter()
    room_counts: Counter = Counter()

    for route in assigned_routes.itertuples(index=False):
        occupants = int(route.occupancy)
        path_nodes = set(
            path_text_to_nodes(str(route.path))
        )

        for node_id in path_nodes:
            node_loads[node_id] += occupants
            room_counts[node_id] += 1

    rows = []

    for node_id, attributes in graph.nodes(data=True):
        node_type = attributes.get("node_type", "")

        if node_type not in {
            "navigation",
            "door",
            "exit",
        }:
            continue

        incident_capacities = [
            float(edge_attributes.get("capacity", 1))
            for _, _, edge_attributes
            in graph.edges(node_id, data=True)
        ]

        capacity_units = (
            min(incident_capacities)
            if incident_capacities
            else 1.0
        )

        effective_capacity = (
            capacity_units * people_per_capacity_unit
        )

        occupants = int(node_loads.get(node_id, 0))
        utilization = (
            occupants / effective_capacity
            if effective_capacity > 0
            else math.inf
        )

        rows.append(
            {
                "node_id": node_id,
                "node_type": node_type,
                "grid_position": attributes.get(
                    "grid_position",
                    "",
                ),
                "capacity_units": capacity_units,
                "effective_capacity_people": effective_capacity,
                "occupants_using_node": occupants,
                "rooms_using_node": int(
                    room_counts.get(node_id, 0)
                ),
                "utilization_ratio": utilization,
                "utilization_percent": utilization * 100.0,
                "is_congested": utilization > 1.0,
            }
        )

    return pd.DataFrame(rows).sort_values(
        ["is_congested", "utilization_ratio"],
        ascending=[False, False],
    )



def _exit_nodes(graph: nx.Graph) -> list[str]:
    """Return all exit node IDs in stable order."""
    return sorted(
        node_id
        for node_id, attributes in graph.nodes(data=True)
        if attributes.get("node_type") == "exit"
    )


def projected_edge_cost(
    attributes: dict,
    current_load: int,
    added_occupants: int,
    people_per_capacity_unit: float,
    congestion_weight: float,
) -> float:
    """Return the risk-aware Dijkstra weight for one edge.

    The edge cost is fixed during one room's Dijkstra run:

        edge cost = distance + congestion_weight * projected_utilization^2

    Projected utilization includes the occupants from the room currently being
    routed. Consequently, Dijkstra can choose a different hallway path to the
    same exit, not merely a different precomputed exit route.
    """
    distance = float(attributes.get("distance", attributes.get("weight", 1.0)))
    capacity_units = float(attributes.get("capacity", 1.0))
    effective_capacity = capacity_units * people_per_capacity_unit

    if effective_capacity <= 0:
        return math.inf

    projected_load = current_load + added_occupants
    projected_utilization = projected_load / effective_capacity
    congestion_penalty = congestion_weight * projected_utilization**2
    return distance + congestion_penalty


def choose_congestion_aware_dijkstra_routes(
    graph: nx.Graph,
    occupancy: pd.DataFrame,
    people_per_capacity_unit: float = PEOPLE_PER_CAPACITY_UNIT,
    congestion_weight: float = CONGESTION_WEIGHT,
) -> pd.DataFrame:
    """Route rooms with repeated congestion-aware Dijkstra searches.

    Rooms are processed from highest occupancy to lowest occupancy. Before each
    room is assigned, Dijkstra receives a dynamic edge-weight function based on
    the occupants already assigned plus the occupants in the current room.

    This remains a greedy multi-room heuristic because earlier room decisions
    are not revisited, but each individual path is a genuine Dijkstra shortest
    path under the current congestion-aware edge weights.
    """
    room_rows = occupancy.sort_values(
        by=["occupancy", "room_id"],
        ascending=[False, True],
    )
    exits = _exit_nodes(graph)
    current_edge_loads: Counter = Counter()
    selected_rows: list[dict] = []

    for room in room_rows.itertuples(index=False):
        room_id = str(room.room_id)
        occupants = int(room.occupancy)
        start_node = f"START_{room_id}"

        if start_node not in graph:
            matching_starts = [
                node_id
                for node_id, attributes in graph.nodes(data=True)
                if attributes.get("node_type") == "room_start"
                and attributes.get("room_id") == room_id
            ]
            if len(matching_starts) != 1:
                raise ValueError(
                    f"Could not identify one room-start node for {room_id}."
                )
            start_node = matching_starts[0]

        def risk_weight(source: str, target: str, attributes: dict) -> float:
            edge = tuple(sorted((source, target)))
            return projected_edge_cost(
                attributes=attributes,
                current_load=int(current_edge_loads.get(edge, 0)),
                added_occupants=occupants,
                people_per_capacity_unit=people_per_capacity_unit,
                congestion_weight=congestion_weight,
            )

        candidates: list[dict] = []

        for exit_node in exits:
            path_nodes = nx.dijkstra_path(
                graph,
                source=start_node,
                target=exit_node,
                weight=risk_weight,
            )
            risk_aware_cost = 0.0
            physical_distance = 0.0
            congestion_penalty = 0.0

            for source, target in zip(path_nodes[:-1], path_nodes[1:]):
                attributes = graph[source][target]
                edge = tuple(sorted((source, target)))
                distance = float(
                    attributes.get("distance", attributes.get("weight", 1.0))
                )
                edge_cost = projected_edge_cost(
                    attributes=attributes,
                    current_load=int(current_edge_loads.get(edge, 0)),
                    added_occupants=occupants,
                    people_per_capacity_unit=people_per_capacity_unit,
                    congestion_weight=congestion_weight,
                )
                risk_aware_cost += edge_cost
                physical_distance += distance
                congestion_penalty += edge_cost - distance

            candidates.append(
                {
                    "room_id": room_id,
                    "room_name": str(room.room_name),
                    "start_node": start_node,
                    "occupancy": occupants,
                    "selected_exit": exit_node,
                    "distance": physical_distance,
                    "congestion_penalty": congestion_penalty,
                    "combined_cost": risk_aware_cost,
                    "hops": len(path_nodes) - 1,
                    "path": " -> ".join(path_nodes),
                }
            )

        selected = min(
            candidates,
            key=lambda row: (
                row["combined_cost"],
                row["distance"],
                row["selected_exit"],
            ),
        )
        selected_rows.append(selected)

        for edge in path_nodes_to_edges(path_text_to_nodes(selected["path"])):
            current_edge_loads[edge] += occupants

    return pd.DataFrame(selected_rows).sort_values("room_id")


def compare_routes(
    classical_routes: pd.DataFrame,
    congestion_routes: pd.DataFrame,
) -> pd.DataFrame:
    """Compare distance-only Dijkstra with congestion-aware Dijkstra."""
    classical = classical_routes[
        ["room_id", "primary_exit", "distance", "hops", "path"]
    ].rename(
        columns={
            "primary_exit": "classical_exit",
            "distance": "classical_distance",
            "hops": "classical_hops",
            "path": "classical_path",
        }
    )

    congestion = congestion_routes[
        [
            "room_id",
            "occupancy",
            "selected_exit",
            "distance",
            "hops",
            "congestion_penalty",
            "combined_cost",
            "path",
        ]
    ].rename(
        columns={
            "selected_exit": "congestion_aware_exit",
            "distance": "congestion_aware_distance",
            "hops": "congestion_aware_hops",
            "path": "congestion_aware_path",
        }
    )

    comparison = classical.merge(congestion, on="room_id", validate="one_to_one")
    comparison["exit_changed"] = (
        comparison["classical_exit"] != comparison["congestion_aware_exit"]
    )
    comparison["path_changed"] = (
        comparison["classical_path"] != comparison["congestion_aware_path"]
    )
    comparison["extra_distance"] = (
        comparison["congestion_aware_distance"]
        - comparison["classical_distance"]
    )
    comparison["extra_hops"] = (
        comparison["congestion_aware_hops"]
        - comparison["classical_hops"]
    )

    return comparison.sort_values("room_id")