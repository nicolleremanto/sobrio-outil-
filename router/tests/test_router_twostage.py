"""Tests de `TwoStageRouter` (`sobrio_router/twostage.py`) — R6 Lot 3, spec §10.3.

Invariant §5.2 côté routeur : l'étage 1 répond TOUJOURS d'abord ; l'étage 2
n'est invoqué QUE si (stage2 présent) ET (texte présent) ET (conf étage 1
< 0.75) ; toute exception/décision moins confiante de l'étage 2 → décision
étage 1 conservée (rule comprise). Sous `SafeRouter` : décision étage 2
corrompue ou étage 2 qui PEND → `fallback:heuristic`, jamais d'exception.

Le plafond 0.74 n'est PAS testé ici : `TwoStageRouter` ne plafonne pas
(MAJOR-1 — il émet `d2` TELLE QUELLE, prouvé par le cas conf 0.9) ; le cap
vit dans `EmbedHead.predict` (test_router_embed). 100 % stdlib.
"""

from __future__ import annotations

import time
from dataclasses import replace

import pytest
from conftest_helpers import make_signals

import sobrio_router
from sobrio_router import Decision, Router, SafeRouter, Signals, TwoStageRouter
from sobrio_router.twostage import STAGE2_ARBITRATION_THRESHOLD

_SOUPE = "des les aux par sur dans avec pour sans sous vers chez"


def _signals(texte: str | None = _SOUPE) -> Signals:
    base = make_signals()
    return replace(base, prompt=replace(base.prompt, prompt_text=texte))


class _RouteurFixe(Router):
    """Renvoie toujours la même décision ; compte ses invocations (spy)."""

    def __init__(self, decision: Decision) -> None:
        self._decision = decision
        self.appels = 0

    def decide(self, signals: Signals) -> Decision:
        self.appels += 1
        return self._decision


class _RouteurLeveur(Router):
    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.appels = 0

    def decide(self, signals: Signals) -> Decision:
        self.appels += 1
        raise self._exc


class _RouteurLent(Router):
    """Étage 2 qui PEND (au-delà du timeout SafeRouter)."""

    def __init__(self, sommeil_s: float) -> None:
        self._sommeil_s = sommeil_s

    def decide(self, signals: Signals) -> Decision:
        time.sleep(self._sommeil_s)
        return Decision(model="claude-opus-4-8", confidence=0.7, rule="embed:v0")


def _d1(conf: float = 0.4) -> Decision:
    return Decision(model="claude-sonnet-5", confidence=conf, rule="ml:v05")


def _d2(conf: float = 0.6, model: str = "claude-opus-4-8") -> Decision:
    return Decision(model=model, confidence=conf, rule="embed:v0")


# ---------------------------------------------------------------------------
# Court-circuits §2.1.2 : stage2 absent, texte absent.
# ---------------------------------------------------------------------------


def test_stage2_none_retourne_d1_tel_quel():
    stage1 = _RouteurFixe(_d1())
    decision = TwoStageRouter(stage1, None).decide(_signals())
    assert decision is stage1._decision  # d1 TEL QUEL, pas une copie
    assert stage1.appels == 1


def test_sans_texte_stage2_jamais_invoque():
    stage1, stage2 = _RouteurFixe(_d1()), _RouteurFixe(_d2(0.99))
    decision = TwoStageRouter(stage1, stage2).decide(_signals(texte=None))
    assert decision is stage1._decision
    assert stage2.appels == 0  # refus silencieux et sans coût


# ---------------------------------------------------------------------------
# Arbitrage D3 (§5.3) : seuil 0.75, override si conf2 > conf1.
# ---------------------------------------------------------------------------


def test_etage1_confiant_075_exact_stage2_jamais_invoque():
    """Borne : à 0.75 EXACTEMENT (≥), l'étage 2 n'est pas consulté."""
    assert STAGE2_ARBITRATION_THRESHOLD == 0.75
    stage2 = _RouteurFixe(_d2(0.99))
    decision = TwoStageRouter(_RouteurFixe(_d1(0.75)), stage2).decide(_signals())
    assert decision.rule == "ml:v05"
    assert stage2.appels == 0


def test_etage1_sous_la_bande_stage2_invoque():
    stage2 = _RouteurFixe(_d2(0.5))
    TwoStageRouter(_RouteurFixe(_d1(0.7499)), stage2).decide(_signals())
    assert stage2.appels == 1


def test_conf2_superieure_d2_emise():
    stage2 = _RouteurFixe(_d2(0.6))
    decision = TwoStageRouter(_RouteurFixe(_d1(0.4)), stage2).decide(_signals())
    assert decision is stage2._decision
    assert decision.rule == "embed:v0"


@pytest.mark.parametrize("conf2", [0.4, 0.3999], ids=("egale", "inferieure"))
def test_conf2_egale_ou_inferieure_d1_conservee(conf2: float):
    stage1 = _RouteurFixe(_d1(0.4))
    decision = TwoStageRouter(stage1, _RouteurFixe(_d2(conf2))).decide(_signals())
    assert decision is stage1._decision
    assert decision.rule == "ml:v05"


