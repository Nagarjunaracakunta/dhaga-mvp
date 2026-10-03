"""Modules may import backend.shared but never each other, so they can later become separate services."""
import re
from pathlib import Path

MODULES = Path(__file__).resolve().parents[1] / "backend" / "modules"


def test_modules_do_not_import_each_other():
    names = [p.name for p in MODULES.iterdir() if p.is_dir() and not p.name.startswith("__")]
    for name in names:
        others = "|".join(n for n in names if n != name)
        pattern = re.compile(rf"backend\.modules\.({others})\b|from \.\.({others})\b")
        for f in (MODULES / name).rglob("*.py"):
            assert not pattern.search(f.read_text()), f"{f} imports another module"
