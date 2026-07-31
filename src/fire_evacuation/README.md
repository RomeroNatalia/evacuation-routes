# `fire_evacuation` package

- `project.py`: resolves FP01–FP05 standardized input/output paths and consumes `--floorplan`.
- `graph_io.py`: loads, validates, and builds the wall-aware NetworkX graph.
- `routing.py`: computes Dijkstra and admissible A* room-to-exit routes and selects primary routes.
- `congestion.py`: applies occupancy, computes utilization, and runs the greedy congestion-aware routing heuristic.
- `visualization.py`: draws graph and route figures.
- `__init__.py`: package metadata and exports.
