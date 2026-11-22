from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from multiprocessing import get_context
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Iterator

SCRIPT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_ROOT))

from odsa_econ.engine import run_cell  # noqa: E402
from odsa_econ.protocol import expand_full_grid, load_protocol, validate_protocol, verify_freeze  # noqa: E402


class CsvSink:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle = path.open("w", encoding="utf-8-sig", newline="")
        self.writer: csv.DictWriter[str] | None = None
        self.row_count = 0

    def append(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        if self.writer is None:
            self.writer = csv.DictWriter(self.handle, fieldnames=list(rows[0]), extrasaction="raise")
            self.writer.writeheader()
        self.writer.writerows(rows)
        self.row_count += len(rows)

    def close(self) -> None:
        self.handle.close()


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run the frozen EINT decision-layer simulation protocol.")
    p.add_argument("--protocol", required=True, type=Path)
    p.add_argument("--freeze", required=True, type=Path)
    p.add_argument("--output-dir", required=True, type=Path)
    p.add_argument("--mode", choices=("validate", "smoke", "full"), default="validate")
    p.add_argument("--authorise-full", action="store_true", help="Required for full manuscript execution.")
    p.add_argument("--workers", type=int, default=1, help="Parallel cell workers for the authorised full run. Seeds are cell-stable and independent of worker count.")
    return p


def _task(payload: tuple[dict[str, Any], dict[str, Any], int, int, bool]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    protocol, cell, stream_count, replications_per_stream, retain = payload
    return run_cell(
        protocol,
        cell,
        stream_count=stream_count,
        replications_per_stream=replications_per_stream,
        retain_replicate_summaries=retain,
    )


def _results(
    protocol: dict[str, Any],
    cells: list[dict[str, Any]],
    stream_count: int,
    replications_per_stream: int,
    workers: int,
    retain: bool,
) -> Iterator[tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]]:
    tasks = [
        (protocol, cell, stream_count, replications_per_stream, retain)
        for cell in cells
    ]
    if workers == 1:
        for task in tasks:
            yield _task(task)
        return
    with ProcessPoolExecutor(max_workers=workers, mp_context=get_context("spawn")) as executor:
        # executor.map preserves the frozen cell order, so output is independent of completion order.
        yield from executor.map(_task, tasks, chunksize=1)


def main() -> int:
    args = parser().parse_args()
    if args.workers <= 0:
        raise SystemExit("--workers must be positive")
    protocol = load_protocol(args.protocol)
    validation = validate_protocol(protocol)
    freeze = verify_freeze(args.protocol, args.freeze)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "PROTOCOL_VALIDATION.json").write_text(
        json.dumps({"protocol": validation, "freeze": freeze}, indent=2) + "\n",
        encoding="utf-8",
    )
    if args.mode == "validate":
        print(json.dumps({"status": "PASS", "mode": "validate", **validation}, indent=2))
        return 0
    if args.mode == "full" and not args.authorise_full:
        raise SystemExit("FULL EXECUTION REFUSED: pass --authorise-full only in the separately authorised EINT-R3 phase")
    if args.mode == "smoke" and args.workers != 1:
        raise SystemExit("Smoke mode is deliberately single-worker so its mechanics output has one stream and a minimal execution surface")

    if args.mode == "smoke":
        cells: list[dict[str, Any]] = []
        for raw in protocol["execution"]["smoke_cells"]:
            cell = dict(raw)
            cell["cell_id"] = str(cell.pop("smoke_id"))
            cell["modules"] = ["smoke"]
            cells.append(cell)
        stream_count = 1
        replications_per_stream = int(protocol["execution"]["smoke_replications_per_cell"])
        retain = True
    else:
        cells = expand_full_grid(protocol)
        stream_count = int(protocol["execution"]["full_stream_count"])
        replications_per_stream = int(protocol["execution"]["full_replications_per_stream"])
        retain = False

    summary_sink = CsvSink(args.output_dir / "CELL_METRIC_SUMMARY.csv")
    stream_sink = CsvSink(args.output_dir / "STREAM_METRIC_SUMMARY.csv")
    replicate_summaries: list[dict[str, Any]] = []
    try:
        iterator = _results(
            protocol,
            cells,
            stream_count,
            replications_per_stream,
            args.workers,
            retain,
        )
        for cell, (rows, replicates, stream_rows) in zip(cells, iterator, strict=True):
            cell_columns = {k: v for k, v in cell.items() if k != "modules"}
            summary_sink.append([{**cell_columns, **row} for row in rows])
            stream_sink.append([{**cell_columns, **row} for row in stream_rows])
            replicate_summaries.extend(replicates)
    finally:
        summary_sink.close()
        stream_sink.close()

    if args.mode == "smoke":
        (args.output_dir / "REPLICATE_MECHANICS.json").write_text(
            json.dumps(replicate_summaries, indent=2) + "\n", encoding="utf-8"
        )
        (args.output_dir / "NOT_MANUSCRIPT_EVIDENCE.txt").write_text(
            "These smoke outputs test execution mechanics and formal invariants only. "
            "They were generated after protocol freeze with 50 replications per selected cell and must not be cited as scientific evidence.\n",
            encoding="utf-8",
        )

    total_replications = len(cells) * stream_count * replications_per_stream
    execution = {
        "status": "PASS",
        "mode": args.mode,
        "cell_count": len(cells),
        "worker_count": args.workers,
        "stream_count": stream_count,
        "replications_per_stream": replications_per_stream,
        "replications_per_cell": stream_count * replications_per_stream,
        "replicate_count": total_replications,
        "summary_row_count": summary_sink.row_count,
        "stream_summary_row_count": stream_sink.row_count,
        "full_results_generated": args.mode == "full",
        "manuscript_evidence": args.mode == "full",
        "ordered_output_independent_of_worker_completion": True,
        "cpu_count_visible": os.cpu_count(),
    }
    (args.output_dir / "EXECUTION_SUMMARY.json").write_text(json.dumps(execution, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(execution, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
