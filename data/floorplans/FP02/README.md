# FP02: School Administration Building

This floorplan uses the same standardized structure as every other dataset.

- `input/graph_nodes.csv`: room starts, navigation points, doors, and exits.
- `input/graph_edges.csv`: legal wall-aware connections, distances, and capacities.
- `input/room_occupancy.csv`: room capacity and deterministic test occupancy.
- `input/metadata.csv`: floorplan name and dataset settings.
- `input/floorplan.png`: reference drawing or schematic.
- `output/`: deterministic preprocessing products and any saved solver results.

Rooms: **33**  
Exits: **8**  
Candidate QUBO route variables: **264**  
Graph nodes: **584**  
Graph edges: **793**  
Test occupancy: **183 people**

Rebuild this floorplan from the repository root:

```bash
python scripts/run_preprocessing_pipeline.py --floorplan FP02
```
