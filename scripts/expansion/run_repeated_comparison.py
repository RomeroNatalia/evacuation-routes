"""Repeated Neal + Hybrid runs across the full 23-floorplan corpus, for a
proper significance test (not just single-shot numbers) on both the original
5 real floorplans and the 18 synthetic ones.

Neal repeats are free (local compute) -- default 10 independent 4-seed
batches per floorplan, matching the paper's own per-run granularity.
Hybrid repeats cost real D-Wave Leap quota -- default 10 per floorplan.
Confirm budget before increasing --hybrid-repeats; a previous run exhausted
quota partway through (see docs/EXPANSION_STATISTICAL_CONFIRMATION.md).

Crash-safe by design: every single Hybrid call's result is written to disk
immediately (docs/expansion_repeated_comparison_raw.json), not just at the
end. If the process dies mid-run (quota exhaustion, network error, etc.),
nothing already computed is lost. Re-running the exact same command resumes
automatically -- floorplans that already have the requested number of Neal
and Hybrid repeats saved are skipped, and a floorplan that's partially done
(e.g. 4 of 10 Hybrid repeats saved before a crash) only runs the remaining
repeats.

Usage:

    DWAVE_API_TOKEN=... python scripts/expansion/run_repeated_comparison.py \
        --repeats 10 --hybrid-repeats 10 --floorplans FP01 FP02 ... SYN_LIN_10_S1 ...
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
OUT_PATH = ROOT / "docs" / "expansion_repeated_comparison_raw.json"


def load_state() -> dict:
    """floorplan -> result dict. Missing/corrupt file just starts empty."""
    if not OUT_PATH.exists():
        return {}
    try:
        data = json.loads(OUT_PATH.read_text())
        return {r["floorplan"]: r for r in data}
    except (json.JSONDecodeError, KeyError):
        return {}


def save_state(state: dict) -> None:
    OUT_PATH.write_text(json.dumps(list(state.values()), indent=2), encoding="utf-8")


def ensure_entry(state: dict, fp: str, n_variables: int, milp_optimum) -> dict:
    if fp not in state:
        state[fp] = {
            "floorplan": fp,
            "n_variables": n_variables,
            "milp_optimum": milp_optimum,
            "neal_energies": [],
            "hybrid_energies": [],
        }
    return state[fp]


def run_neal_repeats(bqm, room_variables, entry: dict, target: int, reads: int, sweeps: int, state: dict) -> None:
    sampler = neal.SimulatedAnnealingSampler()
    start_index = len(entry["neal_energies"])
    for i in range(start_index, target):
        seeds = [1000 * (i + 1) + s for s in range(4)]
        reads_per_seed = max(1, math.ceil(reads / len(seeds)))
        sample_sets = [
            sampler.sample(bqm, num_reads=reads_per_seed, num_sweeps=sweeps, seed=seed)
            for seed in seeds
        ]
        sampleset = dimod.concatenate(sample_sets).aggregate()
        best = best_valid_energy(sampleset, room_variables)
        entry["neal_energies"].append(best)
        save_state(state)  # save after every single repeat, not just at the end


def run_hybrid_repeats(sampler, bqm, room_variables, entry: dict, floorplan: str, target: int, state: dict) -> None:
    start_index = len(entry["hybrid_energies"])
    for i in range(start_index, target):
        sampleset = sampler.sample(bqm, label=f"expansion-hybrid-rep{i}: {floorplan}")
        best = best_valid_energy(sampleset, room_variables)
        entry["hybrid_energies"].append(best)
        save_state(state)  # save after every single Hybrid call -- these are the expensive ones


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

    state = load_state()
    print(f"Resuming with {len(state)} floorplan(s) already having some data saved.\n")

    for fp in args.floorplans:
        input_dir = ROOT / "data" / "floorplans" / fp / "output"
        bqm, routes, room_variables = load_and_build_bqm(input_dir)
        milp_path = input_dir / "milp_gap" / "milp_solution_summary.json"
        milp_optimum = json.loads(milp_path.read_text())["energy"] if milp_path.exists() else None

        entry = ensure_entry(state, fp, bqm.num_variables, milp_optimum)

        if len(entry["neal_energies"]) < args.repeats:
            t0 = time.perf_counter()
            run_neal_repeats(bqm, room_variables, entry, args.repeats, args.reads, args.sweeps, state)
            neal_t = time.perf_counter() - t0
        else:
            neal_t = 0.0

        if len(entry["hybrid_energies"]) < args.hybrid_repeats:
            t0 = time.perf_counter()
            try:
                run_hybrid_repeats(hybrid_sampler, bqm, room_variables, entry, fp, args.hybrid_repeats, state)
            except Exception as exc:
                print(f"\n{fp}: stopped after {len(entry['hybrid_energies'])} Hybrid repeats -- {exc}")
                print("Partial results through this point are already saved. Re-run the same command to resume.")
                raise
            hybrid_t = time.perf_counter() - t0
        else:
            hybrid_t = 0.0

        n_e, h_e = entry["neal_energies"], entry["hybrid_energies"]
        n_gap_mean = 100 * (sum(n_e) / len(n_e) - milp_optimum) / milp_optimum if n_e else float("nan")
        h_gap_mean = 100 * (sum(h_e) / len(h_e) - milp_optimum) / milp_optimum if h_e else float("nan")
        print(f"{fp:20}Neal({len(n_e)}) mean gap={n_gap_mean:8.2f}%   "
              f"Hybrid({len(h_e)}) mean gap={h_gap_mean:8.2f}%   "
              f"(neal {neal_t:.1f}s, hybrid {hybrid_t:.1f}s)")

    print(f"\nAll requested floorplans complete. Written to {OUT_PATH}")


if __name__ == "__main__":
    main()
