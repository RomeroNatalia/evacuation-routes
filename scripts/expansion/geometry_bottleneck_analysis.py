"""Geometric / topological comparison of the five floorplans.

Answers: how many points (nodes), how long are the evacuation-route and
corridor chains, how symmetric is each layout, how many rooms/exits/hallway
nodes are there, and -- the central question -- can we quantify bottlenecks,
and how.

Bottleneck definition (three complementary, independently-motivated measures;
no single number captures "bottleneck-ness" so we report all three):

1. CAPACITY BOTTLENECK -- reuses the paper's own quantity. For edge k,
   maximum_feasible_load[k] = sum over rooms of (the largest normalized load
   any one of that room's candidate routes would put on edge k). This is
   exactly what solve_qubo_neal.compute_objective_scales() computes to build
   the congestion-scale normalizer -- it is the worst case simultaneous
   utilization if every room chose whichever of its routes taxes this edge
   hardest. An edge with maximum_feasible_load > 1 cannot be avoided being a
   real capacity risk under *some* feasible assignment. This measure is
   already in the paper's math; we're just reporting it as a per-edge ranking
   rather than only using it to build S_C.

2. TRAFFIC-CONCENTRATION BOTTLENECK -- for edge k, route_multiplicity[k] =
   the number of distinct room-exit candidate routes that use it. This is a
   pure graph/topology measure independent of occupancy or capacity: it asks
   "how many different rooms' evacuation plans could possibly converge on
   this single edge," regardless of how much capacity it has. High
   multiplicity edges are structural convergence points a floorplan can't
   route around even before capacity is considered.

3. STRUCTURAL BOTTLENECK -- bridge edges (edges whose removal disconnects the
   navigation graph) and articulation points (cut vertices) in the raw
   building graph. A bridge that lies on the only path from >=2 rooms to
   every exit is a literal single point of failure: no candidate route can
   avoid it. This is orthogonal to (1) and (2) -- a bridge can have ample
   capacity and low traffic and still be structurally fragile.

Geometry uses each node's `grid_position` field (e.g. "E3", "D3.5") as a 2D
coordinate: letters -> column index, trailing number -> row (half-integer
positions from door nodes are kept as floats). Symmetry is measured by
best-fit reflective symmetry: for the horizontal and vertical mirror axes
through the node-set centroid, what fraction of nodes have a matching
same-type node at the mirrored position (within tolerance)? 1.0 = perfect
symmetry, 0.0 = none.

Usage:

    python scripts/expansion/geometry_bottleneck_analysis.py
"""

from __future__ import annotations

import csv
import json
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

import networkx as nx
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
FLOORPLANS = ["FP01", "FP02", "FP03", "FP04", "FP05"]
POSITION_TOLERANCE = 0.51  # grid units; half-integer door positions need >0.5


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def col_letters_to_index(letters: str) -> int:
    """Excel-style column parsing: A=0, B=1, ..., Z=25, AA=26, ..."""
    value = 0
    for ch in letters.upper():
        value = value * 26 + (ord(ch) - ord("A") + 1)
    return value - 1


_GRID_RE = re.compile(r"([A-Za-z]+)_?([A-Za-z]*)(\d+(?:\.\d+)?)")


def parse_grid_position(raw: str):
    """Return (x, y) or None if unparseable. Handles the rare 'E_A9' door
    notation (two letter groups separated by underscore) by using the first
    letter group as the column, matching the convention used elsewhere in
    the same floorplan's node set."""
    m = _GRID_RE.match(raw)
    if not m:
        return None
    letters = m.group(1)
    number = float(m.group(3))
    return float(col_letters_to_index(letters)), number


def load_floorplan(fp: str):
    input_dir = ROOT / "data" / "floorplans" / fp / "input"
    output_dir = ROOT / "data" / "floorplans" / fp / "output"

    nodes = read_csv(input_dir / "graph_nodes.csv")
    edges = read_csv(input_dir / "graph_edges.csv")
    routes = read_csv(output_dir / "route_catalog.csv")
    edge_rows = read_csv(output_dir / "edge_index.csv")
    weighted_rows = read_csv(output_dir / "occupancy_weighted_edge_route_matrix.csv")

    return nodes, edges, routes, edge_rows, weighted_rows


def build_position_map(nodes) -> Dict[str, Tuple[float, float]]:
    positions = {}
    for n in nodes:
        parsed = parse_grid_position(n["grid_position"])
        if parsed is not None:
            positions[n["node_id"]] = parsed
    return positions


def compute_node_counts(nodes) -> Dict[str, int]:
    type_counts = Counter(n["node_type"] for n in nodes)
    nav_nodes = [n for n in nodes if n["node_type"] == "navigation"]
    space_counts = Counter(n["space_type"] for n in nav_nodes)
    return {
        "total_nodes": len(nodes),
        "rooms": type_counts.get("room_start", 0),
        "exits": type_counts.get("exit", 0),
        "doors": type_counts.get("door", 0),
        "navigation_nodes_total": type_counts.get("navigation", 0),
        "navigation_in_room": space_counts.get("room", 0),
        "navigation_hallway": space_counts.get("hallway", 0),
    }


