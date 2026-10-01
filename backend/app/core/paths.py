"""Locate repo-level folders (prompts/, policy/, evals/) from the repo checkout or the image (/srv)."""

from pathlib import Path


def find_up(name: str, start: Path | None = None) -> Path:
    here = (start or Path(__file__)).resolve()
    for parent in [here, *here.parents]:
        if (parent / name).is_dir():
            return parent / name
    raise FileNotFoundError(f"no {name}/ above {here}")
