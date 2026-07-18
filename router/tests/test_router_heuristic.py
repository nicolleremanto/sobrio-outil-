"""Tests de HeuristicRouter : chaque règle (cas positifs) + priorité entre règles.

Convention : `make_signals(**overrides)` distribue les clés reconnues de
`PromptSignals` dans `prompt`, tout le reste dans `conversation` (neutre par
défaut) — voir `conftest_helpers.py`.
"""

from __future__ import annotations

from conftest_helpers import make_signals

from sobrio_router import HeuristicRouter

router = HeuristicRouter()


# --- Règle 1 : heuristic:code_context ---------------------------------------


def test_code_context_from_has_code():
    decision = router.decide(make_signals(has_code=True))
    assert decision.rule == "heuristic:code_context"
    assert decision.model == "claude-sonnet-5"
    assert decision.confidence == 0.70


def test_code_context_from_conversation_seen_code():
    decision = router.decide(make_signals(seen_code=True))
    assert decision.rule == "heuristic:code_context"


def test_code_context_from_keyword_flag():
    decision = router.decide(make_signals(keyword_flags=("code",)))
    assert decision.rule == "heuristic:code_context"


def test_code_context_wins_over_reasoning():
    """Priorité : le code prime sur le raisonnement (ordre des règles)."""
    decision = router.decide(make_signals(has_code=True, has_math=True))
    assert decision.rule == "heuristic:code_context"


# --- Règle 2 : heuristic:reasoning_context -----------------------------------


def test_reasoning_context_from_has_math():
    decision = router.decide(make_signals(has_math=True, token_est=200))
    assert decision.rule == "heuristic:reasoning_context"
    assert decision.model == "claude-sonnet-5"


def test_reasoning_context_from_conversation_seen_math():
    decision = router.decide(make_signals(seen_math=True, token_est=200))
    assert decision.rule == "heuristic:reasoning_context"


def test_reasoning_context_from_conversation_seen_reasoning():
    decision = router.decide(make_signals(seen_reasoning=True, token_est=200))
    assert decision.rule == "heuristic:reasoning_context"


def test_reasoning_context_from_demonstration_flag():
    decision = router.decide(make_signals(keyword_flags=("demonstration",), token_est=200))
    assert decision.rule == "heuristic:reasoning_context"


def test_reasoning_context_short_prompt_in_thread_is_the_product_scenario():
    """LE scénario produit : un « démontre-le » court dans un fil de maths.

    Sans mémoire de conversation, un routeur naïf enverrait ce prompt court
    sur le modèle le plus léger (règle 4) ; `seen_reasoning` le rattrape ici.
    Confiance MODÉRÉE (0.60) : le contexte compense sans effacer
    l'incertitude d'un message isolé très court.
    """
    decision = router.decide(make_signals(token_est=10, seen_reasoning=True))
    assert decision.rule == "heuristic:reasoning_context"
    assert decision.confidence == 0.60


def test_reasoning_context_long_prompt_has_higher_confidence():
    decision = router.decide(make_signals(has_math=True, token_est=200))
    assert decision.confidence == 0.75


def test_reasoning_context_wins_over_short_simple():
    """Priorité explicite : raisonnement (règle 2) avant prompt-court (règle 4)."""
    without_reasoning = router.decide(make_signals(token_est=10))
    with_reasoning = router.decide(make_signals(token_est=10, seen_math=True))
    assert without_reasoning.rule == "heuristic:short_simple"
    assert with_reasoning.rule == "heuristic:reasoning_context"


# --- Règle 3 : heuristic:light_transform -------------------------------------


def test_light_transform_resume():
    decision = router.decide(make_signals(token_est=100, keyword_flags=("resume",)))
    assert decision.rule == "heuristic:light_transform"
    assert decision.model == "claude-haiku-4-5"
    assert decision.confidence == 0.70


def test_light_transform_traduction():
    decision = router.decide(make_signals(token_est=100, keyword_flags=("traduction",)))
    assert decision.rule == "heuristic:light_transform"


def test_light_transform_requires_small_prompt():
    """token_est >= 800 : trop long pour rester une transformation « légère »."""
    decision = router.decide(make_signals(token_est=800, keyword_flags=("resume",)))
    assert decision.rule != "heuristic:light_transform"


def test_light_transform_requires_small_conversation_context():
    """context_token_est >= 4000 : un résumé de fil massif n'est plus léger."""
    decision = router.decide(
        make_signals(token_est=100, keyword_flags=("resume",), context_token_est=4000)
    )
    assert decision.rule != "heuristic:light_transform"


# --- Règle 4 : heuristic:short_simple -----------------------------------------


def test_short_simple_default_case():
    decision = router.decide(make_signals(token_est=50))
    assert decision.rule == "heuristic:short_simple"
    assert decision.model == "claude-haiku-4-5"
    assert decision.confidence == 0.80


def test_short_simple_fails_with_heavy_flag_contrat():
    decision = router.decide(make_signals(token_est=50, keyword_flags=("contrat",)))
    assert decision.rule != "heuristic:short_simple"


def test_short_simple_fails_with_heavy_flag_analyse():
    decision = router.decide(make_signals(token_est=50, keyword_flags=("analyse",)))
    assert decision.rule != "heuristic:short_simple"


def test_short_simple_fails_with_long_conversation():
    decision = router.decide(make_signals(token_est=50, msg_count=7))
    assert decision.rule != "heuristic:short_simple"


def test_short_simple_fails_with_large_conversation_context():
    decision = router.decide(make_signals(token_est=50, context_token_est=2000))
    assert decision.rule != "heuristic:short_simple"


# --- Règle 5 : heuristic:complex_task -----------------------------------------


def test_complex_task_from_contrat_flag():
    decision = router.decide(make_signals(token_est=100, keyword_flags=("contrat",)))
    assert decision.rule == "heuristic:complex_task"
    assert decision.model == "claude-opus-4-8"
    assert decision.confidence == 0.65


def test_complex_task_from_analyse_flag():
    decision = router.decide(make_signals(token_est=900, keyword_flags=("analyse",)))
    assert decision.rule == "heuristic:complex_task"


def test_complex_task_from_long_prompt():
    decision = router.decide(make_signals(token_est=900))
    assert decision.rule == "heuristic:complex_task"


def test_complex_task_from_large_conversation_context():
    decision = router.decide(make_signals(token_est=100, context_token_est=4001))
    assert decision.rule == "heuristic:complex_task"


# --- Règle 6 : heuristic:default_balanced -------------------------------------


def test_default_balanced_fallback():
    """Ni court-simple (300<=token_est) ni complexe (<=800, <=4000, pas de flag lourd)."""
    decision = router.decide(make_signals(token_est=500))
    assert decision.rule == "heuristic:default_balanced"
    assert decision.model == "claude-sonnet-5"
    assert decision.confidence == 0.55


# --- Totalité de la liste de règles -------------------------------------------


def test_decide_always_returns_a_visible_catalog_model():
    """Jamais claude-fable-5 (visible: false, RFC-0002) — sobriété, pas juste affichage."""
    visible = {"claude-haiku-4-5", "claude-sonnet-5", "claude-opus-4-8"}
    scenarios = [
        make_signals(),
        make_signals(has_code=True),
        make_signals(has_math=True, token_est=300),
        make_signals(token_est=50, keyword_flags=("resume",)),
        make_signals(token_est=50),
        make_signals(token_est=5000),
    ]
    for signals in scenarios:
        decision = router.decide(signals)
        assert decision.model in visible
