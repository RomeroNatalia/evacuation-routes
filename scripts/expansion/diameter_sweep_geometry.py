"""Structural metrics for the diameter-sweep corpus (plan_9.22.26.md item 3).

Reuses geometry_bottleneck_analysis.analyze_floorplan() (already validated
against the published corpus) for a set of floorplan IDs passed on the
command line, writing to a separate output file so this experimental sweep
never touches the published corpus's tracked geometry JSON.

Usage:
    python scripts/expansion/diameter_sweep_geometry.py SYN_DSWEEP_L06_S1 SYN_DSWEEP_L06_S2 ...
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "expansion"))
from geometry_bottleneck_analysis import analyze_floorplan  # noqa: E402


def main() -> None:
    floorplans = sys.argv[1:]
    results = [analyze_floorplan(fp) for fp in floorplans]

    out_path = ROOT / "docs" / "expansion_diameter_sweep_geometry_raw.json"
    out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

    for r in results:
        print(
            f"{r['floorplan']:20} corridor_diam={r['corridor_diameter_hops']:3}  "
            f"route_hops_mean={r['route_hops_mean']:.2f}  "
            f"route_hops_max={r['route_hops_max']:3}  "
            f"bridges={r['structural_bridge_count']:3}  "
            f"crit_bridges={r['structural_critical_bridge_count']:3}"
        )
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
