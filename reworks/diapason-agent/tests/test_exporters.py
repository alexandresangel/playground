import subprocess
import sys
from pathlib import Path


def test_real_exporters_in_isolated_process():
    root = Path(__file__).parents[1]
    result = subprocess.run(
        [sys.executable, str(root / "scripts/telemetry_check.py")],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "correlation passed" in result.stdout
