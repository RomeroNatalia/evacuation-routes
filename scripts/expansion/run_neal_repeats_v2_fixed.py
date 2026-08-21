"""10-repeat Neal comparison for the V2 (diagonal-fixed) synthetic corpus,
using the CORRECTED unpruned-energy recomputation (fixes the pruned-vs-
unpruned bug in best_valid_energy(), which returns the pruned-BQM search
energy instead of the paper's own true, unpruned objective).

For each repeat, also reports the OLD (buggy, pruned) energy alongside the
new corrected one, so the size of that bug's effect is visible directly
rather than assumed.

Usage:
    python scripts/expansion/run_neal_repeats_v2_fixed.py SYN_LIN_10_S1_V2 [SYN_..._V2 ...]
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

import dimod
import neal
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "expansion"))
from neal_budget_scaling_test import load_and_build_bqm, exact_one_status, variable_name  # noqa: E402
from milp_optimality_gap import load_problem_data, build_arrays, compute_objective_scales, true_energy  # noqa: E402

REPEATS = 10
READS = 1000
SWEEPS = 5000
N_SEEDS = 4


def run_one_floorplan(fp: str) -> dict:
    input_dir = ROOT / "data" / "floorplans" / fp / "output"
    bqm, routes_neal, room_variables = load_and_build_bqm(input_dir)

    routes_milp, weighted_rows, edge_rows, edge_ids = load_problem_data(input_dir)
    distances, weighted_incidence, capacities, normalized_load = build_arrays(
        routes_milp, weighted_rows, edge_rows, edge_ids
    )
    scales = compute_objective_scales(routes_milp, distances, normalized_load)
    var_order = [variable_name(r) for r in routes_milp]

    milp_path = input_dir / "milp_gap" / "milp_solution_summary.json"
    cpsat_energy = json.loads(milp_path.read_text())["energy"] if milp_path.exists() else None

    sampler = neal.SimulatedAnnealingSampler()
    pruned_energies, unpruned_energies = [], []
    t0 = time.perf_counter()
    for i in range(REPEATS):
        seeds = [1000 * (i + 1) + s for s in range(N_SEEDS)]
        reads_per_seed = max(1, math.ceil(READS / N_SEEDS))
        sample_sets = [
            sampler.sample(bqm, num_reads=reads_per_seed, num_sweeps=SWEEPS, seed=seed)
            for seed in seeds
        ]
        sampleset = dimod.concatenate(sample_sets).aggregate()

        best_pruned = None
        best_sample = None
        for datum in sampleset.data(fields=["sample", "energy"], sorted_by="energy"):
            if exact_one_status(datum.sample, room_variables):
                best_pruned = float(datum.energy)
                best_sample = datum.sample
                break

        pruned_energies.append(best_pruned)
        if best_sample is not None:
            x_values = np.array([float(best_sample.get(v, 0)) for v in var_order])
            unpruned_energies.append(true_energy(routes_milp, distances, normalized_load, scales, x_values)["energy"])
        else:
            unpruned_energies.append(None)
    elapsed = time.perf_counter() - t0

    valid_pruned = [e for e in pruned_energies if e is not None]
    valid_unpruned = [e for e in unpruned_energies if e is not None]
    pruned_gap = 100 * (sum(valid_pruned) / len(valid_pruned) - cpsat_energy) / cpsat_energy if valid_pruned and cpsat_energy else None
    unpruned_gap = 100 * (sum(valid_unpruned) / len(valid_unpruned) - cpsat_energy) / cpsat_energy if valid_unpruned and cpsat_energy else None

    return {
        "floorplan": fp,
        "cpsat_reference_energy": cpsat_energy,
        "pruned_energies": pruned_energies,
        "unpruned_energies": unpruned_energies,
        "pruned_gap_pct_OLD_BUGGY": pruned_gap,
        "unpruned_gap_pct_FIXED": unpruned_gap,
        "wall_clock_s": elapsed,
    }


if __name__ == "__main__":
    floorplans = sys.argv[1:]
    out_path = ROOT / "docs" / "expansion_synthetic_neal_v2_fixed_raw.json"
    results = json.loads(out_path.read_text()) if out_path.exists() else []
    done = {r["floorplan"] for r in results}
    for fp in floorplans:
        if fp in done:
            print(f"Skipping {fp} (already done)")
            continue
        print(f"Running {fp}...", flush=True)
        r = run_one_floorplan(fp)
        results.append(r)
        out_path.write_text(json.dumps(results, indent=2))  # save after every floorplan
        print(
            f"  {fp}: OLD(pruned) gap={r['pruned_gap_pct_OLD_BUGGY']:.2f}%  "
            f"FIXED(unpruned) gap={r['unpruned_gap_pct_FIXED']:.2f}%  "
            f"[{r['wall_clock_s']:.1f}s]"
        )
    print(f"\nSaved: {out_path}")
