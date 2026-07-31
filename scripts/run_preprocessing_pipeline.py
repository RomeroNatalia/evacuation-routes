"""Rebuild deterministic preprocessing outputs for one floorplan.

Examples:

    python scripts/run_preprocessing_pipeline.py --floorplan FP01
    python scripts/run_preprocessing_pipeline.py --floorplan FP05

FP01 is used when ``--floorplan`` is omitted.
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from fire_evacuation.project import floorplan_paths_from_argv  # noqa: E402

FLOORPLAN = floorplan_paths_from_argv(ROOT)

STEPS = [
    "run_classical_routing.py",
    "run_congestion_analysis.py",
    "generate_edge_route_incidence_matrix.py",
    "render_floorplan_routes.py",
    "render_dijkstra_vs_congestion.py",
]


def main() -> None:
    for number, script_name in enumerate(STEPS, start=1):
        print(
            f"\n[{number}/{len(STEPS)}] Running {script_name} "
            f"for {FLOORPLAN.floorplan_id}..."
        )
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / script_name),
                "--floorplan",
                FLOORPLAN.floorplan_id,
            ],
            cwd=ROOT,
            check=True,
        )

    print("\nPreprocessing pipeline completed successfully.")
    print(f"Floorplan: {FLOORPLAN.floorplan_id}")
    print(f"Outputs: {FLOORPLAN.output_dir}")


if __name__ == "__main__":
    main()
