#!/usr/bin/env python3
"""Check configured providers."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.providers.smoke import run_configured_smoke_tests


async def main() -> int:
    parser = argparse.ArgumentParser(description="Verify configured OASIS providers")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List probes without calling external APIs",
    )
    args = parser.parse_args()

    result = await run_configured_smoke_tests(live=not args.dry_run)
    print(json.dumps(result, indent=2))
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
