"""Adaptateurs de datasets publics — DERRIÈRE FLAG, chantier R4 (§5.5 ROUTEUR_CLASSIFIEUR.md).

Module autonome (même convention que les autres modules de `router/data/` et
`router/eval/loader.py`).

**STATUT AUJOURD'HUI (voir `router/data/LICENSES.md`) : AUCUNE source
publique n'est utilisée.** Ces adaptateurs existent pour documenter
l'architecture d'activation future, ÉTEINTS par défaut, JAMAIS appelés en
CI/tests (les tests utilisent exclusivement des fixtures locales qui
SIMULENT le format des sources — `router/tests/fixtures/`).

Contrat strict :

1. Toute fonction de TÉLÉCHARGEMENT réelle (`download_*`) refuse tant que
   `SOBRIO_ALLOW_DATASET_DOWNLOAD != "1"` (`RuntimeError` explicite,
   renvoyant vers `LICENSES.md`).
2. MÊME quand le flag est activé, ce module n'effectue AUCUN appel réseau
   lui-même — invariant cost-guard « zéro motif réseau dans `router/` »,
   prouvable par grep (aucun import de `httpx`/`requests`/
   `urllib.request`/`socket` ici, testé par `test_router_data_public_datasets.py`).
   L'intégration d'un client de téléchargement réel est une DÉCISION
   D'ORCHESTRATION séparée (revue licence PUIS activation), non livrée ici.
3. Les fonctions de CONVERSION (`convert_*`) sont PURES et ne retiennent QUE
   des SIGNAUX (aucun texte, règle n°1) — elles opèrent sur des
   enregistrements DÉJÀ chargés en mémoire (dicts), au format SIMULÉ des
   sources envisagées, jamais sur de vraies données téléchargées.
"""

from __future__ import annotations

import os
import re

_FLAG_ENV = "SOBRIO_ALLOW_DATASET_DOWNLOAD"

_CODE_HINT_RE = re.compile(r"```|\bdef \b|\bclass \b|\bimport \b|\bSELECT\b|</?[a-zA-Z]+>")
_MATH_HINT_RE = re.compile(r"[=∑∫√]|\\frac|\bequation\b|\béquation\b", re.IGNORECASE)
_FR_STOPWORDS = (" le ", " la ", " les ", " des ", " est ", " et ", " une ", " du ")
_EN_STOPWORDS = (" the ", " is ", " and ", " of ", " to ", " a ", " in ")


def _require_download_flag(source: str) -> None:
    """Lève si `SOBRIO_ALLOW_DATASET_DOWNLOAD` n'est pas EXACTEMENT '1' (défaut : refus)."""
    if os.environ.get(_FLAG_ENV) != "1":
        raise RuntimeError(
            f"téléchargement de « {source} » refusé : {_FLAG_ENV} doit valoir '1' "
            "(défaut : désactivé). Statut actuel (voir router/data/LICENSES.md) : "
            "AUCUNE source publique utilisée — activation réelle = revue licence "
            "explicite, cf. §5.5 docs/decisions/ROUTEUR_CLASSIFIEUR.md."
        )


def download_lmsys_chat_1m(dest_dir: str) -> None:
    """Téléchargement RÉEL de LMSYS-Chat-1M — désactivé (LICENSES.md : NON UTILISÉ).

    Même flag activé, AUCUN appel réseau n'est effectué ici (invariant
    cost-guard) : l'intégration d'un client de téléchargement réel est hors
    périmètre de ce module, décision d'orchestration séparée.
    """
    _require_download_flag("LMSYS-Chat-1M")
    raise NotImplementedError(
        "intégration réseau non livrée dans router/ (zéro motif réseau, cost-guard) — "
        "activation réelle = revue licence + décision fondateurs (LICENSES.md)"
    )


def download_chatbot_arena(dest_dir: str) -> None:
    """Téléchargement RÉEL de Chatbot Arena conversations — désactivé (LICENSES.md)."""
    _require_download_flag("Chatbot Arena conversations")
    raise NotImplementedError(
        "intégration réseau non livrée dans router/ (zéro motif réseau, cost-guard) — "
        "activation réelle = revue licence + décision fondateurs (LICENSES.md)"
    )


