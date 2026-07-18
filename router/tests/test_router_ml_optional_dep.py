"""Test « sans lightgbm » RÉEL (spec R5 §7.1/§13.11) — subprocess isolé.

Un meta-path finder en tête de `sys.meta_path` BLOQUE tout import de
lightgbm dans un interpréteur frais : `sobrio_router` (heuristique comprise)
doit rester pleinement fonctionnel, `from sobrio_router.ml import MLRouter`
doit réussir (import paresseux §7.1), et SEULE la CONSTRUCTION doit échouer —
en `MLRouterLoadError`, jamais en `ImportError` nu (le bridge s'y fie).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_SCRIPT = """
import sys


class _BloqueurLightgbm:
    def find_spec(self, name, path=None, target=None):
        if name == "lightgbm" or name.startswith("lightgbm."):
            raise ImportError("lightgbm bloque (simulation absence)")
        return None


sys.meta_path.insert(0, _BloqueurLightgbm())

# 1. Le paquet s'importe et l'heuristique decide normalement SANS lightgbm.
import sobrio_router
from sobrio_router import ConversationSignals, HeuristicRouter, PromptSignals, Signals

signals = Signals(
    prompt=PromptSignals(
        char_len=100, token_est=40, lang="fr", has_code=False, has_math=False, keyword_flags=()
    ),
    conversation=ConversationSignals(),
)
decision = HeuristicRouter().decide(signals)
assert decision.rule.startswith("heuristic:"), decision

# 2. L'import du MODULE ml reste possible (lightgbm paresseux, §7.1).
from sobrio_router.ml import MLRouter, MLRouterLoadError

# 3. Seule la CONSTRUCTION échoue — MLRouterLoadError, pas ImportError nu.
try:
    MLRouter(sys.argv[1])
except MLRouterLoadError:
    print("OK-sans-lightgbm")
except ImportError as exc:
    raise SystemExit(f"ImportError nu au lieu de MLRouterLoadError : {exc}")
else:
    raise SystemExit("construction inattendue sans lightgbm")
"""


def test_import_sans_lightgbm(tmp_path: Path):
    proc = subprocess.run(
        [sys.executable, "-c", _SCRIPT, str(tmp_path / "artefact-inexistant")],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert "OK-sans-lightgbm" in proc.stdout
    assert "Traceback" not in proc.stderr
