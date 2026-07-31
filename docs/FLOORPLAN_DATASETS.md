# Floorplan datasets

The project now contains five standardized floorplans. The original office is FP01 and is stored and selected in exactly the same way as FP02–FP05.

| ID | Layout | Rooms | Exits | Route variables | Nodes | Edges | Occupancy | Components | Validation |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| FP01 | Office | 12 | 5 | 60 | 173 | 245 | 100 | 1 | PASS |
| FP02 | School Administration Building | 33 | 8 | 264 | 584 | 793 | 183 | 1 | PASS |
| FP03 | Dormitory | 28 | 9 | 252 | 571 | 790 | 65 | 1 | PASS |
| FP04 | Museum | 8 | 2 | 16 | 173 | 253 | 164 | 1 | PASS |
| FP05 | Clinic | 24 | 3 | 72 | 360 | 497 | 85 | 1 | PASS |

## Validation meaning

A PASS means that every room start can reach every exit, every door node has a valid degree of 2 or 3, all referenced endpoints exist, distances are positive, and A* matches Dijkstra on every room-to-exit pair.

After the marked geometry corrections, both FP02 and FP03 form one connected component with no isolated nodes.

## Standard commands

```bash
python scripts/run_preprocessing_pipeline.py --floorplan FP01
python scripts/run_preprocessing_pipeline.py --floorplan FP05
python scripts/run_all_preprocessing.py
```

Each floorplan writes to its own `output/` folder, so results never overwrite another dataset.

## Coordinate normalization during integration

The supplied FP02, FP03, and FP05 node tables used labels such as `WEST16`, `EAST16`, and `WEST18` for a few exterior exits. Those strings are not ordinary spreadsheet-grid coordinates and were interpreted as extremely large column values by the existing visualization parser. They were replaced with nearby valid grid positions (`A16`, `AG16`, or `A18`) based on each exit's connected interior node. This changes only plotting coordinates; node IDs, graph connections, distances, capacities, routes, and occupancies are unchanged.