def test_twostage_ne_plafonne_pas_d2():
    """MAJOR-1 : `d2` est émise TELLE QUELLE (0.9 > 0.74) — le plafond vit
    dans `EmbedHead.predict`, pas ici ; une `d2` réellement hors contrat est
    l'affaire de la validation SafeRouter (tests plus bas)."""
    decision = TwoStageRouter(_RouteurFixe(_d1(0.4)), _RouteurFixe(_d2(0.9))).decide(_signals())
    assert decision.confidence == 0.9


def test_conf2_nan_d1_conservee():
    """NaN > x est False : la comparaison échoue proprement vers d1."""
    stage1 = _RouteurFixe(_d1(0.4))
    decision = TwoStageRouter(stage1, _RouteurFixe(_d2(float("nan")))).decide(_signals())
    assert decision is stage1._decision


# ---------------------------------------------------------------------------
# Repli fin §2.1.3 : toute exception de l'étage 2 → d1, rule de d1 conservée.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "exc",
    [ValueError("probas non finies : 3 valeurs"), RuntimeError("panne"), Exception("arbitraire")],
    ids=("valueerror", "runtimeerror", "exception"),
)
def test_stage2_leve_repli_fin_sur_d1(exc: Exception):
    stage1 = _RouteurFixe(_d1(0.4))
    stage2 = _RouteurLeveur(exc)
    decision = TwoStageRouter(stage1, stage2).decide(_signals())
    assert decision is stage1._decision
    assert decision.rule == "ml:v05"  # rule de d1 CONSERVÉE (§2.1.3)
    assert stage2.appels == 1


def test_stage1_leve_decide_propage():
    """§2.1 : `decide()` ne lève que si `stage1.decide()` lève — cas couvert
    par le SafeRouter au-dessus (testé juste après)."""
    router = TwoStageRouter(_RouteurLeveur(RuntimeError("etage 1 KO")), _RouteurFixe(_d2()))
    with pytest.raises(RuntimeError):
        router.decide(_signals())


# ---------------------------------------------------------------------------
# Sous SafeRouter (§10.3) : chaîne de repli complète côté routeur.
# ---------------------------------------------------------------------------


def test_stage1_leve_sous_saferouter_fallback_heuristic():
    primaire = TwoStageRouter(_RouteurLeveur(RuntimeError("etage 1 KO")), _RouteurFixe(_d2()))
    decision = SafeRouter(primaire).decide(_signals())
    assert decision.rule == "fallback:heuristic"


@pytest.mark.parametrize(
    "d2_corrompue",
    [
        Decision(model="claude-fable-5", confidence=0.9, rule="embed:v0"),
        Decision(model="claude-opus-4-8", confidence=float("inf"), rule="embed:v0"),
        Decision(model="claude-opus-4-8", confidence=True, rule="embed:v0"),
    ],
    ids=("modele_hors_catalogue", "conf_inf", "conf_bool"),
)
def test_d2_corrompue_sous_saferouter_replie(d2_corrompue: Decision):
    """Décision étage 2 corrompue GAGNANTE de l'arbitrage → la validation
    SafeRouter existante la rejette → `fallback:heuristic` (réutilise R1)."""
    primaire = TwoStageRouter(_RouteurFixe(_d1(0.4)), _RouteurFixe(d2_corrompue))
    decision = SafeRouter(primaire).decide(_signals())
    assert decision.rule == "fallback:heuristic"
    assert decision.model != "claude-fable-5"


def test_stage2_qui_pend_sous_saferouter_timeout_fallback():
    """Étage 2 qui PEND > timeout → SafeRouter répond quand même (heuristique)."""
    primaire = TwoStageRouter(_RouteurFixe(_d1(0.4)), _RouteurLent(0.5))
    decision = SafeRouter(primaire, timeout_s=0.05).decide(_signals())
    assert decision.rule == "fallback:heuristic"


def test_stage2_leve_sous_saferouter_d1_servie_pas_fallback():
    """Le repli FIN reste fin sous SafeRouter : étage 2 KO mais étage 1 sain
    → la décision étage 1 (rule `ml:v05`) part au contrat, PAS l'heuristique."""
    primaire = TwoStageRouter(_RouteurFixe(_d1(0.4)), _RouteurLeveur(RuntimeError("KO")))
    decision = SafeRouter(primaire).decide(_signals())
    assert decision.rule == "ml:v05"
    assert decision.confidence == 0.4


# ---------------------------------------------------------------------------
# Exports du paquet (§1.2).
# ---------------------------------------------------------------------------


def test_exports_twostage_oui_embedrouter_non():
    assert TwoStageRouter is sobrio_router.TwoStageRouter
    assert "TwoStageRouter" in sobrio_router.__all__
    assert not hasattr(sobrio_router, "EmbedRouter")  # réservé bridge/harnais
    assert "EmbedRouter" not in sobrio_router.__all__
