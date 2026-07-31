# Floorplan datasets

Every floorplan is stored in the same way:

```text
FPXX/
├── input/
│   ├── graph_nodes.csv
│   ├── graph_edges.csv
│   ├── room_occupancy.csv
│   ├── metadata.csv
│   └── floorplan.png
└── output/
```

`FP01` is the original office dataset. `FP02` through `FP05` are the four additional layouts. Use `--floorplan FPXX` with every preprocessing, solver, benchmark, or sweep script. If omitted, the scripts default to `FP01`.

See `floorplan_index.csv` for sizes and route-variable counts.
