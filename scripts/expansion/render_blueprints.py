"""Render compact floorplan 'blueprint' diagrams for the paper appendix.

For the 5 real floorplans, renders each from its input graph_nodes.csv /
graph_edges.csv. For the 18 synthetic floorplans, renders one blueprint per
topology x size combination (9 total) rather than all 18 -- S1 and S2 share
identical node positions and edges (only per-room occupancy and per-edge
capacity differ between seeds, which a structural blueprint doesn't show).

Deliberately simpler than src/fire_evacuation/visualization.py's draw_graph
(no route highlighting, no node-ID labels, no 30x20in figure size) --
this is a small multi-panel thumbnail, not a standalone detailed figure.

Usage:

    python scripts/expansion/render_blueprints.py
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "paper" / "figures"
OUT_DIR.mkdir(parents=True, exist_ok=True)

_GRID_RE = re.compile(r"([A-Za-z]+)_?([A-Za-z]*)(\d+(?:\.\d+)?)")


def col_letters_to_index(letters: str) -> int:
    value = 0
    for ch in letters.upper():
        value = value * 26 + (ord(ch) - ord("A") + 1)
    return value - 1


def parse_grid_position(raw: str):
    m = _GRID_RE.match(raw)
    if not m:
        return None
    letters = m.group(1)
    number = float(m.group(3))
    return float(col_letters_to_index(letters)), number


def read_csv(path: Path):
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def render(nodes, edges, title: str, out_path: Path, figsize=(3.2, 2.6)) -> None:
    positions = {}
    for n in nodes:
        p = parse_grid_position(n["grid_position"])
        if p is not None:
            positions[n["node_id"]] = p

    fig, ax = plt.subplots(figsize=figsize)

    for e in edges:
        a, b = e.get("source"), e.get("target")
        if a in positions and b in positions:
            (x1, y1), (x2, y2) = positions[a], positions[b]
            ax.plot([x1, x2], [y1, y2], color="#999999", linewidth=0.5, zorder=1, alpha=0.7)

    by_type = {"navigation_room": [], "navigation_hallway": [], "room_start": [], "door": [], "exit": []}
    for n in nodes:
        p = positions.get(n["node_id"])
        if p is None:
            continue
        t = n["node_type"]
        if t == "navigation":
            key = "navigation_hallway" if n.get("space_type") == "hallway" else "navigation_room"
        else:
            key = t
        by_type.setdefault(key, []).append(p)

    style = {
        "navigation_room": dict(marker=".", s=1.5, c="#d9d9d9", zorder=2),
        "navigation_hallway": dict(marker=".", s=2.5, c="#9e9e9e", zorder=2),
        "room_start": dict(marker="o", s=10, c="#2e7d32", zorder=3, edgecolors="none"),
        "door": dict(marker="s", s=8, c="#e07b1a", zorder=3, edgecolors="none"),
        "exit": dict(marker="D", s=14, c="#c62828", zorder=4, edgecolors="none"),
    }
    for key, pts in by_type.items():
        if not pts:
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        ax.scatter(xs, ys, **style.get(key, dict(marker=".", s=2, c="black")))

    all_x = [p[0] for p in positions.values()]
    all_y = [p[1] for p in positions.values()]
    if all_x:
        ax.set_xlim(min(all_x) - 0.6, max(all_x) + 0.6)
        ax.set_ylim(max(all_y) + 0.6, min(all_y) - 0.6)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_title(title, fontsize=8, pad=3)

    # Deliberately NOT bbox_inches="tight": that crops to content, so a
    # narrow/tall floorplan (e.g. FP05's single vertical corridor) produces
    # a much smaller pixel image than a wide one (e.g. FP02's multi-wing
    # layout). When LaTeX then scales every figure to the same
    # \includegraphics{width=\textwidth}, the narrower source image gets
    # magnified far more, making its title/markers look huge relative to
    # the others. Fixed figsize + fixed dpi + no tight crop keeps every
    # blueprint's output pixel dimensions identical, so uniform LaTeX
    # width scaling produces uniform apparent size.
    fig.tight_layout(pad=0.3)
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


def render_real_floorplans():
    names = {
        "FP01": "FP01 -- Office",
        "FP02": "FP02 -- School admin.",
        "FP03": "FP03 -- Dormitory",
        "FP04": "FP04 -- Museum",
        "FP05": "FP05 -- Clinic",
    }
    for fp, title in names.items():
        input_dir = ROOT / "data" / "floorplans" / fp / "input"
        nodes = read_csv(input_dir / "graph_nodes.csv")
        edges = read_csv(input_dir / "graph_edges.csv")
        render(nodes, edges, title, OUT_DIR / f"blueprint_{fp}.png", figsize=(3.6, 3.0))
        print("rendered", fp)


def render_synthetic_representatives():
    combos = [
        ("linear", 10, "SYN_LIN_10_S1", "Linear, 10 rooms"),
        ("linear", 20, "SYN_LIN_20_S1", "Linear, 20 rooms"),
        ("linear", 30, "SYN_LIN_30_S1", "Linear, 30 rooms"),
        ("tree", 10, "SYN_TRE_10_S1", "Tree, 10 rooms"),
        ("tree", 20, "SYN_TRE_20_S1", "Tree, 20 rooms"),
        ("tree", 30, "SYN_TRE_30_S1", "Tree, 30 rooms"),
        ("loop", 10, "SYN_LOO_10_S1", "Loop, 10 rooms"),
        ("loop", 20, "SYN_LOO_20_S1", "Loop, 20 rooms"),
        ("loop", 30, "SYN_LOO_30_S1", "Loop, 30 rooms"),
    ]
    for topo, size, fp, title in combos:
        input_dir = ROOT / "data" / "floorplans" / fp / "input"
        nodes = read_csv(input_dir / "graph_nodes.csv")
        edges = read_csv(input_dir / "graph_edges.csv")
        out_name = f"blueprint_SYN_{topo}_{size}.png"
        render(nodes, edges, title, OUT_DIR / out_name, figsize=(3.0, 3.0))
        print("rendered", fp, "->", out_name)


if __name__ == "__main__":
    render_real_floorplans()
    render_synthetic_representatives()
    print(f"\nAll blueprints written to {OUT_DIR}")
