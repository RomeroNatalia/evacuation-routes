"""Run Neal at the paper's exact baseline settings (1000 reads, 5000 sweeps,
seeds 42-45) on a list of floorplans, reusing the same BQM construction as
neal_budget_scaling_test.py, and record the best valid energy plus gap vs.
the certified MILP optimum for each.

Usage:

    python scripts/expansion/run_neal_baseline_batch.py SYN_LIN_10_S1 SYN_LIN_10_S2 ...
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import dimod
import neal

sys.path.insert(0, str(Path(__file__).resolve().parent))
from neal_budget_scaling_test import load_and_build_bqm, best_valid_energy  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def run_one(floorplan: str, reads: int, sweeps: int, seeds) -> dict:
    input_dir = ROOT / "data" / "floorplans" / floorplan / "output"
    bqm, routes, room_variables = load_and_build_bqm(input_dir)

    milp_path = input_dir / "milp_gap" / "milp_solution_summary.json"
    milp_optimum = json.loads(milp_path.read_text())["energy"] if milp_path.exists() else None

    sampler = neal.SimulatedAnnealingSampler()
    reads_per_seed = max(1, math.ceil(reads / len(seeds)))
    start = time.perf_counter()
    sample_sets = [
        sampler.sample(bqm, num_reads=reads_per_seed, num_sweeps=sweeps, seed=seed)
        for seed in seeds
    ]
    sampleset = dimod.concatenate(sample_sets).aggregate()
    elapsed = time.perf_counter() - start

    best = best_valid_energy(sampleset, room_variables)
    gap_pct = 100.0 * (best - milp_optimum) / milp_optimum if (best is not None and milp_optimum) else None

    return {
        "floorplan": floorplan,
        "n_variables": bqm.num_variables,
        "n_interactions": bqm.num_interactions,
        "milp_optimum": milp_optimum,
        "neal_best_energy": best,
        "neal_gap_pct": gap_pct,
        "wall_clock_seconds": elapsed,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("floorplans", nargs="+")
    parser.add_argument("--reads", type=int, default=1000)
    parser.add_argument("--sweeps", type=int, default=5000)
    parser.add_argument("--seeds", type=int, nargs="+", default=[42, 43, 44, 45])
    args = parser.parse_args()

    results = []
    for fp in args.floorplans:
        r = run_one(fp, args.reads, args.sweeps, args.seeds)
        gap_str = f"{r['neal_gap_pct']:.2f}%" if r["neal_gap_pct"] is not None else "n/a"
        print(f"{fp:20}vars={r['n_variables']:>4}  energy={r['neal_best_energy']:.6f}  gap={gap_str:>10}  t={r['wall_clock_seconds']:.2f}s")
        results.append(r)

    out_path = ROOT / "docs" / "expansion_synthetic_neal_results.json"
    existing = []
    if out_path.exists():
        existing = json.loads(out_path.read_text())
        existing = [e for e in existing if e["floorplan"] not in {r["floorplan"] for r in results}]
    out_path.write_text(json.dumps(existing + results, indent=2), encoding="utf-8")
    print(f"\nWritten to {out_path}")


if __name__ == "__main__":
    main()
