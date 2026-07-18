"""Corrections de la ronde 1 (privacy-sentinel FAIL + majors qa/ml) — verrouillées.

Couvre : prompt_text EXCLU de repr/str (fuite trouvée par le sentinel),
validation de `rule` par SafeRouter (None/int -> repli, plus jamais de 500),
confiance non finie (±inf) et bool rejetées, borne contexte 4000 inclusive.
"""

from __future__ import annotations

from conftest_helpers import make_signals

from sobrio_router import (
    ConversationSignals,
    Decision,
    HeuristicRouter,
    PromptSignals,
    Router,
    SafeRouter,
    Signals,
)


class _StubRouter(Router):
    def __init__(self, decision: Decision) -> None:
        self._decision = decision

    def decide(self, signals: Signals) -> Decision:
        return self._decision


# ---------------------------------------------------------------------------
# Privacy (FAIL ronde 1) : le texte ne sort JAMAIS via repr/str.
# ---------------------------------------------------------------------------


def test_prompt_text_never_in_repr_or_str():
    """repr()/str()/f-string d'un signal ne sérialisent JAMAIS le texte.

    Vecteur de fuite trouvé par privacy-sentinel (ronde 1) : un log de debug
    ou une exception non rattrapée passe souvent par repr() — le champ
    réservé doit y être invisible (field(repr=False)).
    """
    sentinel = "SECRET_LEAK_TEST_R1"
    prompt = PromptSignals(
        char_len=10,
        token_est=5,
        lang="fr",
        has_code=False,
        has_math=False,
        keyword_flags=(),
        prompt_text=sentinel,
    )
    bundle = Signals(prompt=prompt, conversation=ConversationSignals())
    for rendered in (repr(prompt), str(prompt), f"{prompt}", repr(bundle), str(bundle)):
        assert sentinel not in rendered
    # Le champ reste bien LISIBLE par l'étage 2 (accès direct, en mémoire).
    assert prompt.prompt_text == sentinel


# ---------------------------------------------------------------------------
# SafeRouter : rule invalide -> repli (major qa ronde 1).
# ---------------------------------------------------------------------------


def test_safe_router_rejects_none_rule():
    """rule=None transmis tel quel ferait un 500 pydantic : repli obligatoire."""
    rogue = _StubRouter(Decision(model="claude-sonnet-5", confidence=0.9, rule=None))
    decision = SafeRouter(primary=rogue).decide(make_signals(token_est=50))
    assert decision.rule == "fallback:heuristic"


def test_safe_router_rejects_non_string_rule():
    rogue = _StubRouter(Decision(model="claude-sonnet-5", confidence=0.9, rule=42))
    decision = SafeRouter(primary=rogue).decide(make_signals(token_est=50))
    assert decision.rule == "fallback:heuristic"


def test_safe_router_rejects_empty_rule():
    rogue = _StubRouter(Decision(model="claude-sonnet-5", confidence=0.9, rule=""))
    decision = SafeRouter(primary=rogue).decide(make_signals(token_est=50))
    assert decision.rule == "fallback:heuristic"


# ---------------------------------------------------------------------------
# SafeRouter : confiance non finie / bool -> repli (major ml ronde 1).
# ---------------------------------------------------------------------------


def test_safe_router_rejects_positive_infinity():
    """+inf n'est PAS un débordement fini : artefact corrompu -> repli, pas 1.0."""
    rogue = _StubRouter(Decision(model="claude-sonnet-5", confidence=float("inf"), rule="ml:v05"))
    decision = SafeRouter(primary=rogue).decide(make_signals(token_est=50))
    assert decision.rule == "fallback:heuristic"


def test_safe_router_rejects_negative_infinity():
    rogue = _StubRouter(Decision(model="claude-sonnet-5", confidence=float("-inf"), rule="ml:v05"))
    decision = SafeRouter(primary=rogue).decide(make_signals(token_est=50))
    assert decision.rule == "fallback:heuristic"


def test_safe_router_rejects_bool_confidence():
    """True/False sont des int en Python : type étranger -> repli (symétrique)."""
    for flag in (True, False):
        rogue = _StubRouter(Decision(model="claude-sonnet-5", confidence=flag, rule="ml:v05"))
        decision = SafeRouter(primary=rogue).decide(make_signals(token_est=50))
        assert decision.rule == "fallback:heuristic", flag


# ---------------------------------------------------------------------------
# Borne contexte 4000 : inclusive, en miroir du < 4000 des règles légères.
# ---------------------------------------------------------------------------


def test_context_exactly_4000_is_complex_task():
    """À 4000 pile : complex_task décide (plus de couture default_balanced)."""
    router = HeuristicRouter()
    decision = router.decide(make_signals(token_est=100, context_token_est=4000))
    assert decision.rule == "heuristic:complex_task"
    # Et la transformation légère bascule bien sur complex au même point.
    resume = router.decide(
        make_signals(token_est=100, keyword_flags=("resume",), context_token_est=4000)
    )
    assert resume.rule == "heuristic:complex_task"
