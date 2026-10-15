"""Protect frozen public artifacts from optional generation/client tools."""
from pathlib import Path

PUBLIC_ROOT = Path(__file__).resolve().parents[1]


def new_output_directory(path: Path, roots=()):
    target = Path(path).resolve()
    for root in (PUBLIC_ROOT, *roots):
        root = Path(root).resolve()
        if target.is_relative_to(root):
            parts = target.relative_to(root).parts
            if len(parts) < 2 or parts[0] != "generated":
                raise ValueError("Inside the public package, output must use generated/<new-name>")
    if target.exists():
        raise ValueError("Output directory already exists; choose a new directory")
    target.mkdir(parents=True, exist_ok=False)
    return target
