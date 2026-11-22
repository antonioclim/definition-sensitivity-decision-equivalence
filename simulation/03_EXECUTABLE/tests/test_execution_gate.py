from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
EXEC = ROOT / "03_EXECUTABLE"
PROTOCOL = ROOT / "02_FROZEN_PROTOCOL" / "eint_r2_decision_protocol.yml"
FREEZE = ROOT / "02_FROZEN_PROTOCOL" / "eint_r2_decision_protocol.freeze.json"


def test_full_execution_requires_explicit_authorisation(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(EXEC / "run_protocol.py"),
            "--protocol",
            str(PROTOCOL),
            "--freeze",
            str(FREEZE),
            "--output-dir",
            str(tmp_path),
            "--mode",
            "full",
        ],
        cwd=EXEC,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert "FULL EXECUTION REFUSED" in completed.stderr + completed.stdout