def compute_chain_lengths(routes, nodes, edges) -> Dict[str, object]:
    route_hops = [int(r["edge_count"]) for r in routes]
    route_distance = [float(r["distance"]) for r in routes]

    # Corridor-only subgraph diameter: longest shortest-path (in hops) among
    # pure hallway navigation nodes, using only navigation-type edges.
    hallway_ids = {n["node_id"] for n in nodes if n["node_type"] == "navigation" and n["space_type"] == "hallway"}
    G = nx.Graph()
    G.add_nodes_from(hallway_ids)
    for e in edges:
        if e["edge_type"] == "navigation" and e["source"] in hallway_ids and e["target"] in hallway_ids:
            G.add_edge(e["source"], e["target"])

    if G.number_of_nodes() > 0:
        components = list(nx.connected_components(G))
        largest = max(components, key=len)
        subG = G.subgraph(largest)
        corridor_diameter = nx.diameter(subG) if subG.number_of_nodes() > 1 else 0
        n_corridor_components = len(components)
    else:
        corridor_diameter = 0
        n_corridor_components = 0

    return {
        "route_hops_mean": statistics.mean(route_hops),
        "route_hops_median": statistics.median(route_hops),
        "route_hops_min": min(route_hops),
        "route_hops_max": max(route_hops),
        "route_hops_std": statistics.pstdev(route_hops),
        "route_distance_mean": statistics.mean(route_distance),
        "route_distance_max": max(route_distance),
        "corridor_node_count": len(hallway_ids),
        "corridor_connected_components": n_corridor_components,
        "corridor_diameter_hops": corridor_diameter,
    }


def compute_symmetry(nodes, positions) -> Dict[str, float]:
    typed_points = defaultdict(list)
    for n in nodes:
        pos = positions.get(n["node_id"])
        if pos is not None:
            typed_points[n["node_type"]].append(pos)

    all_points = [p for pts in typed_points.values() for p in pts]
    if not all_points:
        return {"vertical_mirror_score": 0.0, "horizontal_mirror_score": 0.0, "point_reflection_score": 0.0}

    xs = [p[0] for p in all_points]
    ys = [p[1] for p in all_points]
    cx = (min(xs) + max(xs)) / 2.0
    cy = (min(ys) + max(ys)) / 2.0

    def match_fraction(transform) -> float:
        matched = 0
        total = 0
        for node_type, pts in typed_points.items():
            point_set = set((round(x, 1), round(y, 1)) for x, y in pts)
            for (x, y) in pts:
                total += 1
                tx, ty = transform(x, y)
                # search a small neighborhood for a same-type point (tolerant match)
                found = any(
                    abs(tx - px) <= POSITION_TOLERANCE and abs(ty - py) <= POSITION_TOLERANCE
                    for (px, py) in point_set
                )
                if found:
                    matched += 1
        return matched / total if total else 0.0

    vertical_mirror = match_fraction(lambda x, y: (2 * cx - x, y))       # mirror across vertical axis
    horizontal_mirror = match_fraction(lambda x, y: (x, 2 * cy - y))     # mirror across horizontal axis
    point_reflection = match_fraction(lambda x, y: (2 * cx - x, 2 * cy - y))  # 180-degree rotation

    return {
        "vertical_mirror_score": vertical_mirror,
        "horizontal_mirror_score": horizontal_mirror,
        "point_reflection_score": point_reflection,
        "best_symmetry_score": max(vertical_mirror, horizontal_mirror, point_reflection),
    }


def compute_capacity_bottlenecks(routes, edge_rows, weighted_rows, edge_ids) -> Dict[str, object]:
    """maximum_feasible_load[k], exactly as in compute_objective_scales."""
    room_indices = defaultdict(list)
    for i, r in enumerate(routes):
        room_indices[r["room_id"]].append(i)

    capacity_by_edge = {row["edge_id"]: float(row["capacity_units"]) * 10.0 for row in edge_rows}
    n_edges = len(edge_ids)
    weighted_incidence = np.zeros((len(routes), n_edges), dtype=float)
    for i, row in enumerate(weighted_rows):
        for k, edge_id in enumerate(edge_ids):
            weighted_incidence[i, k] = float(row[edge_id])
    capacities = np.array([capacity_by_edge[e] for e in edge_ids], dtype=float)
    normalized_load = weighted_incidence / capacities

    max_feasible_load = np.zeros(n_edges, dtype=float)
    for idxs in room_indices.values():
        max_feasible_load += np.max(normalized_load[idxs, :], axis=0)

    over_capacity_edges = int(np.sum(max_feasible_load > 1.0))
    top_idx = np.argsort(max_feasible_load)[::-1][:5]

    return {
        "capacity_bottleneck_edge_count_over_1x": over_capacity_edges,
        "capacity_bottleneck_max_feasible_load_max": float(max_feasible_load.max()),
        "capacity_bottleneck_max_feasible_load_mean": float(max_feasible_load.mean()),
        "capacity_bottleneck_top5_edges": [
            {"edge_id": edge_ids[i], "max_feasible_load": float(max_feasible_load[i])}
            for i in top_idx
        ],
    }


