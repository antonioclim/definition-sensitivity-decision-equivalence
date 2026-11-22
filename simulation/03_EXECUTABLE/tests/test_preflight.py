from pathlib import Path
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
EXEC = ROOT / "03_EXECUTABLE"
PROTOCOL = ROOT / "02_FROZEN_PROTOCOL" / "eint_r2_decision_protocol.yml"
FREEZE = ROOT / "02_FROZEN_PROTOCOL" / "eint_r2_decision_protocol.freeze.json"


def test_preflight_passes_for_empty_directory(tmp_path: Path) -> None:
    output = tmp_path / "full"
    report = tmp_path / "preflight.json"
    completed = subprocess.run(
        [
            sys.executable,
            str(EXEC / "preflight_full_run.py"),
            "--protocol",
            str(PROTOCOL),
            "--freeze",
            str(FREEZE),
            "--output-dir",
            str(output),
            "--workers",
            "1",
            "--minimum-free-gb",
            "0.001",
            "--report",
            str(report),
        ],
        cwd=EXEC,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["status"] == "PASS"
    assert payload["full_execution_performed"] is False
