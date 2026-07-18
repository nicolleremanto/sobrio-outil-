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
`conftest_helpers.py`, sans créer de vrai `conftest.py`), soit par
`router/data/generate_corpus.py` (chantier R4, correction M1) qui insère
lui-même `router/eval/` dans `sys.path` pour devenir GOLDEN-AWARE : les
fonctions `signal_signature`/`golden_signatures` ci-dessous sont l'UNIQUE
source de vérité de la « signature canonique » d'une ligne de signaux —
aucun autre module ne réimplémente cette logique (les VALEURS du golden ne
sont, elles, jamais recopiées : seule cette fonction de hachage l'est).
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


def signal_signature(prompt: dict, conversation: dict) -> tuple:
    """Signature CANONIQUE d'une paire (prompt, conversation) — mêmes champs, même ordre.

    Fonction de hachage PURE (aucune I/O) : sert à comparer deux SOURCES de
    signaux (golden vs. corpus synthétique) sans jamais recopier leurs
    valeurs — seule cette définition est partagée (M1, anti-fuite). `prompt`
    et `conversation` sont des dicts au format JSON du schéma `Signals`
    (`sobrio_router.types`) ; `keyword_flags` est trié pour rester stable
    quel que soit l'ordre d'insertion.
    """
    return (
        prompt["char_len"],
        prompt["token_est"],
        prompt["lang"],
        prompt["has_code"],
        prompt["has_math"],
        tuple(sorted(prompt["keyword_flags"])),
        conversation["msg_count"],
        conversation["context_token_est"],
        conversation["seen_code"],
        conversation["seen_math"],
        conversation["seen_reasoning"],
        conversation["current_model"],
        conversation["recos_shown"],
        conversation["recos_followed"],
        conversation["derogations_up"],
    )


def golden_entry_signature(entry: GoldenEntry) -> tuple:
    """Signature canonique (`signal_signature`) d'une entrée golden déjà typée."""
    p, c = entry.signals.prompt, entry.signals.conversation
    return signal_signature(
        {
            "char_len": p.char_len,
            "token_est": p.token_est,
            "lang": p.lang,
            "has_code": p.has_code,
            "has_math": p.has_math,
            "keyword_flags": list(p.keyword_flags),
        },
        {
            "msg_count": c.msg_count,
            "context_token_est": c.context_token_est,
            "seen_code": c.seen_code,
            "seen_math": c.seen_math,
            "seen_reasoning": c.seen_reasoning,
            "current_model": c.current_model,
            "recos_shown": c.recos_shown,
            "recos_followed": c.recos_followed,
            "derogations_up": c.derogations_up,
        },
    )


def golden_signatures(path: Path = GOLDEN_PATH) -> frozenset[tuple]:
    """Ensemble des signatures canoniques de TOUT le golden set (M1, anti-fuite).

    Utilisé par `generate_corpus.py` pour re-tirer, PENDANT la génération,
    toute ligne dont la signature coïnciderait avec une entrée golden — et
    par les tests pour vérifier l'intersection vide au N LIVRÉ (30 000).
    """
    return frozenset(golden_entry_signature(e) for e in load_golden(path))
