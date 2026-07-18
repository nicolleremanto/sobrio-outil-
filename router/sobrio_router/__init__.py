"""sobrio_router — routeur de recommandation Sobrio (classifieur, pas de LLM).

R1 : socle (types, interface, repli) + v0 heuristique. Voir
`docs/decisions/ROUTEUR_CLASSIFIEUR.md` pour l'architecture cible (deux
étages) et `docs/rfc/RFC-0001-signals-conversation.md` pour le schéma des
signaux.
"""

from __future__ import annotations

from .adapter import features_to_signals
from .heuristic import HeuristicRouter
from .interface import Router
from .safe import SafeRouter
from .types import ConversationSignals, Decision, PromptSignals, Signals

__all__ = [
    "ConversationSignals",
    "Decision",
    "HeuristicRouter",
    "PromptSignals",
    "Router",
    "SafeRouter",
    "Signals",
    "features_to_signals",
]
