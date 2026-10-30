"""Pinned dependencies stay limited to what the service imports."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNUSED = {"pandas", "seaborn"}


def pinned(path: Path) -> set[str]:
    names = set()
    for line in path.read_text().splitlines():
        m = re.match(r"([A-Za-z0-9_.\-]+)", line.strip())
        if m and not line.lstrip().startswith(("#", "-")):
            names.add(m.group(1).lower())
    return names


def test_unused_packages_are_not_pinned():
    for name in ("requirements.in", "requirements.txt"):
        assert not UNUSED & pinned(ROOT / name), f"{name} still pins {UNUSED & pinned(ROOT / name)}"


def test_no_source_imports_the_removed_packages():
    sources = [p for p in ROOT.rglob("*.py") if "venv" not in p.parts] + list(ROOT.rglob("*.ipynb"))
    for path in sources:
        text = path.read_text()
        for pkg in UNUSED:
            assert not re.search(rf"^\s*(import|from)\s+{pkg}\b|\"(import|from) {pkg}\b", text, re.MULTILINE), f"{path} imports {pkg}"
