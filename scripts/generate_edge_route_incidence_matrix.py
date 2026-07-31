"""Generate edge-route incidence matrices for a selected evacuation floorplan.

Run from the repository root:

    python scripts/generate_edge_route_incidence_matrix.py

Inputs:
    data/floorplans/FPXX/input/graph_nodes.csv
    data/floorplans/FPXX/input/graph_edges.csv
    data/floorplans/FPXX/input/room_occupancy.csv

Outputs:
    data/floorplans/FPXX/output/edge_route_incidence_matrix.csv
    data/floorplans/FPXX/output/occupancy_weighted_edge_route_matrix.csv
    data/floorplans/FPXX/output/route_catalog.csv
    data/floorplans/FPXX/output/edge_index.csv
"""

from pathlib import Path
import pandas as pd
import networkx as nx
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from fire_evacuation.project import floorplan_paths_from_argv  # noqa: E402

FLOORPLAN = floorplan_paths_from_argv(ROOT)
OUTPUT_DIR = FLOORPLAN.output_dir


def main() -> None:
    node_path = FLOORPLAN.nodes_csv
    edge_path = FLOORPLAN.edges_csv
    occupancy_path = FLOORPLAN.occupancy_csv

    nodes = pd.read_csv(node_path)
    edges = pd.read_csv(edge_path)
    occupancy = pd.read_csv(occupancy_path)

    graph = nx.Graph()

    for row in nodes.itertuples(index=False):
        graph.add_node(
            str(row.node_id),
            node_type=str(row.node_type),
            room_id=None if pd.isna(row.room_id) else str(row.room_id),
            room_name=None if pd.isna(row.room_name) else str(row.room_name),
        )

    for row in edges.itertuples(index=False):
        graph.add_edge(
            str(row.source),
            str(row.target),
            distance=float(row.distance),
            capacity=float(row.capacity),
            edge_type=str(row.edge_type),
        )

    room_starts = nodes.loc[nodes["node_type"] == "room_start"].copy()
    exits = nodes.loc[nodes["node_type"] == "exit"].copy()

    occupancy_by_room = (
        occupancy.set_index("room_id")["occupancy"].to_dict()
    )

    # Each physical edge gets one stable column identifier.
    # The graph is undirected, so A--B and B--A refer to the same edge.
    edge_records = []
    edge_id_by_pair = {}

    for index, row in edges.iterrows():
        source = str(row["source"])
        target = str(row["target"])
        edge_id = f"E{index + 1:03d}:{source}--{target}"
        edge_id_by_pair[frozenset((source, target))] = edge_id

        edge_records.append(
            {
                "edge_id": edge_id,
                "source": source,
                "target": target,
                "distance": float(row["distance"]),
                "capacity_units": float(row["capacity"]),
                "edge_type": str(row["edge_type"]),
            }
        )

    binary_rows = []
    weighted_rows = []
    route_rows = []

    # There is one candidate route for every room-exit combination.
    for room in room_starts.itertuples(index=False):
        start_node = str(room.node_id)
        room_id = str(room.room_id)
        room_name = str(room.room_name)
        people = int(occupancy_by_room[room_id])

        for exit_row in exits.itertuples(index=False):
            exit_node = str(exit_row.node_id)
            route_id = f"{room_id}__{exit_node}"

            path = nx.dijkstra_path(
                graph,
                source=start_node,
                target=exit_node,
                weight="distance",
            )
            route_distance = nx.path_weight(
                graph,
                path,
                weight="distance",
            )

            used_edge_ids = []
            for source, target in zip(path[:-1], path[1:]):
                pair = frozenset((source, target))
                used_edge_ids.append(edge_id_by_pair[pair])

            used_edge_set = set(used_edge_ids)

            binary_row = {"route_id": route_id}
            weighted_row = {"route_id": route_id}

            for edge in edge_records:
                edge_id = edge["edge_id"]

                # A[r,e,k] = 1 when route (r,e) uses edge k.
                binary_row[edge_id] = int(edge_id in used_edge_set)

                # p_r * A[r,e,k] gives the number of people that
                # would load edge k if this route were selected.
                weighted_row[edge_id] = (
                    people if edge_id in used_edge_set else 0
                )

            binary_rows.append(binary_row)
            weighted_rows.append(weighted_row)

            route_rows.append(
                {
                    "route_id": route_id,
                    "room_id": room_id,
                    "room_name": room_name,
                    "start_node": start_node,
                    "exit_node": exit_node,
                    "occupancy": people,
                    "distance": float(route_distance),
                    "edge_count": len(used_edge_ids),
                    "path": " -> ".join(path),
                    "edge_ids": " | ".join(used_edge_ids),
                }
            )

    incidence = pd.DataFrame(binary_rows)
    weighted = pd.DataFrame(weighted_rows)
    routes = pd.DataFrame(route_rows)
    edge_index = pd.DataFrame(edge_records)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    incidence_path = (
        OUTPUT_DIR / "edge_route_incidence_matrix.csv"
    )
    weighted_path = (
        OUTPUT_DIR / "occupancy_weighted_edge_route_matrix.csv"
    )
    routes_path = OUTPUT_DIR / "route_catalog.csv"
    edge_index_path = OUTPUT_DIR / "edge_index.csv"

    incidence.to_csv(incidence_path, index=False)
    weighted.to_csv(weighted_path, index=False)
    routes.to_csv(routes_path, index=False)
    edge_index.to_csv(edge_index_path, index=False)

    print("EDGE-ROUTE INCIDENCE MATRIX CREATED")
    print(f"Candidate routes: {len(incidence)}")
    print(f"Physical edges:   {len(edge_records)}")
    print(f"Matrix shape:     {len(incidence)} x {len(edge_records)}")
    print()
    print(f"Binary matrix:   {incidence_path}")
    print(f"Weighted matrix: {weighted_path}")
    print(f"Route catalog:   {routes_path}")
    print(f"Edge index:      {edge_index_path}")
    print()
    print("Preview:")
    print(incidence.iloc[:5, :12].to_string(index=False))


if __name__ == "__main__":
    main()
