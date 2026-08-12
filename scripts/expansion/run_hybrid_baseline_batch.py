"""Run D-Wave Leap Hybrid once per floorplan, on the exact same penalized BQM
as run_neal_baseline_batch.py, for a directly comparable gap measurement.

Requires DWAVE_API_TOKEN in the environment (never written to any file --
pass it as an env var only, e.g. `DWAVE_API_TOKEN=... python ...`).

Usage:

    DWAVE_API_TOKEN=... python scripts/expansion/run_hybrid_baseline_batch.py SYN_LIN_10_S1 ...
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from dwave.system import LeapHybridSampler

sys.path.insert(0, str(Path(__file__).resolve().parent))
from neal_budget_scaling_test import load_and_build_bqm, best_valid_energy  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def run_one(sampler, floorplan: str) -> dict:
    input_dir = ROOT / "data" / "floorplans" / floorplan / "output"
    bqm, routes, room_variables = load_and_build_bqm(input_dir)

    milp_path = input_dir / "milp_gap" / "milp_solution_summary.json"
    milp_optimum = json.loads(milp_path.read_text())["energy"] if milp_path.exists() else None

    start = time.perf_counter()
    sampleset = sampler.sample(bqm, label=f"expansion-hybrid: {floorplan}")
    elapsed = time.perf_counter() - start

    best = best_valid_energy(sampleset, room_variables)
    gap_pct = 100.0 * (best - milp_optimum) / milp_optimum if (best is not None and milp_optimum) else None

    qpu_access_time = None
    try:
        qpu_access_time = sampleset.info.get("run_time")
    except Exception:
        pass

    return {
        "floorplan": floorplan,
        "n_variables": bqm.num_variables,
        "n_interactions": bqm.num_interactions,
        "milp_optimum": milp_optimum,
        "hybrid_best_energy": best,
        "hybrid_gap_pct": gap_pct,
        "wall_clock_seconds": elapsed,
        "solver_run_time_us": qpu_access_time,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("floorplans", nargs="+")
    args = parser.parse_args()

    token = os.environ.get("DWAVE_API_TOKEN")
    if not token:
        raise SystemExit("DWAVE_API_TOKEN must be set in the environment (not passed as a CLI arg).")

    sampler = LeapHybridSampler(token=token)
    print(f"Connected: {sampler.solver.name}\n")

    results = []
    for fp in args.floorplans:
        r = run_one(sampler, fp)
        gap_str = f"{r['hybrid_gap_pct']:.2f}%" if r["hybrid_gap_pct"] is not None else "n/a"
        print(f"{fp:20}vars={r['n_variables']:>4}  energy={r['hybrid_best_energy']:.6f}  gap={gap_str:>10}  t={r['wall_clock_seconds']:.2f}s")
        results.append(r)

    out_path = ROOT / "docs" / "expansion_hybrid_results.json"
    existing = []
    if out_path.exists():
        existing = json.loads(out_path.read_text())
        existing = [e for e in existing if e["floorplan"] not in {r["floorplan"] for r in results}]
    out_path.write_text(json.dumps(existing + results, indent=2), encoding="utf-8")
    print(f"\nWritten to {out_path}")


if __name__ == "__main__":
    main()
