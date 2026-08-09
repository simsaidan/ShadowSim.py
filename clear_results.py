#!/usr/bin/env python3
"""Clear generated simulation result files under results/."""

from __future__ import annotations

import shutil
from pathlib import Path


def clear_results(results_dir: Path) -> tuple[int, list[Path]]:
    """Delete all files/directories inside results_dir except .gitkeep.

    Return number of removed entries and a list of removed paths.
    """
    if not results_dir.exists():
        return 0, []

    removed: list[Path] = []
    for entry in results_dir.iterdir():
        if entry.name == ".gitkeep":
            continue
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()
        removed.append(entry)
    return len(removed), removed


def main() -> None:
    """Clear the repository ``results/`` directory and print what was removed."""
    root = Path(__file__).resolve().parent
    results_dir = root / "results"
    count, removed = clear_results(results_dir)
    print(f"Cleared {count} item(s) from {results_dir}")
    for path in removed:
        print(f" - {path.name}")


if __name__ == "__main__":
    main()
