# Current scripts

All active scripts accept `--floorplan FP01` through `--floorplan FP05`. FP01 is the default.

## Preprocessing

- `run_preprocessing_pipeline.py`: rebuild one floorplan.
- `run_all_preprocessing.py`: rebuild all included floorplans.
- `run_classical_routing.py`: validate graph and compute Dijkstra/A* routes.
- `audit_graph_geometry.py`: report diagonal and unusually long source-target connections without modifying data.
- `run_congestion_analysis.py`: apply occupancy and greedy congestion-aware Dijkstra.
- `generate_edge_route_incidence_matrix.py`: create the QUBO route catalog and edge matrices.
- `render_route_summary.py`, `render_floorplan_routes.py`, and `render_dijkstra_vs_congestion.py`: generate figures.

## QUBO solvers

- `solve_qubo_neal.py`
- `solve_qubo_hybrid.py`
- `solve_qubo_qpu.py`

## Repeated experiments

- `benchmark_qubo_neal.py`
- `benchmark_qubo_hybrid.py`
- `benchmark_qubo_qpu.py`
- `sweep/`: assignment-penalty sweeps for all three solvers.

Examples:

```bash
python scripts/run_preprocessing_pipeline.py --floorplan FP03
python scripts/solve_qubo_neal.py --floorplan FP03
python scripts/benchmark_qubo_neal.py --floorplan FP03 10
```
