# Reproducibility guide

## Install

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Rebuild deterministic data

One floorplan:

```bash
python scripts/run_preprocessing_pipeline.py --floorplan FP02
```

All floorplans:

```bash
python scripts/run_all_preprocessing.py
```

Outputs are written under `data/floorplans/FPXX/output/` and never overwrite another floorplan.

## Solve or benchmark

```bash
python scripts/solve_qubo_neal.py --floorplan FP02
python scripts/benchmark_qubo_neal.py --floorplan FP02 10
```

After `dwave setup --auth`, replace `neal` with `hybrid` or `qpu` for cloud runs. Direct-QPU embedding may fail for larger instances; record that limitation rather than changing the logical model.

## Validate

```bash
pytest
python -m compileall src scripts tests
```

The FP01 saved stochastic results are retained. New stochastic solver runs are not expected to reproduce exact samples bit for bit.
