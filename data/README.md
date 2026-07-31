# Data

All datasets are under `floorplans/FP01` through `floorplans/FP05`. Each floorplan has identical `input/` and `output/` structure, so the original office floorplan is accessed in exactly the same way as the four new floorplans.

Run one dataset:

```bash
python scripts/run_preprocessing_pipeline.py --floorplan FP03
```

Run all datasets:

```bash
python scripts/run_all_preprocessing.py
```
