"""sobrio_router — routeur de recommandation Sobrio (classifieur, pas de LLM).

R1 : socle (types, interface, repli) + v0 heuristique. Voir
`docs/decisions/ROUTEUR_CLASSIFIEUR.md` pour l'architecture cible (deux
étages) et `docs/rfc/RFC-0001-signals-conversation.md` pour le schéma des
signaux.
"""

from __future__ import annotations

from .adapter import features_to_signals
from .heuristic import VISIBLE_MODELS, HeuristicRouter
from .interface import Router
from .safe import SafeRouter
from .twostage import TwoStageRouter
from .types import ConversationSignals, Decision, PromptSignals, Signals

# `TwoStageRouter` est exporté (composition servie par le bridge, R6) ;
# `EmbedRouter` ne l'est PAS — sa construction est réservée au bridge et aux
# harnais, comme `MLRouter` (spec R6 §1.2).
__all__ = [
    "VISIBLE_MODELS",
    "ConversationSignals",
    "Decision",
    "HeuristicRouter",
    "PromptSignals",
    "Router",
    "SafeRouter",
    "Signals",
    "TwoStageRouter",
    "features_to_signals",
]
