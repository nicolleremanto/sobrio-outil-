"""Adaptateur TRANSITOIRE : bloc `features` (contrat v1.x) -> `Signals` (RFC-0001).

Le contrat `/v1/recommend` (`contracts/openapi.yaml`) ne connaît aujourd'hui
que le bloc `features`, calculé sur le seul dernier prompt. Ce module fait le
pont vers `Signals`, l'interface STABLE du routeur : `conversation` est
construite NEUTRE (aucune mémoire de conversation ne transite encore par le
contrat serveur). Même patron que côté extension, où `client.ts` mappe
`signals` -> `features` en sens inverse pour le mode API v1.0.

TODO(RFC-0001) : cet adaptateur SAUTE le jour où le contrat accepte
directement `signals` — `routes.py` construira alors `Signals` sans passer
par `Features`.
"""

from __future__ import annotations

from typing import Protocol

from .types import ConversationSignals, PromptSignals, Signals


class _FeaturesLike(Protocol):
    """Structure minimale attendue — évite une dépendance dure à pydantic/l'API.

    `sobrio_router` n'a AUCUNE dépendance (stdlib seule, R1) : on ne peut pas
    importer `app.schemas.Features` ici sans créer une dépendance inversée
    (l'API dépend du routeur, pas l'inverse). Un `Protocol` structurel suffit.
    """

    char_len: int
    token_est: int
    lang: str
    has_code: bool
    has_attachment_hint: bool
    keyword_flags: list[str]


def features_to_signals(features: _FeaturesLike, *, prompt_text: str | None = None) -> Signals:
    """Mappe le bloc `features` v1.x vers `Signals`, conversation NEUTRE.

    - `has_math` : absent de `features` v1.0 (signal introduit par
      RFC-0001) -> `False` par défaut. CONSÉQUENCE ASSUMÉE (revue
      ml-architect, ronde 0) : la règle `heuristic:reasoning_context` est
      DORMANTE sur le chemin serveur tant que la RFC-0001 n'est pas adoptée
      (le flag `demonstration` n'existe pas non plus dans l'enum v1.0) — le
      scénario « démontre-le court dans un fil maths » ne vit aujourd'hui
      que dans le mock de l'extension. C'est un argument POUR la RFC-0001,
      pas un défaut du routeur.
    - `has_attachment_hint` : mappé prudemment sur le drapeau lourd
      `analyse` (correction ronde 0, ml-architect) — une pièce jointe est un
      signal fort de tâche documentaire ; sans ce mapping, un prompt court
      AVEC pièce jointe partait sur le modèle le plus léger. TODO(RFC) :
      champ dédié dans `signals` plutôt que ce repli sémantique.
    - `conversation` : tous les champs à leur valeur neutre (zéro / False /
      None) — pas de mémoire de conversation tant que le contrat ne la
      transporte pas.
    - `prompt_text` (keyword-only, R6 Lot 1) : `None` par défaut — l'appel
      SANS kwarg reste bit-identique à R5. Fourni (triple verrou §3 ouvert,
      câblé au Lot 4), il est ATTACHÉ tel quel à `PromptSignals` : aucune
      validation, transformation ni journalisation — le texte ne fait que
      transiter EN MÉMOIRE vers l'étage 2 (contrat d'usage strict documenté
      sur `PromptSignals`, verrou de sérialisation compris).
    """
    keyword_flags = tuple(features.keyword_flags)
    if features.has_attachment_hint and "analyse" not in keyword_flags:
        keyword_flags = (*keyword_flags, "analyse")
    prompt = PromptSignals(
        char_len=features.char_len,
        token_est=features.token_est,
        lang=features.lang,
        has_code=features.has_code,
        has_math=False,
        keyword_flags=keyword_flags,
        prompt_text=prompt_text,
    )
    conversation = ConversationSignals()
    return Signals(prompt=prompt, conversation=conversation)
