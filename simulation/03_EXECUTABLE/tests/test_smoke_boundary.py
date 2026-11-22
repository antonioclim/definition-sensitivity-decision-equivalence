import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SMOKE = ROOT / "04_SMOKE_OUTPUTS_NOT_MANUSCRIPT_EVIDENCE"


def test_smoke_outputs_are_not_mislabelled_as_evidence() -> None:
    execution = json.loads((SMOKE / "EXECUTION_SUMMARY.json").read_text(encoding="utf-8"))
    assert execution["mode"] == "smoke"
    assert execution["full_results_generated"] is False
    assert execution["manuscript_evidence"] is False
    notice = (SMOKE / "NOT_MANUSCRIPT_EVIDENCE.txt").read_text(encoding="utf-8")
    assert "must not be cited as scientific evidence" in notice
