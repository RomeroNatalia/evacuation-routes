"""Report diagonal and unusually long graph edges for one floorplan.

Examples:

    python scripts/audit_graph_geometry.py --floorplan FP02
    python scripts/audit_graph_geometry.py --floorplan FP03

This audit does not modify data. It helps identify source-target connections
that should be reviewed against the floorplan drawing before preprocessing.
"""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fire_evacuation.graph_io import grid_position_to_xy, load_graph_data  # noqa: E402
from fire_evacuation.project import floorplan_paths_from_argv  # noqa: E402

FLOORPLAN = floorplan_paths_from_argv(ROOT)


def main() -> None:
    nodes, edges = load_graph_data(FLOORPLAN.nodes_csv, FLOORPLAN.edges_csv)
    position_by_node = {
        str(row.node_id): grid_position_to_xy(str(row.grid_position))
        for row in nodes.itertuples(index=False)
    }

    diagonal = []
    long_edges = []

    for row in edges.itertuples(index=False):
        source = str(row.source)
        target = str(row.target)
        x1, y1 = position_by_node[source]
        x2, y2 = position_by_node[target]
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)

        if dx > 0 and dy > 0:
            diagonal.append((source, target, dx, dy, row.edge_type))

        manhattan = dx + dy
        if manhattan > 2.0:
            long_edges.append((source, target, manhattan, row.edge_type))

    print(f"Floorplan: {FLOORPLAN.floorplan_id}")
    print(f"Nodes: {len(nodes)}")
    print(f"Edges: {len(edges)}")
    print(f"Diagonal edges: {len(diagonal)}")
    print(f"Edges longer than 2 grid units: {len(long_edges)}")

    if diagonal:
        print("\nDIAGONAL EDGES")
        for source, target, dx, dy, edge_type in diagonal:
            print(
                f"- {source} -- {target} | dx={dx:g}, dy={dy:g} | {edge_type}"
            )

    if long_edges:
        print("\nLONG EDGES TO REVIEW")
        for source, target, length, edge_type in long_edges:
            print(
                f"- {source} -- {target} | Manhattan length={length:g} | {edge_type}"
            )

    if not diagonal:
        print("\nPASS: every edge is horizontal or vertical.")


if __name__ == "__main__":
    main()
