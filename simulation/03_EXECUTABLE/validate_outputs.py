from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    required = [
        "PROTOCOL_VALIDATION.json",
        "EXECUTION_SUMMARY.json",
        "CELL_METRIC_SUMMARY.csv",
        "STREAM_METRIC_SUMMARY.csv",
        "NOT_MANUSCRIPT_EVIDENCE.txt",
        "REPLICATE_MECHANICS.json",
    ]
    missing = [name for name in required if not (args.output_dir / name).is_file()]
    if missing:
        raise SystemExit(f"missing output files: {missing}")
    execution = json.loads((args.output_dir / "EXECUTION_SUMMARY.json").read_text(encoding="utf-8"))
    if execution["mode"] != "smoke" or execution["full_results_generated"] or execution["manuscript_evidence"]:
        raise SystemExit("output boundary violation")
    with (args.output_dir / "CELL_METRIC_SUMMARY.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise SystemExit("metric summary is empty")
    forbidden = ["telephone", "country_name", "source_label", "respondent_id", "microdata"]
    combined = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in args.output_dir.rglob("*") if path.is_file())
    hits = [token for token in forbidden if token in combined.lower()]
    report = {
        "status": "PASS" if not hits else "FAIL",
        "required_files": required,
        "metric_rows": len(rows),
        "forbidden_token_hits": hits,
        "sha256": {path.name: sha256(path) for path in sorted(args.output_dir.iterdir()) if path.is_file()},
    }
    (args.output_dir / "OUTPUT_VALIDATION.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if hits:
        raise SystemExit(f"forbidden output tokens: {hits}")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
