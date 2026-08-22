"""Generate a synthetic floorplan with a controlled corridor topology.

To confirm the FP02/FP03 root-cause hypothesis (structural bottleneck
density, not raw variable count, predicts optimality gap) statistically, we
need more than 5 data points, and ideally need to vary bottleneck density
*independently* of size rather than hoping naturally-occurring floorplans do
it for us. This generates floorplans in the exact same CSV schema as
FP01-FP05 (graph_nodes.csv, graph_edges.csv, room_occupancy.csv,
metadata.csv) with three controlled corridor topologies:

- "linear": a single corridor spine, rooms attached along its length, exits
  at the ends. Maximum structural bottleneck: nearly every corridor edge is
  a bridge shared by many rooms.
- "tree": a main spine with periodic branches, rooms on the branches. Some
  bottleneck (branch-point edges are shared by every room on that branch)
  but less than linear.
- "loop": corridor nodes form a rectangular ring, rooms attached around the
  outside, exits spaced around the ring. Minimal structural bottleneck: the
  ring means most corridor edges have an alternate path and are not bridges.

Known simplification (documented, not hidden): real floorplans have an
interior in-room navigation grid (multiple tiles per room, contributing
edge_type="room_start" edges and space_type="room" navigation nodes) that
this generator skips -- each room here is just room_start -> door ->
corridor directly. This does not distort the corridor-network structural
metrics (bridges, corridor diameter, route hop count through the shared
network) that the bottleneck hypothesis is actually about, but it does mean
route hop counts here are systematically shorter than the real floorplans'
(no in-room meandering) and the synthetic corpus should be analyzed for
within-corpus trends primarily, with the real 5 floorplans checked
separately for consistency of direction, not pooled as if identically
distributed.

Usage:

    python scripts/expansion/generate_synthetic_floorplan.py SYN01 --topology linear --rooms 12 --exits 2 --seed 1
"""

from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parents[2]

NODE_FIELDS = [
    "node_id", "node_type", "grid_position", "description",
    "space_type", "space_id", "space_name", "room_id", "room_name",
]
EDGE_FIELDS = ["source", "target", "edge_type", "distance", "capacity", "notes"]


