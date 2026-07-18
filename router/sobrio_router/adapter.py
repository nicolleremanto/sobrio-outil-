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


def features_to_signals(features: _FeaturesLike) -> Signals:
    """Mappe le bloc `features` v1.x vers `Signals`, conversation NEUTRE.

    - `has_math` : absent de `features` v1.0 (signal introduit par
      RFC-0001) -> `False` par défaut.
    - `has_attachment_hint` : volontairement NON interprété en v0 — la
      RFC-0001 ne définit pas encore de portée précise pour ce signal côté
      routeur ; l'ignorer explicitement vaut mieux que lui deviner un sens
      (TODO RFC).
    - `conversation` : tous les champs à leur valeur neutre (zéro / False /
      None) — pas de mémoire de conversation tant que le contrat ne la
      transporte pas.
    """
    prompt = PromptSignals(
        char_len=features.char_len,
        token_est=features.token_est,
        lang=features.lang,
        has_code=features.has_code,
        has_math=False,
        keyword_flags=tuple(features.keyword_flags),
    )
    conversation = ConversationSignals()
    return Signals(prompt=prompt, conversation=conversation)
