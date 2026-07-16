"""Routeur de recommandation — architecture pluggable.

`Router` est l'interface ; `HeuristicRouterV0` est l'implémentation stub du
Lot 0 : trois règles TRIVIALES mais explicables (le champ `rule` de la
réponse est obligatoire par contrat).

TODO(LotB) : routeur v0 heuristique complet (pondération des flags, langue,
pièces jointes, calibration de la confiance).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from sobrio_impact import estimate

from .catalog import EUR_PER_USD, model_ids, model_prices
from .schemas import Alternative, Features, ImpactEstimate

# Flags "lourds" : signaux d'une tâche exigeante (contrat, analyse, code).
_HEAVY_FLAGS = frozenset({"contrat", "analyse", "code"})

# Bande d'incertitude stub sur le coût : +/-20 %.
# TODO(LotB) : bande calibrée (variance réelle des tokens de sortie observés).
_COST_BAND = 0.20


@dataclass(frozen=True)
class Decision:
    """Décision de routage : modèle, règle explicable, confiance."""

    model_id: str
    rule: str
    confidence: float


class Router(ABC):
    """Interface de routeur : features (jamais de texte) -> décision."""

    @abstractmethod
    def decide(self, features: Features) -> Decision:
        """Décide du modèle recommandé à partir des seules features."""


class HeuristicRouterV0(Router):
    """Trois règles triviales mais explicables (stub Lot 0)."""

    def decide(self, features: Features) -> Decision:
        flags = set(features.keyword_flags)
        # (a) court, sans code ni flag lourd -> le modèle le plus léger.
        if (
            features.token_est < 300
            and not features.has_code
            and not (flags & _HEAVY_FLAGS)
        ):
            return Decision("haiku-4-5", "heuristic:short_simple", 0.8)
        # (b) présence de code -> modèle intermédiaire.
        if features.has_code or "code" in flags:
            return Decision("sonnet-4-6", "heuristic:code_task", 0.7)
        # (c) sinon (long, contrat/analyse...) -> modèle le plus capable.
        return Decision("opus-4-8", "heuristic:complex_task", 0.6)


def estimate_tokens_out(features: Features) -> int:
    """Hypothèse stub de tokens de sortie pour chiffrer coût et énergie.

    TODO(LotB) : estimer depuis l'historique réel (par règle et par org).
    """
    return max(150, min(2000, features.token_est))


def _cost_eur_per_call(model_id: str, tokens_in: int, tokens_out: int) -> float:
    """Coût central stub d'un appel (EUR), prix catalogue USD/Mtok."""
    price_in, price_out = model_prices(model_id)
    cost_usd = (tokens_in * price_in + tokens_out * price_out) / 1_000_000
    return cost_usd * EUR_PER_USD


def build_alternatives(decision: Decision, features: Features) -> list[Alternative]:
    """Les autres modèles du catalogue, avec delta de coût en fourchette.

    Le delta est chiffré autour d'une valeur centrale stub, avec une bande
    +/-20 % — jamais une valeur unique (règle n°3).
    """
    tokens_out = estimate_tokens_out(features)
    reco_cost = _cost_eur_per_call(decision.model_id, features.token_est, tokens_out)
    alternatives = []
    for model_id in model_ids():
        if model_id == decision.model_id:
            continue
        delta = _cost_eur_per_call(model_id, features.token_est, tokens_out) - reco_cost
        low, high = sorted((delta * (1 - _COST_BAND), delta * (1 + _COST_BAND)))
        alternatives.append(
            Alternative(
                model=model_id,
                delta_cost_eur_per_call_min=round(low, 6),
                delta_cost_eur_per_call_max=round(high, 6),
            )
        )
    return alternatives


def build_impact_estimate(decision: Decision, features: Features) -> ImpactEstimate:
    """Impact de l'appel recommandé, en fourchettes uniquement (règle n°3).

    L'énergie vient de `sobrio_impact.estimate` (Range min-max obligatoire —
    on ne fabrique JAMAIS un scalaire d'impact ici). Le coût est une bande
    stub +/-20 % autour de la valeur centrale. TODO(LotB) : bande calibrée.
    """
    tokens_out = estimate_tokens_out(features)
    energy = estimate(decision.model_id, tokens_out)  # Range(min, max, scope, source)
    cost = _cost_eur_per_call(decision.model_id, features.token_est, tokens_out)
    return ImpactEstimate(
        energy_wh_min=round(energy.min, 6),
        energy_wh_max=round(energy.max, 6),
        cost_eur_min=round(cost * (1 - _COST_BAND), 6),
        cost_eur_max=round(cost * (1 + _COST_BAND), 6),
    )
