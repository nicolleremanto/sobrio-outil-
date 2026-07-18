"""Alternatives et estimation d'impact, à partir de l'id du modèle recommandé.

Le routage proprement dit (décider QUEL modèle) vit désormais dans le
package `sobrio_router` (chantier R1) — voir `router_bridge.py` pour la
construction de l'instance effective par organisation. Ce module ne garde
que ce qui dépend du catalogue Sobrio (prix, impact), indépendamment de la
façon dont le modèle a été choisi.
"""

from __future__ import annotations

from sobrio_impact import estimate

from .catalog import EUR_PER_USD, model_prices, visible_model_ids
from .schemas import Alternative, Features, ImpactEstimate

# Bande d'incertitude stub sur le coût : +/-20 %.
# TODO(LotB) : bande calibrée (variance réelle des tokens de sortie observés).
_COST_BAND = 0.20


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


def build_alternatives(model_id: str, features: Features) -> list[Alternative]:
    """Les autres modèles du catalogue, avec delta de coût en fourchette.

    Le delta est chiffré autour d'une valeur centrale stub, avec une bande
    +/-20 % — jamais une valeur unique (règle n°3).
    """
    tokens_out = estimate_tokens_out(features)
    reco_cost = _cost_eur_per_call(model_id, features.token_est, tokens_out)
    alternatives = []
    # Alternatives = modèles VISIBLES (proposables à la dérogation) autres que
    # le recommandé — Fable 5 (visible: false) n'apparaît pas dans la réponse.
    for other_id in visible_model_ids():
        if other_id == model_id:
            continue
        delta = _cost_eur_per_call(other_id, features.token_est, tokens_out) - reco_cost
        low, high = sorted((delta * (1 - _COST_BAND), delta * (1 + _COST_BAND)))
        alternatives.append(
            Alternative(
                model=other_id,
                delta_cost_eur_per_call_min=round(low, 6),
                delta_cost_eur_per_call_max=round(high, 6),
            )
        )
    return alternatives


def build_impact_estimate(model_id: str, features: Features) -> ImpactEstimate:
    """Impact de l'appel recommandé, en fourchettes uniquement (règle n°3).

    L'énergie vient de `sobrio_impact.estimate` (Range min-max obligatoire —
    on ne fabrique JAMAIS un scalaire d'impact ici). Le coût est une bande
    stub +/-20 % autour de la valeur centrale. TODO(LotB) : bande calibrée.
    """
    tokens_out = estimate_tokens_out(features)
    energy = estimate(model_id, tokens_out)  # Range(min, max, scope, source)
    cost = _cost_eur_per_call(model_id, features.token_est, tokens_out)
    return ImpactEstimate(
        energy_wh_min=round(energy.min, 6),
        energy_wh_max=round(energy.max, 6),
        cost_eur_min=round(cost * (1 - _COST_BAND), 6),
        cost_eur_max=round(cost * (1 + _COST_BAND), 6),
    )
