"""Visualize the navigation graph and the selected classical routes."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx
import pandas as pd


def draw_graph(
    graph: nx.Graph,
    output_path: str | Path,
    primary_routes: pd.DataFrame | None = None,
) -> None:
    """Draw the verified graph, optionally highlighting primary routes."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    positions = {
        node_id: attributes["position"]
        for node_id, attributes in graph.nodes(data=True)
    }

    figure, axis = plt.subplots(figsize=(30, 20))

    # Draw the verified legal graph lightly in the background.
    nx.draw_networkx_edges(
        graph,
        positions,
        ax=axis,
        width=0.9,
        alpha=0.35,
    )

    node_styles = {
        "navigation": ("o", 35),
        "room_start": ("o", 180),
        "door": ("s", 120),
        "exit": ("D", 160),
    }

    for node_type, (shape, size) in node_styles.items():
        matching_nodes = [
            node_id
            for node_id, attributes in graph.nodes(data=True)
            if attributes.get("node_type") == node_type
        ]

        nx.draw_networkx_nodes(
            graph,
            positions,
            nodelist=matching_nodes,
            node_shape=shape,
            node_size=size,
            edgecolors="black",
            linewidths=0.8,
            ax=axis,
        )

    # Highlight each selected primary route with a thicker line.
    if primary_routes is not None:
        for route in primary_routes.itertuples(index=False):
            path_nodes = str(route.path).split(" -> ")
            path_edges = list(zip(path_nodes[:-1], path_nodes[1:]))

            nx.draw_networkx_edges(
                graph,
                positions,
                edgelist=path_edges,
                width=2.0,
                alpha=0.85,
                ax=axis,
            )

    # Label special nodes. Labeling all 143 navigation points makes the
    # overview difficult to read, so the room starts, doors, and exits are
    # emphasized here. The CSV retains every navigation-node ID.
    for node_id, attributes in graph.nodes(data=True):
        if attributes.get("node_type") == "navigation":
            continue

        x_position, y_position = positions[node_id]
        axis.annotate(
            node_id,
            (x_position, y_position),
            xytext=(0, 9),
            textcoords="offset points",
            ha="center",
            fontsize=7,
            fontweight="bold",
            bbox={
                "boxstyle": "round,pad=0.12",
                "facecolor": "white",
                "alpha": 0.85,
                "linewidth": 0.35,
            },
        )

    # Row 1 belongs at the top of the floor-plan-style drawing.
    all_x = [position[0] for position in positions.values()]
    all_y = [position[1] for position in positions.values()]

    axis.set_xlim(min(all_x) - 0.8, max(all_x) + 0.8)
    axis.set_ylim(max(all_y) + 0.8, min(all_y) - 0.8)
    axis.set_aspect("equal", adjustable="box")
    axis.set_xlabel("Grid column")
    axis.set_ylabel("Grid row")
    axis.set_title(
        "Classical primary evacuation routes",
        fontsize=18,
        pad=18,
    )

    figure.tight_layout()
    figure.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(figure)
