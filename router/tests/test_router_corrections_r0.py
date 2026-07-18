"""Corrections de la ronde 0 (revue ml-architect + qa-auditor) — verrouillées.

Couvre : validation de la sortie du primaire par SafeRouter, mode
`primary=None` (échec au chargement), plafond Sonnet des transformations
légères longues (plus jamais Opus), absence de bande morte à 800 tokens,
mapping pièce jointe -> drapeau lourd, recoupement des ids avec le catalogue
(source de vérité), et point d'extension `prompt_text` inerte en v0.
"""

from __future__ import annotations

import pathlib

import yaml
from conftest_helpers import make_signals

from sobrio_router import (
    VISIBLE_MODELS,
    Decision,
    HeuristicRouter,
    Router,
    SafeRouter,
    Signals,
    features_to_signals,
)
from sobrio_router.heuristic import _RULES

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Catalogue : la source de vérité recoupe les étiquettes du routeur.
# ---------------------------------------------------------------------------


def _catalog_visible_ids() -> set[str]:
    catalog = yaml.safe_load((_REPO_ROOT / "contracts" / "model_catalog.yaml").read_text())
    return {
        model["id"]
        for model in catalog["models"]
        if model.get("visible", True)  # visible par défaut, comme l'API
    }


def test_visible_models_matches_catalog():
    """VISIBLE_MODELS == ids visibles de contracts/model_catalog.yaml (qa r0)."""
    assert VISIBLE_MODELS == _catalog_visible_ids()


def test_all_rule_outputs_are_visible_catalog_ids():
    """Chaque règle ne peut produire QUE des ids visibles du catalogue."""
    probe = make_signals()  # les lambdas decide() n'utilisent que token_est
    for rule in _RULES:
        model, confidence = rule.decide(probe)
        assert model in _catalog_visible_ids(), rule.name
        assert 0.0 <= confidence <= 1.0, rule.name


# ---------------------------------------------------------------------------
# Transformations légères : plafond Sonnet, aucune bande morte (ml r0).
# ---------------------------------------------------------------------------


def test_light_transform_inclusive_up_to_800_tokens():
    router = HeuristicRouter()
    for tokens in (500, 799, 800):  # borne INCLUSIVE : 800 reste léger
        decision = router.decide(make_signals(token_est=tokens, keyword_flags=("resume",)))
        assert decision.model == "claude-haiku-4-5", tokens
        assert decision.rule == "heuristic:light_transform", tokens


def test_light_transform_long_caps_at_sonnet_never_opus():
    """resume/traduction longs -> Sonnet (jamais Opus), continuité au seuil."""
    router = HeuristicRouter()
    for tokens in (801, 1000, 3000):
        for flag in ("resume", "traduction"):
            decision = router.decide(make_signals(token_est=tokens, keyword_flags=(flag,)))
            assert decision.model == "claude-sonnet-5", (tokens, flag)
            assert decision.rule == "heuristic:light_transform_long", (tokens, flag)


def test_light_transform_with_heavy_flag_goes_complex():
    """« Résume ce contrat » : le flag lourd l'emporte -> complex_task/Opus."""
    router = HeuristicRouter()
    decision = router.decide(make_signals(token_est=500, keyword_flags=("resume", "contrat")))
    assert decision.model == "claude-opus-4-8"
    assert decision.rule == "heuristic:complex_task"


def test_light_transform_massive_context_goes_complex():
    """Résumer un fil énorme n'est plus « léger » : complex_task décide."""
    router = HeuristicRouter()
    decision = router.decide(
        make_signals(token_est=1000, keyword_flags=("resume",), context_token_est=5000)
    )
    assert decision.rule == "heuristic:complex_task"


# ---------------------------------------------------------------------------
# SafeRouter : validation de la sortie du primaire (ml r0, invariant §5.2).
# ---------------------------------------------------------------------------


class _StubRouter(Router):
    """Primaire de test : renvoie une décision arbitraire SANS lever."""

    def __init__(self, decision: Decision) -> None:
        self._decision = decision

    def decide(self, signals: Signals) -> Decision:
        return self._decision


