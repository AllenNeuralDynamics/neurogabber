import sys
from pathlib import Path


def _ensure_src_path():
    """Add project src/ to sys.path for imports when running tests without install."""
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        src = parent / "src"
        if src.exists() and (parent / "pyproject.toml").exists():
            sys.path.insert(0, str(src))
            break


_ensure_src_path()
