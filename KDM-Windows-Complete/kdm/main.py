"""
KDM application entry when run as a module::

    python3 -m kdm.main

Delegates to the legacy single-file app at the repository root (``kdm.py``).
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path


def main() -> None:
    legacy = Path(__file__).resolve().parent.parent / "kdm.py"
    if not legacy.is_file():
        print("[KDM] Missing:", legacy)
        sys.exit(1)
    runpy.run_path(str(legacy), run_name="__main__")


if __name__ == "__main__":
    main()
