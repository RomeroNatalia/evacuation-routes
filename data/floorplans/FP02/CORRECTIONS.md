# FP02 geometry corrections

This dataset was corrected from the marked FP02 validation image before final experiments.

## Changes applied

- Removed all diagonal graph edges and replaced them with horizontal or vertical connections.
- Corrected exit positions: `EXIT_A` to `C27`, `EXIT_C` to `E1`, and `EXIT_F` to `P27`.
- Removed the unused boundary nodes `E27` and `AA27`.
- Added missing nodes `K18.5`, `U18.5`, and `AB16`.
- Moved `DOOR_33` to `Q18.5` and `DOOR_43` to `Q21` as marked.
- Moved `AA18`–`AA20` to `AB18`–`AB20`.
- Moved `U24`–`U26` to `T24`–`T26`.
- Completed the central row-23 hallway and the missing `P19`–`P21` vertical hallway links.
- Corrected malformed connections for `DOOR_26`, `DOOR_32`, `DOOR_34`, and `DOOR_39`.

## Validation after correction

- Nodes: **584**
- Edges: **793**
- Connected components: **1**
- Isolated nodes: **0**
- Every room reaches every exit: **yes**
- Every door has degree 2: **yes**
- Diagonal edges: **0**

Regenerate the outputs from the repository root with:

```bash
python scripts/run_preprocessing_pipeline.py --floorplan FP02
```
