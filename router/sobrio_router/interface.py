"""Interface abstraite du routeur (contrat stable, docs/decisions/ROUTEUR_CLASSIFIEUR.md).

`Router.decide(signals) -> Decision` ne change JAMAIS de forme : la séquence
produit v0 heuristique → v0.5 classifieur pré-entraîné → v1 recalibré se
branche entièrement derrière cette interface. Rien ne change côté extension
ni côté contrat `/v1/recommend` quand l'implémentation évolue.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .types import Decision, Signals


class Router(ABC):
    """Un routeur décide d'un modèle à partir de signaux structurés (jamais de texte)."""

    @abstractmethod
    def decide(self, signals: Signals) -> Decision:
        """Décide du modèle recommandé à partir des signaux prompt + conversation."""
