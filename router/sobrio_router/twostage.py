"""TwoStageRouter — composition étage 1 + étage 2, arbitrage D3 (spec R6 §2.1, §5.3).

AUCUN import de `embed`/`ml` au niveau module (§1.1) : les instances sont
INJECTÉES déjà construites par le bridge (`stage2` est un `EmbedRouter` en
production, ou `None` — modèle absent, dérive, dépendances manquantes :
cas NOMINAL sur clone frais).

`decide()` ne lève que si `stage1.decide()` lève — cas couvert par le
`SafeRouter` au-dessus (invariant §5.2 : l'API n'est JAMAIS indisponible).
Toute exception de l'étage 2 → repli fin silencieux sur la décision étage 1,
`rule` de l'étage 1 conservée (observabilité fine du repli : TODO V2, même
décision que R1).

Le plafond 0.74 (D3) n'apparaît PAS ici : il est appliqué UNIQUEMENT par
`EmbedHead.predict` (chaîne §5.2bis, valeur `confidence_cap` du metadata) —
ce routeur reçoit une `d2` déjà plafonnée, identique à celle que mesure le
harnais (correction MAJOR-1, 2026-07-23).
"""

from __future__ import annotations

from .interface import Router
from .types import Decision, Signals

# Seuil d'arbitrage D3 : l'étage 2 ne s'exécute QUE si la confiance de
# l'étage 1 est SOUS la bande d'auto-bascule RFC-0003 (< 0.75) — un étage 1
# confiant n'est jamais contredit par une tête v0, et le coût latence n'est
# payé que sur les cas ambigus.
STAGE2_ARBITRATION_THRESHOLD: float = 0.75


class TwoStageRouter(Router):
    """Compose l'étage 1 (toujours calculé) et l'étage 2 optionnel (§2.1)."""

    def __init__(self, stage1: Router, stage2: Router | None) -> None:
        self._stage1 = stage1
        self._stage2 = stage2

    def decide(self, signals: Signals) -> Decision:
        # 1. L'étage 1 répond TOUJOURS d'abord (§2.1.1).
        d1 = self._stage1.decide(signals)
        # 2. Étage 2 absent OU pas de texte → d1 tel quel : le REFUS de
        # traiter le texte est silencieux et sans coût (§2.1.2).
        if self._stage2 is None or signals.prompt.prompt_text is None:
            return d1
        # Arbitrage D3 : un étage 1 confiant (≥ 0.75) court-circuite —
        # l'étage 2 n'est alors JAMAIS invoqué (§5.3, testé par spy).
        if d1.confidence >= STAGE2_ARBITRATION_THRESHOLD:
            return d1
        # 3. Arbitrage sous try/except : TOUTE exception de l'étage 2 (refus,
        # probas non finies, panne arbitraire) → repli fin sur d1 (§2.1.3).
        try:
            d2 = self._stage2.decide(signals)
            if d2.confidence > d1.confidence:
                return d2
        except Exception:
            pass
        return d1
