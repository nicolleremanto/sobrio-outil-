"""Contrat CLI du point d'entrée de recalibration mensuelle v1."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "router" / "train" / "recalibrate.py"
_MESSAGE = (
    "REFUS : recalibration impossible — télémétrie v1 requise (aucune donnée réelle disponible)"
)


def test_recalibration_refuse_exit_2_sans_traceback():
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert proc.returncode == 2
    assert proc.stdout == ""
    assert proc.stderr.strip() == _MESSAGE
    assert "Traceback" not in proc.stdout + proc.stderr
