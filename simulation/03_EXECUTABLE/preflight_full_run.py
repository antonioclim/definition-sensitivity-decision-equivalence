from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_ROOT))

from odsa_econ.protocol import expand_full_grid, load_protocol, validate_protocol, verify_freeze  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight the authorised EINT-R3 full execution without running it.")
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--freeze", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--workers", required=True, type=int)
    parser.add_argument("--minimum-free-gb", type=float, default=2.0)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()

    if args.workers <= 0:
        raise SystemExit("workers must be positive")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    existing = [p.name for p in args.output_dir.iterdir()]
    if existing:
        raise SystemExit(f"full output directory must be empty: {existing[:10]}")

    protocol = load_protocol(args.protocol)
    validation = validate_protocol(protocol)
    freeze = verify_freeze(args.protocol, args.freeze)
    cells = expand_full_grid(protocol)
    usage = shutil.disk_usage(args.output_dir)
    free_gb = usage.free / (1024**3)
    cpu_count = os.cpu_count() or 1
    checks = {
        "protocol_validation": validation["status"] == "PASS",
        "freeze_validation": freeze["status"] == "PASS",
        "cell_count": len(cells) == int(protocol["execution"]["declared_unique_full_cell_count"]),
        "worker_count_positive": args.workers > 0,
        "worker_count_not_above_visible_cpu": args.workers <= cpu_count,
        "free_storage": free_gb >= args.minimum_free_gb,
        "output_directory_empty": not existing,
    }
    report = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "visible_cpu_count": cpu_count,
        "requested_workers": args.workers,
        "free_storage_gb": free_gb,
        "minimum_free_storage_gb": args.minimum_free_gb,
        "unique_cells": len(cells),
        "streams_per_cell": int(protocol["execution"]["full_stream_count"]),
        "replications_per_stream": int(protocol["execution"]["full_replications_per_stream"]),
        "full_replications": len(cells) * int(protocol["execution"]["full_replications_per_cell"]),
        "estimated_cell_summary_rows": len(cells) * 3988,
        "estimated_stream_summary_rows": len(cells) * int(protocol["execution"]["full_stream_count"]) * 1582,
        "full_execution_performed": False,
    }
    destination = args.report or args.output_dir.parent / "EINT_R3_FULL_RUN_PREFLIGHT.json"
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
