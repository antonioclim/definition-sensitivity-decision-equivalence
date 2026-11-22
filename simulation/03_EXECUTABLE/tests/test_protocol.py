from pathlib import Path

from odsa_econ.protocol import expand_full_grid, load_protocol, validate_protocol, verify_freeze

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "02_FROZEN_PROTOCOL" / "eint_r2_decision_protocol.yml"
FREEZE = ROOT / "02_FROZEN_PROTOCOL" / "eint_r2_decision_protocol.freeze.json"


def test_protocol_and_freeze_pass() -> None:
    protocol = load_protocol(PROTOCOL)
    result = validate_protocol(protocol)
    assert result["unique_full_cell_count"] == 270
    assert result["full_replicate_row_count"] == 1_080_000
    assert verify_freeze(PROTOCOL, FREEZE)["status"] == "PASS"


def test_grid_deduplication_and_module_membership() -> None:
    cells = expand_full_grid(load_protocol(PROTOCOL))
    assert len(cells) == 270
    assert len({cell["cell_id"] for cell in cells}) == 270
    assert any(len(cell["modules"]) > 1 for cell in cells)
