#!/usr/bin/env python3
"""Entry point: export Samsung Health data for the last N days into one JSON file.

Usage:
    python3 export_health.py                 # asks how many days, uses newest export in data/
    python3 export_health.py --days 14
    python3 export_health.py --days 14 --out-dir ~/exports   # choose destination folder
    python3 export_health.py --folder path/to/export --days 30 --out out.json
    python3 export_health.py --selftest      # run correctness self-checks

Pure standard library — no pip install required.
"""

import sys
from pathlib import Path

# Make the package importable when run as a plain script from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from shealth_export.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
