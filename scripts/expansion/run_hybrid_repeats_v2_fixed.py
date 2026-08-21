"""10-repeat Hybrid comparison for the V2 (diagonal-fixed) synthetic corpus,
using the CORRECTED unpruned-energy recomputation (same fix as
run_neal_repeats_v2_fixed.py, applied to the Hybrid side).

Crash-safe: saves after every single floorplan's 10 Hybrid repeats, not
just at the end. Re-running resumes automatically (skips floorplans
already fully done).

Usage:
    python scripts/expansion/run_hybrid_repeats_v2_fixed.py SYN_LIN_10_S1_V2 [SYN_..._V2 ...]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
from dwave.system import LeapHybridSampler

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "expansion"))
from neal_budget_scaling_test import load_and_build_bqm, exact_one_status, variable_name  # noqa: E402
from milp_optimality_gap import load_problem_data, build_arrays, compute_objective_scales, true_energy  # noqa: E402

REPEATS = 10
OUT_PATH = ROOT / "docs" / "expansion_synthetic_hybrid_v2_fixed_raw.json"


def load_state() -> dict:
    if not OUT_PATH.exists():
        return {}
    try:
        return {r["floorplan"]: r for r in json.loads(OUT_PATH.read_text())}
    except (json.JSONDecodeError, KeyError):
        return {}


def save_state(state: dict) -> None:
    OUT_PATH.write_text(json.dumps(list(state.values()), indent=2), encoding="utf-8")


def run_one_floorplan(fp: str, sampler: LeapHybridSampler) -> dict:
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

    pruned_energies, unpruned_energies, runtimes = [], [], []
    t0 = time.perf_counter()
    for i in range(REPEATS):
        call_t0 = time.perf_counter()
        sampleset = sampler.sample(bqm, label=f"v4-hybrid-rep{i}: {fp}")
        runtimes.append(time.perf_counter() - call_t0)

        best_pruned, best_sample = None, None
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
        "runtimes_s": runtimes,
        "wall_clock_s": elapsed,
    }


if __name__ == "__main__":
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
        save_state(state)  # save after every floorplan
        print(
            f"  {fp}: OLD(pruned) gap={r['pruned_gap_pct_OLD_BUGGY']:.2f}%  "
            f"FIXED(unpruned) gap={r['unpruned_gap_pct_FIXED']:.2f}%  "
            f"[{r['wall_clock_s']:.1f}s]"
        )
    print(f"\nSaved: {OUT_PATH}")
