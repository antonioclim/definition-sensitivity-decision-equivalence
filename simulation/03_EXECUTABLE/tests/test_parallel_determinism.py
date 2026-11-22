from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
EXEC = ROOT / "03_EXECUTABLE"
sys.path.insert(0, str(EXEC))

from odsa_econ.protocol import load_protocol  # noqa: E402
from run_protocol import _results  # noqa: E402

PROTOCOL = load_protocol(ROOT / "02_FROZEN_PROTOCOL" / "eint_r2_decision_protocol.yml")


def cells() -> list[dict]:
    result = []
    for raw in PROTOCOL["execution"]["smoke_cells"][:2]:
        cell = dict(raw)
        cell["cell_id"] = cell.pop("smoke_id")
        cell["modules"] = ["parallel_test"]
        result.append(cell)
    return result


def test_parallel_worker_count_does_not_change_ordered_cell_results() -> None:
    sequential = list(_results(PROTOCOL, cells(), 1, 2, 1, False))
    parallel = list(_results(PROTOCOL, cells(), 1, 2, 2, False))
    assert sequential == parallel
