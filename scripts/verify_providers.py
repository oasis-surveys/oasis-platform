#!/usr/bin/env python3
"""Run the backend provider check."""

from __future__ import annotations

import runpy
from pathlib import Path


if __name__ == "__main__":
    script = Path(__file__).resolve().parents[1] / "backend/scripts/verify_providers.py"
    runpy.run_path(str(script), run_name="__main__")
