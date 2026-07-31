# Repository integration manifest

This archive was rebuilt from the cleaned July 2026 capstone snapshot and the supplied four-floorplan CSV package.

## Removed from the earlier repository snapshot

- the earlier `fire_evacuation_V1` project
- old notebooks and notebook support files
- nested ZIP archives and progress-dashboard files
- obsolete pre-normalization solvers and result folders
- duplicate `(1)` files, Python caches, and repeated logical-QUBO exports

## Current retained implementation

- one active graph/routing/congestion package
- one current Neal, Hybrid, and direct-QPU solver
- one current benchmark script per solver
- one current assignment-penalty sweep per solver
- the FP01 saved benchmark and sweep results used in the prior discussion
- standardized FP01–FP05 input datasets
- deterministic routing, congestion, matrix, and visualization outputs for all five floorplans

## Multi-floorplan changes

- every floorplan now uses `data/floorplans/FPXX/input/` and `output/`
- FP01 was moved into the same structure as FP02–FP05
- source filenames are standardized as `graph_nodes.csv`, `graph_edges.csv`, `room_occupancy.csv`, `metadata.csv`, and `floorplan.png`
- every active script accepts `--floorplan FPXX` and defaults to FP01
- `run_all_preprocessing.py` rebuilds all datasets without overwriting one another
- output filenames were made layout-neutral rather than office-specific
- the A* heuristic was scaled to remain admissible for schematic grids whose coordinate spacing differs from stored edge-distance units

## Validation performed

- all five preprocessing datasets were successfully loaded and routed
- all room starts can reach every exit
- all doorway nodes have two or three valid graph connections
- A* and Dijkstra agree on every room-to-exit minimum distance
- route catalogs and edge-incidence matrices were generated for all five floorplans
- 10 automated tests passed
- all Python source files compiled successfully

No D-Wave cloud jobs were submitted for FP02–FP05 during integration. Their QUBO input files are ready, but Hybrid and QPU results require the user's configured Leap account. The FP01 saved cloud results were preserved.
