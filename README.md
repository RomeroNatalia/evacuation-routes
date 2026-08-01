# Fire Evacuation QUBO Capstone

This repository contains the current five-floorplan version of the capstone. It models each building as a wall-aware graph and compares distance-only Dijkstra/A*, greedy congestion-aware Dijkstra, Neal simulated annealing, D-Wave Leap Hybrid, and direct D-Wave QPU sampling.

## Included floorplans

| ID | Layout | Rooms | Exits | QUBO variables | Nodes | Edges | Test occupants |
|---|---|---:|---:|---:|---:|---:|---:|
| FP01 | Office | 12 | 5 | 60 | 173 | 245 | 100 |
| FP02 | School Administration Building | 33 | 8 | 264 | 584 | 793 | 183 |
| FP03 | Dormitory | 28 | 9 | 252 | 571 | 790 | 65 |
| FP04 | Museum | 8 | 2 | 16 | 173 | 253 | 164 |
| FP05 | Clinic | 24 | 3 | 72 | 360 | 497 | 85 |

`FP01` is the original office floorplan. All five datasets use the same folder structure and commands.

## Repository structure

```text
.
├── data/floorplans/
│   ├── FP01/
│   │   ├── input/
│   │   └── output/
│   ├── FP02/
│   ├── FP03/
│   ├── FP04/
│   └── FP05/
├── docs/
├── scripts/
├── src/fire_evacuation/
└── tests/
```

## Installation

Python 3.10 or newer is required.

```bash
python -m venv .venv
source .venv/bin/activate       # macOS/Linux
# .venv\Scripts\Activate.ps1  # Windows PowerShell
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Configure Leap only for Hybrid or direct-QPU jobs:

```bash
dwave setup --auth
```

## Select a floorplan

Every active script accepts `--floorplan`. FP01 is the default.

```bash
python scripts/run_preprocessing_pipeline.py --floorplan FP01
python scripts/run_preprocessing_pipeline.py --floorplan FP05
```

Process all included datasets:

```bash
python scripts/run_all_preprocessing.py
```

## Solve the QUBO

```bash
python scripts/solve_qubo_neal.py --floorplan FP04
python scripts/solve_qubo_hybrid.py --floorplan FP04
python scripts/solve_qubo_qpu.py --floorplan FP04
```

Cloud solvers submit quota-limited jobs. Larger floorplans may not embed directly on the QPU; an embedding failure is a legitimate scaling result rather than a preprocessing error.

## Repeated benchmarks

```bash
python scripts/benchmark_qubo_neal.py --floorplan FP01 10
python scripts/benchmark_qubo_hybrid.py --floorplan FP01 10
python scripts/benchmark_qubo_qpu.py --floorplan FP01 10
```

## Assignment-penalty sweeps

```bash
python scripts/sweep/sweep_assignment_penalty_neal.py --floorplan FP01 5
python scripts/sweep/sweep_assignment_penalty_hybrid.py --floorplan FP01 5
python scripts/sweep/sweep_assignment_penalty_qpu.py --floorplan FP01 5
```

## Tests

```bash
pytest
python -m compileall src scripts tests
```

The tests validate every included floorplan, confirm room-to-exit reachability and doorway degree, and compare A* with Dijkstra.

## Current saved results

The completed solver benchmarks and assignment-penalty sweeps from the prior discussion are preserved under each floorplan, for example: `data/floorplans/FP01/output/`. The capstone contains complete 30-run Neal and Hybrid results for all five floor plans and QPU results for FP01, FP04, and FP05.

## Model scope

This is a static, capacity-aware route-assignment model. It does not simulate time-dependent queues, smoke spread, walking speed, panic, or individual occupant behavior. The optimized QUBO combines normalized route distance, normalized squared edge utilization, and an exactly-one-route penalty.
