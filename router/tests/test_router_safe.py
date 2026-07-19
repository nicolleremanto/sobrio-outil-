"""Tests de SafeRouter : invariant §5.2 — decide() ne lève JAMAIS.

Couvre : primary qui lève, primary qui dépasse le timeout, primary sain
(décision inchangée), et le filet de tout dernier recours si même le
fallback lève (ne doit normalement jamais arriver).
"""

from __future__ import annotations

import time

from conftest_helpers import make_signals

from sobrio_router import Decision, HeuristicRouter, Router, Signals
from sobrio_router.safe import SafeRouter


class _RaisingRouter(Router):
    """Primaire qui lève systématiquement (simule un artefact ML cassé)."""

    def decide(self, signals: Signals) -> Decision:
        raise RuntimeError("primary router en panne (test)")


class _SlowRouter(Router):
    """Primaire qui dort plus longtemps que le budget de timeout."""

    def __init__(self, sleep_s: float) -> None:
        self._sleep_s = sleep_s

    def decide(self, signals: Signals) -> Decision:
        time.sleep(self._sleep_s)
        return Decision(model="claude-opus-4-8", confidence=0.99, rule="slow:should_not_arrive")


class _StaticRouter(Router):
    """Primaire sain : renvoie toujours la même décision, instantanément."""

    def __init__(self, decision: Decision) -> None:
        self._decision = decision

    def decide(self, signals: Signals) -> Decision:
        return self._decision


class _AlsoRaisingFallback:
    """Faux routeur de repli qui lève lui aussi — ne doit normalement jamais arriver."""

    def decide(self, signals: Signals) -> Decision:
        raise RuntimeError("fallback lui-même en panne (test)")


def test_primary_exception_falls_back_to_heuristic_rule():
    safe = SafeRouter(primary=_RaisingRouter(), fallback=HeuristicRouter(), timeout_s=0.050)
    decision = safe.decide(make_signals(token_est=50))
    assert decision.rule == "fallback:heuristic"
    # Le modèle correspond à ce que l'heuristique aurait décidé (short_simple -> haiku).
    assert decision.model == "claude-haiku-4-5"


def test_primary_timeout_falls_back_to_heuristic_rule():
    safe = SafeRouter(
        primary=_SlowRouter(sleep_s=0.080), fallback=HeuristicRouter(), timeout_s=0.020
    )
    decision = safe.decide(make_signals(token_est=50))
    assert decision.rule == "fallback:heuristic"
    assert decision.model == "claude-haiku-4-5"
    # La décision du primaire (lente) n'a JAMAIS été utilisée.
    assert decision.rule != "slow:should_not_arrive"


def test_primary_healthy_decision_passes_through_unchanged():
    expected = Decision(model="claude-sonnet-5", confidence=0.42, rule="ml:v05")
    safe = SafeRouter(primary=_StaticRouter(expected), fallback=HeuristicRouter(), timeout_s=0.050)
    decision = safe.decide(make_signals())
    assert decision == expected  # rule PAS remplacée : le primaire a répondu à temps.


def test_fallback_rule_name_always_replaced_not_leaked():
    """Même si HeuristicRouter aurait choisi une autre règle, `rule` devient le repli."""
    safe = SafeRouter(primary=_RaisingRouter(), fallback=HeuristicRouter(), timeout_s=0.050)
    decision = safe.decide(make_signals(has_code=True))  # aurait été heuristic:code_context
    assert decision.rule == "fallback:heuristic"
    assert not decision.rule.startswith("heuristic:")


def test_hardcoded_fallback_when_fallback_itself_raises():
    """Filet de tout dernier recours : décision codée en dur, ne dépend d'aucune logique."""
    safe = SafeRouter(primary=_RaisingRouter(), fallback=_AlsoRaisingFallback(), timeout_s=0.050)
    decision = safe.decide(make_signals())
    assert decision.model == "claude-sonnet-5"
    assert decision.confidence == 0.5
    assert decision.rule == "fallback:heuristic"


def test_decide_never_raises_for_a_battery_of_signals():
    """Balayage de signaux variés (aucun texte) : `decide()` ne lève jamais, primaire cassé."""
    safe = SafeRouter(primary=_RaisingRouter(), fallback=HeuristicRouter(), timeout_s=0.050)
    for token_est in (0, 10, 50, 300, 800, 5000):
        for has_code in (True, False):
            for flags in ((), ("contrat",), ("code",)):
                signals = make_signals(token_est=token_est, has_code=has_code, keyword_flags=flags)
                decision = safe.decide(signals)
                assert isinstance(decision, Decision)
                assert decision.rule == "fallback:heuristic"


def test_executor_shared_across_calls_not_recreated():
    """Le pool d'exécution est créé UNE FOIS par instance (pas par appel)."""
    safe = SafeRouter(primary=HeuristicRouter(), fallback=HeuristicRouter(), timeout_s=0.050)
    executor_before = safe._executor
    safe.decide(make_signals())
    safe.decide(make_signals(token_est=900))
    assert safe._executor is executor_before
