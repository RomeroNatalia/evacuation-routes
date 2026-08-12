"""Repeated Neal + Hybrid runs across the full 23-floorplan corpus, for a
proper significance test (not just single-shot numbers) on both the original
5 real floorplans and the 18 synthetic ones.

Neal repeats are free (local compute) -- default 10 independent 4-seed
batches per floorplan, matching the paper's own per-run granularity.
Hybrid repeats cost real D-Wave Leap quota -- default 10 per floorplan,
23 floorplans x 10 = 230 calls x ~3.0s service-enforced minimum =~ 11.5
minutes of Hybrid solver time total. Confirm budget before increasing
--hybrid-repeats.

Usage:

    DWAVE_API_TOKEN=... python scripts/expansion/run_repeated_comparison.py \
        --repeats 10 --floorplans FP01 FP02 ... SYN_LIN_10_S1 ...
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

import dimod
import neal
from dwave.system import LeapHybridSampler

sys.path.insert(0, str(Path(__file__).resolve().parent))
from neal_budget_scaling_test import load_and_build_bqm, best_valid_energy  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def neal_runs(bqm, room_variables, n_repeats: int, reads: int, sweeps: int):
    sampler = neal.SimulatedAnnealingSampler()
    energies = []
    for i in range(n_repeats):
        seeds = [1000 * (i + 1) + s for s in range(4)]
        reads_per_seed = max(1, math.ceil(reads / len(seeds)))
        sample_sets = [
            sampler.sample(bqm, num_reads=reads_per_seed, num_sweeps=sweeps, seed=seed)
            for seed in seeds
        ]
        sampleset = dimod.concatenate(sample_sets).aggregate()
        best = best_valid_energy(sampleset, room_variables)
        energies.append(best)
    return energies


def hybrid_runs(sampler, bqm, room_variables, floorplan: str, n_repeats: int):
    energies = []
    for i in range(n_repeats):
        sampleset = sampler.sample(bqm, label=f"expansion-hybrid-rep{i}: {floorplan}")
        best = best_valid_energy(sampleset, room_variables)
        energies.append(best)
    return energies


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--floorplans", nargs="+", required=True)
    parser.add_argument("--repeats", type=int, default=10, help="Neal repeats")
    parser.add_argument("--hybrid-repeats", type=int, default=10)
    parser.add_argument("--reads", type=int, default=1000)
    parser.add_argument("--sweeps", type=int, default=5000)
    args = parser.parse_args()

    token = os.environ.get("DWAVE_API_TOKEN")
    if not token:
        raise SystemExit("DWAVE_API_TOKEN must be set in the environment.")
    hybrid_sampler = LeapHybridSampler(token=token)
    print(f"Connected: {hybrid_sampler.solver.name}\n")

    all_results = []
    for fp in args.floorplans:
        input_dir = ROOT / "data" / "floorplans" / fp / "output"
        bqm, routes, room_variables = load_and_build_bqm(input_dir)
        milp_path = input_dir / "milp_gap" / "milp_solution_summary.json"
        milp_optimum = json.loads(milp_path.read_text())["energy"] if milp_path.exists() else None

        t0 = time.perf_counter()
        neal_energies = neal_runs(bqm, room_variables, args.repeats, args.reads, args.sweeps)
        neal_t = time.perf_counter() - t0

        t0 = time.perf_counter()
        hybrid_energies = hybrid_runs(hybrid_sampler, bqm, room_variables, fp, args.hybrid_repeats)
        hybrid_t = time.perf_counter() - t0

        result = {
            "floorplan": fp,
            "n_variables": bqm.num_variables,
            "milp_optimum": milp_optimum,
            "neal_energies": neal_energies,
            "hybrid_energies": hybrid_energies,
            "neal_wall_clock_s": neal_t,
            "hybrid_wall_clock_s": hybrid_t,
        }
        all_results.append(result)

        n_gap_mean = 100 * (sum(neal_energies) / len(neal_energies) - milp_optimum) / milp_optimum
        h_gap_mean = 100 * (sum(hybrid_energies) / len(hybrid_energies) - milp_optimum) / milp_optimum
        print(f"{fp:20}Neal mean gap={n_gap_mean:8.2f}%   Hybrid mean gap={h_gap_mean:8.2f}%   "
              f"(neal {neal_t:.1f}s, hybrid {hybrid_t:.1f}s)")

    out_path = ROOT / "docs" / "expansion_repeated_comparison_raw.json"
    existing = []
    if out_path.exists():
        existing = json.loads(out_path.read_text())
        existing = [e for e in existing if e["floorplan"] not in {r["floorplan"] for r in all_results}]
    out_path.write_text(json.dumps(existing + all_results, indent=2), encoding="utf-8")
    print(f"\nWritten to {out_path}")


if __name__ == "__main__":
    main()
