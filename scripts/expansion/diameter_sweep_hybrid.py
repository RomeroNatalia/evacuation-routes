"""10-repeat Hybrid comparison for the diameter-sweep corpus (plan_9.22.26.md item 3).

Reuses run_one_floorplan() from run_hybrid_repeats_v2_fixed.py (same
REPEATS=10, corrected unpruned-energy recomputation, crash-safe per-floorplan
saving) but writes to a separate output file so this experimental sweep
never touches the published corpus's tracked results or spends its quota
budget accounting.

Usage:
    python scripts/expansion/diameter_sweep_hybrid.py SYN_DSWEEP_L06_S1 SYN_DSWEEP_L06_S2 ...
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from dwave.system import LeapHybridSampler

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "expansion"))
from run_hybrid_repeats_v2_fixed import run_one_floorplan  # noqa: E402

OUT_PATH = ROOT / "docs" / "expansion_diameter_sweep_hybrid_raw.json"


def load_state() -> dict:
    if not OUT_PATH.exists():
        return {}
    try:
        return {r["floorplan"]: r for r in json.loads(OUT_PATH.read_text())}
    except (json.JSONDecodeError, KeyError):
        return {}


def save_state(state: dict) -> None:
    OUT_PATH.write_text(json.dumps(list(state.values()), indent=2), encoding="utf-8")


def main() -> None:
    floorplans = sys.argv[1:]
    sampler = LeapHybridSampler()
    print(f"Connected: {sampler.solver.name}\n")

    state = load_state()
    for fp in floorplans:
        if fp in state:
            print(f"Skipping {fp} (already done)")
            continue
        print(f"Running {fp}...", flush=True)
        r = run_one_floorplan(fp, sampler)
        state[fp] = r
        save_state(state)
        print(f"  {fp}: gap={r['unpruned_gap_pct_FIXED']:.2f}%  [{r['wall_clock_s']:.1f}s]")

    print(f"\nSaved: {OUT_PATH}")


if __name__ == "__main__":
    main()
