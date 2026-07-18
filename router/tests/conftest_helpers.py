"""Fabrique de signaux partagée par les tests du package `sobrio_router`.

Nommé `conftest_helpers` (et non `conftest.py`) : ce n'est PAS un fichier de
fixtures pytest, juste un module utilitaire importé explicitement — évite
toute confusion avec la découverte automatique de conftest.
"""

from __future__ import annotations

from sobrio_router import ConversationSignals, PromptSignals, Signals

_PROMPT_DEFAULTS: dict = {
    "char_len": 100,
    "token_est": 40,
    "lang": "fr",
    "has_code": False,
    "has_math": False,
    "keyword_flags": (),
}


def make_signals(**overrides: object) -> Signals:
    """Construit un `Signals` valide, surchargeable champ par champ.

    Les clés reconnues de `PromptSignals` vont dans `prompt` ; toutes les
    autres vont dans `conversation` (elle est intégralement optionnelle).
    """
    prompt_kwargs = dict(_PROMPT_DEFAULTS)
    conversation_kwargs: dict = {}
    for key, value in overrides.items():
        if key in prompt_kwargs:
            prompt_kwargs[key] = value
        else:
            conversation_kwargs[key] = value
    return Signals(
        prompt=PromptSignals(**prompt_kwargs),
        conversation=ConversationSignals(**conversation_kwargs),
    )