def test_safe_router_rejects_unknown_model():
    """Un primaire qui prédit un modèle hors catalogue -> repli, jamais transmis."""
    rogue = _StubRouter(Decision(model="gpt-4-leaked", confidence=0.9, rule="ml:v05"))
    decision = SafeRouter(primary=rogue).decide(make_signals(token_est=50))
    assert decision.model in VISIBLE_MODELS
    assert decision.rule == "fallback:heuristic"


def test_safe_router_rejects_fable_not_visible():
    """claude-fable-5 (visible:false, RFC-0002) n'est JAMAIS recommandé."""
    rogue = _StubRouter(Decision(model="claude-fable-5", confidence=0.9, rule="ml:v05"))
    decision = SafeRouter(primary=rogue).decide(make_signals(token_est=50))
    assert decision.model in VISIBLE_MODELS
    assert decision.rule == "fallback:heuristic"


def test_safe_router_clamps_out_of_range_confidence():
    """Confiance 1.7 (artefact mal calibré) : clampée à 1.0, décision conservée."""
    overconfident = _StubRouter(Decision(model="claude-sonnet-5", confidence=1.7, rule="ml:v05"))
    decision = SafeRouter(primary=overconfident).decide(make_signals(token_est=50))
    assert decision.model == "claude-sonnet-5"
    assert decision.confidence == 1.0
    assert decision.rule == "ml:v05"  # léger débordement : pas un repli


def test_safe_router_rejects_nan_confidence():
    nan_router = _StubRouter(
        Decision(model="claude-sonnet-5", confidence=float("nan"), rule="ml:v05")
    )
    decision = SafeRouter(primary=nan_router).decide(make_signals(token_est=50))
    assert decision.rule == "fallback:heuristic"
    assert 0.0 <= decision.confidence <= 1.0


def test_safe_router_primary_none_serves_fallback():
    """Échec au CHARGEMENT (artefact manquant) : primary=None -> repli direct."""
    safe = SafeRouter(primary=None)
    decision = safe.decide(make_signals(token_est=50))
    assert decision.rule == "fallback:heuristic"
    assert decision.model in VISIBLE_MODELS


# ---------------------------------------------------------------------------
# Adaptateur : pièce jointe = signal lourd ; prompt_text inerte (ml r0).
# ---------------------------------------------------------------------------


class _FeaturesStub:
    def __init__(self, **overrides):
        self.char_len = overrides.get("char_len", 120)
        self.token_est = overrides.get("token_est", 30)
        self.lang = overrides.get("lang", "fr")
        self.has_code = overrides.get("has_code", False)
        self.has_attachment_hint = overrides.get("has_attachment_hint", False)
        self.keyword_flags = overrides.get("keyword_flags", [])


def test_adapter_attachment_hint_maps_to_heavy_flag():
    """Prompt court AVEC pièce jointe : ne part plus sur le modèle le plus léger."""
    signals = features_to_signals(_FeaturesStub(has_attachment_hint=True))
    assert "analyse" in signals.prompt.keyword_flags
    decision = HeuristicRouter().decide(signals)
    assert decision.rule == "heuristic:complex_task"
    assert decision.model == "claude-opus-4-8"


def test_adapter_attachment_hint_no_duplicate_flag():
    signals = features_to_signals(
        _FeaturesStub(has_attachment_hint=True, keyword_flags=["analyse"])
    )
    assert signals.prompt.keyword_flags.count("analyse") == 1


def test_adapter_never_populates_prompt_text():
    """Point d'extension étage 2 : STRICTEMENT None via l'adaptateur v0."""
    signals = features_to_signals(_FeaturesStub())
    assert signals.prompt.prompt_text is None


def test_heuristic_ignores_prompt_text():
    """L'étage 1 est INSENSIBLE au texte : même décision avec ou sans."""
    base = make_signals(token_est=50)
    with_text = Signals(
        prompt=type(base.prompt)(
            char_len=base.prompt.char_len,
            token_est=base.prompt.token_est,
            lang=base.prompt.lang,
            has_code=base.prompt.has_code,
            has_math=base.prompt.has_math,
            keyword_flags=base.prompt.keyword_flags,
            prompt_text="texte transitoire en mémoire (jamais persisté)",
        ),
        conversation=base.conversation,
    )
    assert HeuristicRouter().decide(with_text) == HeuristicRouter().decide(base)