def download_routellm_judge_data(dest_dir: str) -> None:
    """Téléchargement RÉEL des données de jugement RouteLLM/GPT-4 — désactivé (LICENSES.md)."""
    _require_download_flag("RouteLLM/GPT-4 judge data")
    raise NotImplementedError(
        "intégration réseau non livrée dans router/ (zéro motif réseau, cost-guard) — "
        "activation réelle = revue licence + décision fondateurs (LICENSES.md)"
    )


def _lang_of(text: str) -> str:
    """Heuristique TRÈS grossière fr/en/other (mots vides fréquents) pour dériver `lang`.

    Le texte source n'est utilisé qu'EN MÉMOIRE, le temps de cet appel — il
    n'est jamais conservé dans la valeur retournée par les fonctions
    `convert_*` (règle n°1).
    """
    lowered = f" {text.lower()} "
    fr_hits = sum(lowered.count(w) for w in _FR_STOPWORDS)
    en_hits = sum(lowered.count(w) for w in _EN_STOPWORDS)
    if fr_hits == 0 and en_hits == 0:
        return "other"
    return "fr" if fr_hits >= en_hits else "en"


def _signals_from_text(text: str) -> dict:
    """Dérive un dict compatible `PromptSignals` depuis un texte EN MÉMOIRE (jamais conservé)."""
    return {
        "char_len": len(text),
        "token_est": max(1, round(len(text) / 4)),
        "lang": _lang_of(text),
        "has_code": bool(_CODE_HINT_RE.search(text)),
        "has_math": bool(_MATH_HINT_RE.search(text)),
        "keyword_flags": [],
    }


def convert_lmsys_record(record: dict) -> dict:
    """Convertit un enregistrement AU FORMAT SIMULÉ LMSYS-Chat-1M en signaux SEULS.

    `record` attendu : `{"conversation": [{"role": "user"|"assistant", "content": str}, ...]}`
    (format SIMULÉ, jamais téléchargé ici — voir
    `router/tests/fixtures/lmsys_sample.jsonl`). Seul le DERNIER tour
    utilisateur alimente les signaux de prompt ; les tours précédents
    n'alimentent que des AGRÉGATS de conversation (jamais leur texte).
    """
    turns = record.get("conversation", [])
    user_turns = [t for t in turns if t.get("role") == "user"]
    last_text = user_turns[-1].get("content", "") if user_turns else ""
    prior_turns = turns[:-1] if turns else []
    return {
        "prompt": _signals_from_text(last_text),
        "conversation": {
            "msg_count": len(turns),
            "context_token_est": sum(
                max(1, round(len(t.get("content", "")) / 4)) for t in prior_turns
            ),
            "seen_code": any(_CODE_HINT_RE.search(t.get("content", "")) for t in prior_turns),
            "seen_math": any(_MATH_HINT_RE.search(t.get("content", "")) for t in prior_turns),
            "seen_reasoning": False,
            "current_model": None,
            "recos_shown": 0,
            "recos_followed": 0,
            "derogations_up": 0,
        },
    }


def convert_chatbot_arena_record(record: dict) -> dict:
    """Convertit un enregistrement AU FORMAT SIMULÉ Chatbot Arena en signaux SEULS.

    `record` attendu : `{"prompt": str}` (un seul tour — format SIMULÉ plus
    simple que LMSYS ; voir `router/tests/fixtures/chatbot_arena_sample.jsonl`).
    """
    return {
        "prompt": _signals_from_text(record.get("prompt", "")),
        "conversation": {
            "msg_count": 0,
            "context_token_est": 0,
            "seen_code": False,
            "seen_math": False,
            "seen_reasoning": False,
            "current_model": None,
            "recos_shown": 0,
            "recos_followed": 0,
            "derogations_up": 0,
        },
    }
