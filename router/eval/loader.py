"""Chargement du golden set — reconstruit des `Signals` typés depuis `golden.jsonl`.

Réutilise EXCLUSIVEMENT `sobrio_router.types` (via le paquet installé
`sobrio_router`) : aucune réimplémentation du schéma RFC-0001 ici, conforme à
la consigne du chantier R3. Le golden set est FIGÉ (chantier R2, hash
committé `GOLDEN_SHA256`) : ce module ne fait que LIRE, jamais écrire ni
modifier `golden.jsonl` (le fichier reste sous la responsabilité exclusive de
`generate_golden.py` + re-figeage explicite, cf. `HUMAN_REVIEW_WELCOME.md`).

Module autonome (pas de paquet `router.eval` installé) : importé soit comme
script frère par `harness.py` (import plat `from loader import ...`, le
script étant lancé directement — `python router/eval/harness.py` place son
propre répertoire en tête de `sys.path`), soit par les tests
(`router/tests/test_router_eval_*.py`), qui ajoutent explicitement
`router/eval/` à `sys.path` avant l'import (même esprit que
`conftest_helpers.py`, sans créer de vrai `conftest.py`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from sobrio_router import ConversationSignals, PromptSignals, Signals

GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
GOLDEN_PATH = GOLDEN_DIR / "golden.jsonl"
GOLDEN_SHA_PATH = GOLDEN_DIR / "GOLDEN_SHA256"


@dataclass(frozen=True)
class GoldenEntry:
    """Une entrée du golden set réduite à ce dont l'éval a besoin.

    `note` (description indirecte, jamais de citation de prompt) n'est PAS
    reprise ici : elle ne sert qu'à la relecture humaine (chantier R2), pas
    au protocole d'évaluation.
    """

    id: str
    category: str
    label: str
    signals: Signals


def _entry_from_dict(raw: dict) -> GoldenEntry:
    """Reconstruit une entrée typée depuis un dict JSON (une ligne de `golden.jsonl`)."""
    prompt = PromptSignals(**raw["signals"]["prompt"])
    conversation = ConversationSignals(**raw["signals"]["conversation"])
    return GoldenEntry(
        id=raw["id"],
        category=raw["category"],
        label=raw["label"],
        signals=Signals(prompt=prompt, conversation=conversation),
    )


def load_golden(path: Path = GOLDEN_PATH) -> list[GoldenEntry]:
    """Charge et parse toutes les entrées du golden set (une par ligne JSONL)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return [_entry_from_dict(json.loads(line)) for line in lines if line.strip()]


def golden_sha256(path: Path = GOLDEN_SHA_PATH) -> str:
    """Lit le hash sha256 committé du golden set (première colonne du fichier)."""
    return path.read_text(encoding="utf-8").split()[0]
