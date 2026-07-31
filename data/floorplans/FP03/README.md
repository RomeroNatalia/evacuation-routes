# FP03: Dormitory

This floorplan uses the same standardized structure as every other dataset.

- `input/graph_nodes.csv`: room starts, navigation points, doors, and exits.
- `input/graph_edges.csv`: legal wall-aware connections, distances, and capacities.
- `input/room_occupancy.csv`: room capacity and deterministic test occupancy.
- `input/metadata.csv`: floorplan name and dataset settings.
- `input/floorplan.png`: reference drawing or schematic.
- `output/`: deterministic preprocessing products and any saved solver results.

Rooms: **28**  
Exits: **9**  
Candidate QUBO route variables: **252**  
Graph nodes: **571**  
Graph edges: **790**  
Test occupancy: **65 people**

Rebuild this floorplan from the repository root:

```bash
python scripts/run_preprocessing_pipeline.py --floorplan FP03
```
