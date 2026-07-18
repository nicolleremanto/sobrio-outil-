"""Fixtures partagées des tests du routeur (chantier R5).

Premier vrai `conftest.py` du lot : la fixture `artefact_v05` est
SESSION-SCOPED (un entraînement complet ~3 s, UNE fois pour toute la
session) — impossible à partager entre fichiers autrement. La fabrique de
signaux, elle, reste dans `conftest_helpers.py` (import explicite, cf. sa
docstring).

`sys.path` : insère `router/train/` et `router/eval/` (modules autonomes,
même convention que les autres fichiers de tests du lot).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROUTER_DIR = Path(__file__).resolve().parents[1]
for _sub in ("train", "eval"):
    _p = str(_ROUTER_DIR / _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)


@pytest.fixture(scope="session")
def artefact_v05(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Artefact candidat ENTRAÎNÉ (fonctions réelles de train_v05, corpus de référence).

    Écrit dans un répertoire de session jetable — jamais dans
    `router/artifacts/models/` (les tests ne touchent pas aux artefacts
    réels du poste).
    """
    pytest.importorskip("lightgbm")
    import train_v05

    if not train_v05.DEFAULT_CORPUS_PATH.is_file():
        pytest.skip("corpus de référence absent — régénérer via make router-corpus")
    out_dir = tmp_path_factory.mktemp("artefact_v05")
    train_v05.run_training(train_v05.DEFAULT_CORPUS_PATH, out_dir)
    return out_dir
