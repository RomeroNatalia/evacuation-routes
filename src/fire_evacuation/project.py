"""Resolve standardized input and output paths for a floorplan dataset."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import sys


DEFAULT_FLOORPLAN_ID = "FP01"


@dataclass(frozen=True)
class FloorplanPaths:
    """All standardized paths for one floorplan."""

    repository_root: Path
    floorplan_id: str
    floorplan_dir: Path
    input_dir: Path
    output_dir: Path
    nodes_csv: Path
    edges_csv: Path
    occupancy_csv: Path
    metadata_csv: Path
    floorplan_image: Path


def available_floorplans(repository_root: str | Path) -> list[str]:
    """Return all floorplan IDs that contain a standardized input folder."""
    base = Path(repository_root) / "data" / "floorplans"
    if not base.exists():
        return []
    return sorted(
        path.name
        for path in base.iterdir()
        if path.is_dir() and (path / "input").is_dir()
    )


def consume_floorplan_argument(
    default: str = DEFAULT_FLOORPLAN_ID,
) -> str:
    """Read and remove ``--floorplan`` from ``sys.argv``.

    Removing the option preserves the existing optional positional run-count
    arguments used by benchmark and sweep scripts.
    """
    selected = os.environ.get("FLOORPLAN_ID", default).strip().upper()
    cleaned = [sys.argv[0]]
    index = 1

    while index < len(sys.argv):
        argument = sys.argv[index]
        if argument == "--floorplan":
            if index + 1 >= len(sys.argv):
                raise SystemExit("--floorplan requires an ID such as FP01.")
            selected = sys.argv[index + 1].strip().upper()
            index += 2
            continue
        if argument.startswith("--floorplan="):
            selected = argument.split("=", 1)[1].strip().upper()
            index += 1
            continue
        cleaned.append(argument)
        index += 1

    sys.argv[:] = cleaned
    return selected


def floorplan_paths(
    repository_root: str | Path,
    floorplan_id: str,
) -> FloorplanPaths:
    """Resolve and validate one standardized floorplan directory."""
    root = Path(repository_root).resolve()
    floorplan_id = floorplan_id.strip().upper()
    floorplan_dir = root / "data" / "floorplans" / floorplan_id
    input_dir = floorplan_dir / "input"
    output_dir = floorplan_dir / "output"

    required = {
        "graph_nodes.csv": input_dir / "graph_nodes.csv",
        "graph_edges.csv": input_dir / "graph_edges.csv",
        "room_occupancy.csv": input_dir / "room_occupancy.csv",
        "metadata.csv": input_dir / "metadata.csv",
    }
    missing = [name for name, path in required.items() if not path.exists()]
    if missing:
        choices = ", ".join(available_floorplans(root)) or "none"
        raise FileNotFoundError(
            f"Floorplan {floorplan_id} is missing: {', '.join(missing)}. "
            f"Available floorplans: {choices}."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    return FloorplanPaths(
        repository_root=root,
        floorplan_id=floorplan_id,
        floorplan_dir=floorplan_dir,
        input_dir=input_dir,
        output_dir=output_dir,
        nodes_csv=required["graph_nodes.csv"],
        edges_csv=required["graph_edges.csv"],
        occupancy_csv=required["room_occupancy.csv"],
        metadata_csv=required["metadata.csv"],
        floorplan_image=input_dir / "floorplan.png",
    )


def floorplan_paths_from_argv(
    repository_root: str | Path,
    default: str = DEFAULT_FLOORPLAN_ID,
) -> FloorplanPaths:
    """Resolve the floorplan selected by ``--floorplan`` or the environment."""
    return floorplan_paths(repository_root, consume_floorplan_argument(default))