def col_letters(n: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA, matching grid_position_to_xy's inverse."""
    n += 1
    letters = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters = chr(ord("A") + rem) + letters
    return letters


class Builder:
    def __init__(self):
        self.nodes = []
        self.edges = []
        self._edge_pairs = set()
        self._raw_positions = {}

    def add_node(self, node_id, node_type, x, y, space_type="", space_id="", space_name="", room_id="", room_name=""):
        # grid_position strings have no minus sign and no arbitrary column
        # fractions -- raw (x, y) is kept and validated/shifted to a valid,
        # non-negative grid in finalize(), called once all nodes are added.
        self._raw_positions[node_id] = (float(x), float(y))
        self.nodes.append({
            "node_id": node_id, "node_type": node_type, "grid_position": None,
            "description": f"{node_type} node", "space_type": space_type,
            "space_id": space_id, "space_name": space_name, "room_id": room_id, "room_name": room_name,
        })

    def finalize(self) -> None:
        """Shift all coordinates so every x, y >= 0, then render grid_position strings."""
        xs = [x for x, _ in self._raw_positions.values()]
        ys = [y for _, y in self._raw_positions.values()]
        min_x, min_y = min(xs), min(ys)
        # A small positive margin keeps everything strictly >= 1 (some real
        # floorplans start at row/col 1, not 0) and avoids any edge-case at
        # exactly 0 with the "_A" half-column marker.
        shift_x, shift_y = -min_x + 1, -min_y + 1

        for node in self.nodes:
            x, y = self._raw_positions[node["node_id"]]
            x, y = x + shift_x, y + shift_y
            frac = round(x - int(x), 6)
            if frac not in (0.0, 0.5):
                raise ValueError(f"node {node['node_id']}: x={x} has unsupported column fraction {frac}")
            node["grid_position"] = (
                f"{col_letters(int(x))}{y:g}" if frac == 0.0 else f"{col_letters(int(x))}_A{y:g}"
            )

    def add_edge(self, a, b, edge_type, distance, capacity, notes=""):
        key = frozenset((a, b))
        if key in self._edge_pairs or a == b:
            return
        self._edge_pairs.add(key)
        self.edges.append({
            "source": a, "target": b, "edge_type": edge_type,
            "distance": distance, "capacity": capacity, "notes": notes,
        })


def build_linear(n_rooms: int, n_exits: int, rng: random.Random, corridor_length: int = None) -> Builder:
    """corridor_length, when given, decouples corridor diameter from n_rooms:
    rooms attach round-robin (r % corridor_len), so a corridor shorter than
    n_rooms places multiple rooms per corridor node instead of stretching the
    corridor to match room count. This is what lets the diameter-sweep
    experiment (paper/revision/plan_9.22.26.md item 3) hold N = n_rooms *
    n_exits fixed while varying corridor diameter independently -- the
    default (None) preserves the original corridor_len = max(n_rooms,
    n_exits + 1) behavior used by the published corpus.
    """
    b = Builder()
    corridor_len = corridor_length if corridor_length is not None else max(n_rooms, n_exits + 1)
    corridor_len = max(corridor_len, n_exits + 1, 2)
    for i in range(corridor_len):
        b.add_node(f"C{i}", "navigation", i, 0, space_type="hallway")
    for i in range(corridor_len - 1):
        b.add_edge(f"C{i}", f"C{i+1}", "navigation", 1.0, rng.choice([3, 4, 5]))

    exit_positions = [round(i) for i in np_linspace(0, corridor_len - 1, n_exits)]
    for e, pos in enumerate(exit_positions):
        exit_id = f"EXIT_{chr(65 + e)}"
        b.add_node(exit_id, "exit", pos, -0.5)
        b.add_edge(f"C{pos}", exit_id, "exit", 1.0, rng.choice([4, 5, 6]))

    for r in range(n_rooms):
        attach = r % corridor_len
        side = 1 if r % 2 == 0 else -1
        room_id, room_name = f"R{r+1:02d}", f"Room {r+1:02d}"
        start_id, door_id = f"START_{room_id}", f"DOOR_{r+1:02d}"
        b.add_node(start_id, "room_start", attach, side * 2, space_type="room", space_id=room_id, room_id=room_id, room_name=room_name)
        b.add_node(door_id, "door", attach, side * 1, space_type="door", space_id=room_id, room_id=room_id, room_name=room_name)
        b.add_edge(start_id, door_id, "room_start", 1.0, rng.choice([2, 3]))
        b.add_edge(door_id, f"C{attach}", "door_to_hallway", 1.0, rng.choice([2, 3]))
    return b


def build_tree(n_rooms: int, n_exits: int, rng: random.Random) -> Builder:
    b = Builder()
    spine_len = max(6, n_rooms // 3)
    for i in range(spine_len):
        b.add_node(f"C{i}", "navigation", i, 0, space_type="hallway")
    for i in range(spine_len - 1):
        b.add_edge(f"C{i}", f"C{i+1}", "navigation", 1.0, rng.choice([3, 4, 5]))

    branch_points = list(range(1, spine_len - 1, max(1, spine_len // max(1, n_exits))))
    room_counter = 0
    branch_uid = 0

    def add_room(attach_node_id, x, y):
        nonlocal room_counter
        room_counter += 1
        room_id, room_name = f"R{room_counter:02d}", f"Room {room_counter:02d}"
        start_id, door_id = f"START_{room_id}", f"DOOR_{room_counter:02d}"
        b.add_node(start_id, "room_start", x, y + 1, space_type="room", space_id=room_id, room_id=room_id, room_name=room_name)
        b.add_node(door_id, "door", x, y, space_type="door", space_id=room_id, room_id=room_id, room_name=room_name)
        b.add_edge(start_id, door_id, "room_start", 1.0, rng.choice([2, 3]))
        b.add_edge(door_id, attach_node_id, "door_to_hallway", 1.0, rng.choice([2, 3]))

    # branch_x is the branch corridor's own column, offset by a fixed +0.5
    # from the spine (a valid half-column step); rooms sit a further whole
    # column out from the branch, on the same side.
    #
    # Each (branch_point, side) is a growable branch. Round-robin one room
    # at a time across all branches until every room is placed -- this
    # guarantees every room attaches to the nearest node on its own
    # branch's chain (never a distant, unrelated node from a separate
    # fallback path), and branches grow evenly regardless of whether
    # n_rooms divides cleanly across them.
    branches = []
    for bp in branch_points:
        for side in (1, -1):
            branch_uid += 1
            branches.append({"prev": f"C{bp}", "x": bp + 0.5, "side": side, "j": 0, "uid": branch_uid})

    branch_idx = 0
    while room_counter < n_rooms:
        branch = branches[branch_idx % len(branches)]
        branch_idx += 1
        j = branch["j"]
        branch["j"] += 1
        bnode = f"B{branch['uid']}_{j}"
        y = branch["side"] * (j + 1)
        b.add_node(bnode, "navigation", branch["x"], y, space_type="hallway")
        if j == 0:
            # The spine -> first-branch-node edge would otherwise move both
            # in x (0.5) and y (1) in a single hop -- a diagonal shortcut a
            # real, wall-respecting corridor can't take. Route it through an
            # axis-aligned elbow instead (turn the corner in two hops).
            elbow = f"E{branch['uid']}"
            b.add_node(elbow, "navigation", branch["x"], 0, space_type="hallway")
            b.add_edge(branch["prev"], elbow, "navigation", 1.0, rng.choice([2, 3, 4]))
            b.add_edge(elbow, bnode, "navigation", 1.0, rng.choice([2, 3, 4]))
        else:
            b.add_edge(branch["prev"], bnode, "navigation", 1.0, rng.choice([2, 3, 4]))
        branch["prev"] = bnode
        add_room(bnode, branch["x"] + branch["side"] * 1, y)

    exit_positions = [0, spine_len - 1] + [branch_points[i] for i in range(min(n_exits - 2, len(branch_points)))]
    for e, pos in enumerate(exit_positions[:n_exits]):
        exit_id = f"EXIT_{chr(65 + e)}"
        b.add_node(exit_id, "exit", pos, -0.7)
        b.add_edge(f"C{pos}", exit_id, "exit", 1.0, rng.choice([4, 5, 6]))
    return b


def build_loop(n_rooms: int, n_exits: int, rng: random.Random) -> Builder:
    b = Builder()
    perimeter = max(12, n_rooms)
    side_len = max(3, perimeter // 4)
    ring: List[Tuple[float, float]] = []
    for i in range(side_len):
        ring.append((i, 0))
    for i in range(side_len):
        ring.append((side_len - 1, i))
    for i in range(side_len):
        ring.append((side_len - 1 - i, side_len - 1))
    for i in range(side_len):
        ring.append((0, side_len - 1 - i))
    ring = list(dict.fromkeys(ring))  # de-dup corners while preserving order

    ring_ids = []
    for i, (x, y) in enumerate(ring):
        node_id = f"C{i}"
        b.add_node(node_id, "navigation", x, y, space_type="hallway")
        ring_ids.append(node_id)
    n = len(ring_ids)
    for i in range(n):
        b.add_edge(ring_ids[i], ring_ids[(i + 1) % n], "navigation", 1.0, rng.choice([3, 4, 5]))

    exit_positions = [round(i) for i in np_linspace(0, n - 1, n_exits)]
    for e, pos in enumerate(exit_positions):
        exit_id = f"EXIT_{chr(65 + e)}"
        x, y = ring[pos]
        # ring -> exit would otherwise move both in x (0.5) and y (1) in a
        # single hop -- route it through an axis-aligned elbow instead.
        elbow_id = f"EELBOW_{exit_id}"
        b.add_node(elbow_id, "navigation", x + 0.5, y, space_type="hallway")
        b.add_node(exit_id, "exit", x + 0.5, y + 1)
        b.add_edge(ring_ids[pos], elbow_id, "navigation", 1.0, rng.choice([4, 5, 6]))
        b.add_edge(elbow_id, exit_id, "exit", 1.0, rng.choice([4, 5, 6]))

    for r in range(n_rooms):
        attach_idx = r % n
        x, y = ring[attach_idx]
        room_id, room_name = f"R{r+1:02d}", f"Room {r+1:02d}"
        start_id, door_id = f"START_{room_id}", f"DOOR_{r+1:02d}"
        b.add_node(door_id, "door", x - 0.5, y - 1, space_type="door", space_id=room_id, room_id=room_id, room_name=room_name)
        b.add_node(start_id, "room_start", x - 0.5, y - 2, space_type="room", space_id=room_id, room_id=room_id, room_name=room_name)
        b.add_edge(start_id, door_id, "room_start", 1.0, rng.choice([2, 3]))
        # door -> ring node would otherwise move both in x (0.5) and y (1)
        # in a single hop -- a diagonal shortcut a real, wall-respecting
        # corridor can't take. Route it through an axis-aligned elbow
        # instead (turn the corner in two hops).
        elbow_id = f"ELBOW_{room_id}"
        b.add_node(elbow_id, "navigation", x - 0.5, y, space_type="hallway")
        b.add_edge(door_id, elbow_id, "door_to_hallway", 1.0, rng.choice([2, 3]))
        b.add_edge(elbow_id, ring_ids[attach_idx], "navigation", 1.0, rng.choice([2, 3]))
    return b


def np_linspace(a, b, n):
    if n <= 1:
        return [a]
    step = (b - a) / (n - 1)
    return [a + step * i for i in range(n)]


BUILDERS = {"linear": build_linear, "tree": build_tree, "loop": build_loop}


def write_floorplan(floorplan_id: str, builder: Builder, rng: random.Random, topology: str) -> None:
    builder.finalize()
    input_dir = ROOT / "data" / "floorplans" / floorplan_id / "input"
    input_dir.mkdir(parents=True, exist_ok=True)

    with (input_dir / "graph_nodes.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=NODE_FIELDS)
        writer.writeheader()
        writer.writerows(builder.nodes)

    with (input_dir / "graph_edges.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=EDGE_FIELDS)
        writer.writeheader()
        writer.writerows(builder.edges)

    room_rows = []
    for n in builder.nodes:
        if n["node_type"] == "room_start":
            occupancy = rng.randint(2, 25)
            capacity = occupancy + rng.randint(0, 5)
            room_rows.append({
                "room_id": n["room_id"], "room_name": n["room_name"],
                "capacity": capacity, "occupancy": occupancy,
            })
    with (input_dir / "room_occupancy.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["room_id", "room_name", "capacity", "occupancy"])
        writer.writeheader()
        writer.writerows(room_rows)

    with (input_dir / "metadata.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["floorplan_id", "floorplan_name", "grid_unit", "people_per_capacity_unit", "image_file", "notes"])
        writer.writeheader()
        writer.writerow({
            "floorplan_id": floorplan_id,
            "floorplan_name": f"Synthetic {topology}",
            "grid_unit": 1.0, "people_per_capacity_unit": 10,
            "image_file": "", "notes": f"Generated synthetic floorplan, topology={topology}",
        })


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("floorplan_id")
    parser.add_argument("--topology", choices=list(BUILDERS), required=True)
    parser.add_argument("--rooms", type=int, required=True)
    parser.add_argument("--exits", type=int, required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--corridor-length", type=int, default=None,
        help="Linear topology only: corridor node count, decoupled from --rooms "
             "(rooms attach round-robin). Omit to preserve the original "
             "corridor_len = max(rooms, exits + 1) behavior.",
    )
    args = parser.parse_args()
    if args.corridor_length is not None and args.topology != "linear":
        raise SystemExit("--corridor-length is only supported for --topology linear")

    rng = random.Random(args.seed)
    if args.topology == "linear":
        builder = build_linear(args.rooms, args.exits, rng, corridor_length=args.corridor_length)
    else:
        builder = BUILDERS[args.topology](args.rooms, args.exits, rng)
    write_floorplan(args.floorplan_id, builder, rng, args.topology)
    print(f"{args.floorplan_id}: {args.topology}, {len(builder.nodes)} nodes, {len(builder.edges)} edges")


if __name__ == "__main__":
    main()
