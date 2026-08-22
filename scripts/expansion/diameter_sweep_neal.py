"""10-repeat Neal comparison for the diameter-sweep corpus (plan_9.22.26.md item 3).

Reuses run_one_floorplan() from run_neal_repeats_v2_fixed.py (already
validated against the published corpus's methodology -- same REPEATS/READS/
SWEEPS/N_SEEDS and the corrected unpruned-energy recomputation) but writes to
a separate output file so this experimental sweep never touches the
published corpus's tracked results.

Usage:
    python scripts/expansion/diameter_sweep_neal.py SYN_DSWEEP_L06_S1 SYN_DSWEEP_L06_S2 ...
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "expansion"))
from run_neal_repeats_v2_fixed import run_one_floorplan  # noqa: E402


def main() -> None:
    floorplans = sys.argv[1:]
    out_path = ROOT / "docs" / "expansion_diameter_sweep_neal_raw.json"
    results = json.loads(out_path.read_text()) if out_path.exists() else []
    done = {r["floorplan"] for r in results}

    for fp in floorplans:
        if fp in done:
            print(f"Skipping {fp} (already done)")
            continue
        print(f"Running {fp}...", flush=True)
        r = run_one_floorplan(fp)
        results.append(r)
        out_path.write_text(json.dumps(results, indent=2))
        print(f"  {fp}: gap={r['unpruned_gap_pct_FIXED']:.2f}%  [{r['wall_clock_s']:.1f}s]")

    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
