"""Run deterministic preprocessing for every included floorplan."""

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from fire_evacuation.project import available_floorplans  # noqa: E402


def main() -> None:
    floorplans = available_floorplans(ROOT)
    if not floorplans:
        raise SystemExit("No standardized floorplans were found.")

    for index, floorplan_id in enumerate(floorplans, start=1):
        print(f"\n=== [{index}/{len(floorplans)}] {floorplan_id} ===")
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "run_preprocessing_pipeline.py"),
                "--floorplan",
                floorplan_id,
            ],
            cwd=ROOT,
            check=True,
        )

    print("\nAll floorplans were processed successfully.")


if __name__ == "__main__":
    main()