def compute_traffic_bottlenecks(routes, edge_ids) -> Dict[str, object]:
    multiplicity = Counter()
    for r in routes:
        for token in r["edge_ids"].split(" | "):
            multiplicity[token] += 1

    n_rooms = len(set(r["room_id"] for r in routes))
    if not multiplicity:
        return {"traffic_bottleneck_max_multiplicity": 0, "traffic_bottleneck_top1_share": 0.0}

    max_mult, max_edge = max((v, k) for k, v in multiplicity.items())
    top5 = sorted(multiplicity.items(), key=lambda kv: -kv[1])[:5]

    return {
        "traffic_bottleneck_max_multiplicity": max_mult,
        "traffic_bottleneck_max_multiplicity_edge": max_edge,
        "traffic_bottleneck_top1_share_of_rooms": max_mult / n_rooms,
        "traffic_bottleneck_top5_edges": [{"edge_id": k, "route_multiplicity": v} for k, v in top5],
    }


def compute_structural_bottlenecks(nodes, edges, routes) -> Dict[str, object]:
    G = nx.Graph()
    for n in nodes:
        G.add_node(n["node_id"])
    for e in edges:
        G.add_edge(e["source"], e["target"])

    # Restrict to the largest connected component for bridge/articulation analysis.
    largest_cc = max(nx.connected_components(G), key=len)
    subG = G.subgraph(largest_cc).copy()

    bridges = list(nx.bridges(subG))
    articulation_points = list(nx.articulation_points(subG))

    bridge_set = {frozenset(b) for b in bridges}

    # A "critical bridge" is a bridge that appears on >=2 distinct rooms'
    # candidate routes -- i.e. a literal single point of failure for more
    # than one room, not just an unavoidable dead-end for one room's own
    # start node.
    room_sets_per_bridge = defaultdict(set)
    for r in routes:
        path_nodes = r["path"].split(" -> ")
        for a, b in zip(path_nodes, path_nodes[1:]):
            key = frozenset((a, b))
            if key in bridge_set:
                room_sets_per_bridge[key].add(r["room_id"])

    critical_bridges = {k: v for k, v in room_sets_per_bridge.items() if len(v) >= 2}
    max_rooms_on_single_bridge = max((len(v) for v in room_sets_per_bridge.values()), default=0)

    return {
        "structural_bridge_count": len(bridges),
        "structural_articulation_point_count": len(articulation_points),
        "structural_critical_bridge_count": len(critical_bridges),
        "structural_max_rooms_sharing_one_bridge": max_rooms_on_single_bridge,
    }


def analyze_floorplan(fp: str) -> Dict[str, object]:
    nodes, edges, routes, edge_rows, weighted_rows = load_floorplan(fp)
    edge_ids = [r["edge_id"] for r in edge_rows]
    positions = build_position_map(nodes)

    result = {"floorplan": fp}
    result.update(compute_node_counts(nodes))
    result.update(compute_chain_lengths(routes, nodes, edges))
    result.update(compute_symmetry(nodes, positions))
    result.update(compute_capacity_bottlenecks(routes, edge_rows, weighted_rows, edge_ids))
    result.update(compute_traffic_bottlenecks(routes, edge_ids))
    result.update(compute_structural_bottlenecks(nodes, edges, routes))
    return result


def main() -> None:
    results = [analyze_floorplan(fp) for fp in FLOORPLANS]

    out_json = ROOT / "docs" / "expansion_geometry_bottleneck_raw.json"
    out_json.write_text(json.dumps(results, indent=2), encoding="utf-8")

    header = (
        f"{'FP':5}{'rooms':>6}{'exits':>6}{'hallwyNd':>9}{'corrDiam':>9}"
        f"{'hops(mean/max)':>16}{'symmetry':>9}{'capBN>1x':>9}{'trafficMax%':>12}"
        f"{'bridges':>8}{'critBridge':>11}"
    )
    lines = [header]
    for r in results:
        lines.append(
            f"{r['floorplan']:5}{r['rooms']:6}{r['exits']:6}{r['navigation_hallway']:9}"
            f"{r['corridor_diameter_hops']:9}"
            f"{r['route_hops_mean']:8.1f}/{r['route_hops_max']:<6}"
            f"{r['best_symmetry_score']:9.2f}{r['capacity_bottleneck_edge_count_over_1x']:9}"
            f"{100*r['traffic_bottleneck_top1_share_of_rooms']:11.1f}%"
            f"{r['structural_bridge_count']:8}{r['structural_critical_bridge_count']:11}"
        )
    table = "\n".join(lines)
    print(table)

    (ROOT / "docs" / "expansion_geometry_table.txt").write_text(table + "\n", encoding="utf-8")
    print(f"\nWritten to {out_json}")


if __name__ == "__main__":
    main()
