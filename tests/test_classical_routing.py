"""Regression tests for all standardized floorplan datasets."""

from pathlib import Path

import pandas as pd
import pytest

from fire_evacuation.graph_io import (
    build_navigation_graph,
    load_graph_data,
    validate_graph_connectivity,
)
from fire_evacuation.project import available_floorplans, floorplan_paths
from fire_evacuation.routing import (
    choose_primary_routes,
    compute_all_room_exit_routes,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FLOORPLAN_IDS = available_floorplans(REPOSITORY_ROOT)


def _build_test_graph(floorplan_id: str):
    paths = floorplan_paths(REPOSITORY_ROOT, floorplan_id)
    nodes, edges = load_graph_data(paths.nodes_csv, paths.edges_csv)
    return paths, nodes, edges, build_navigation_graph(nodes, edges)


@pytest.mark.parametrize("floorplan_id", FLOORPLAN_IDS)
def test_source_tables_and_graph_are_valid(floorplan_id):
    paths, nodes, edges, graph = _build_test_graph(floorplan_id)
    occupancy = pd.read_csv(paths.occupancy_csv)
    validation = validate_graph_connectivity(graph)

    assert graph.number_of_nodes() == len(nodes)
    assert graph.number_of_edges() == len(edges)
    assert validation["all_doors_have_valid_degree"] is True
    assert validation["all_rooms_reach_all_exits"] is True
    assert set(occupancy["room_id"]) == set(
        nodes.loc[nodes["node_type"] == "room_start", "room_id"]
    )


@pytest.mark.parametrize("floorplan_id", FLOORPLAN_IDS)
def test_astar_matches_dijkstra_and_primary_count(floorplan_id):
    paths, nodes, edges, graph = _build_test_graph(floorplan_id)
    all_routes = compute_all_room_exit_routes(graph)
    primary_routes = choose_primary_routes(all_routes)
    room_count = int((nodes["node_type"] == "room_start").sum())
    exit_count = int((nodes["node_type"] == "exit").sum())

    assert all_routes["distances_match"].all()
    assert len(all_routes) == room_count * exit_count
    assert len(primary_routes) == room_count


def test_fp02_edges_are_axis_aligned():
    """Regression check for the marked FP02 geometry correction."""
    from fire_evacuation.graph_io import grid_position_to_xy

    paths = floorplan_paths(REPOSITORY_ROOT, "FP02")
    nodes, edges = load_graph_data(paths.nodes_csv, paths.edges_csv)
    positions = {
        str(row.node_id): grid_position_to_xy(str(row.grid_position))
        for row in nodes.itertuples(index=False)
    }

    diagonal_edges = []
    for row in edges.itertuples(index=False):
        x1, y1 = positions[str(row.source)]
        x2, y2 = positions[str(row.target)]
        if x1 != x2 and y1 != y2:
            diagonal_edges.append((str(row.source), str(row.target)))

    assert diagonal_edges == []


def test_half_column_grid_position_support():
    """Door coordinates such as E_A9 represent halfway between E and F."""
    from fire_evacuation.graph_io import grid_position_to_xy

    assert grid_position_to_xy("E_A9") == (5.5, 9.0)
    assert grid_position_to_xy("E_A13") == (5.5, 13.0)


def test_fp03_edges_are_axis_aligned_and_duplicates_removed():
    """Regression check for the marked FP03 geometry correction."""
    from fire_evacuation.graph_io import grid_position_to_xy

    paths = floorplan_paths(REPOSITORY_ROOT, "FP03")
    nodes, edges = load_graph_data(paths.nodes_csv, paths.edges_csv)
    positions = {
        str(row.node_id): grid_position_to_xy(str(row.grid_position))
        for row in nodes.itertuples(index=False)
    }

    diagonal_edges = []
    for row in edges.itertuples(index=False):
        x1, y1 = positions[str(row.source)]
        x2, y2 = positions[str(row.target)]
        if x1 != x2 and y1 != y2:
            diagonal_edges.append((str(row.source), str(row.target)))

    assert diagonal_edges == []
    assert not any(str(node_id).endswith("_2") for node_id in nodes["node_id"])
    assert set(nodes.loc[nodes["node_type"] == "door", "node_id"]).issuperset(
        {"DOOR_16", "DOOR_21", "DOOR_45"}
    )
