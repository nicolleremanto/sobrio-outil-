"""Routeur heuristique v0 : règles LISIBLES, ORDONNÉES, chacune NOMMÉE.

Le nom de chaque règle EST le champ `rule` de la décision qu'elle produit —
la recommandation reste explicable de bout en bout (contrat
`/v1/recommend`). Étiquettes de sortie = ids VISIBLES du catalogue
(`contracts/model_catalog.yaml`) : `claude-fable-5` (`visible: false`,
RFC-0002) n'est JAMAIS recommandé ici, c'est une décision de sobriété, pas
un simple filtre d'affichage a posteriori.

Les règles forment une liste ORDONNÉE : la PREMIÈRE qui matche l'emporte
(priorité = ordre de déclaration, testé explicitement dans
`tests/test_router_heuristic.py`). Notamment : le code prime sur le
raisonnement, qui lui-même prime sur les prompts courts — un « démontre-le »
de trois mots dans un fil de maths ne doit pas retomber sur le modèle le
plus léger simplement parce qu'il est court.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .interface import Router
from .types import Decision, Signals

# Flags "lourds" (contrat/analyse) : tâches exigeantes qui ne doivent JAMAIS
# atterrir sur le modèle le plus léger, même si le prompt est court. "code"
# n'y figure pas : il a sa propre règle, prioritaire (cf. règle 1).
_HEAVY_FLAGS = frozenset({"contrat", "analyse"})

# Vocabulaire des transformations légères : les guides fournisseurs
# recommandent les petits modèles pour ces tâches à faible risque.
_LIGHT_TRANSFORM_FLAGS = frozenset({"resume", "traduction"})


@dataclass(frozen=True)
class _Rule:
    """Une règle nommée : prédicat sur les signaux -> (modèle, confiance) si elle matche.

    `name` alimente directement le champ `rule` de la `Decision` — c'est
    pourquoi chaque règle porte un nom stable et descriptif (`heuristic:...`).
    """

    name: str
    predicate: Callable[[Signals], bool]
    decide: Callable[[Signals], tuple[str, float]]


def _code_context(s: Signals) -> bool:
    """Code détecté sur ce prompt OU déjà vu dans la conversation.

    Guide fournisseur : les tâches de code bénéficient d'un modèle
    intermédiaire même sur un prompt court (contexte technique implicite).
    """
    return s.prompt.has_code or s.conversation.seen_code or "code" in s.prompt.keyword_flags


def _reasoning_confidence(s: Signals) -> float:
    # Un prompt court ("démontre-le") DANS un fil de raisonnement reste
    # incertain isolément : le contexte de conversation compense sans
    # atteindre la confiance d'un prompt long et explicite lui-même.
    return 0.60 if s.prompt.token_est < 50 else 0.75


def _reasoning_context(s: Signals) -> bool:
    """Maths/démonstration sur ce prompt OU déjà vues dans la conversation.

    C'est la règle qui rattrape un prompt court posé au fil d'une
    conversation de raisonnement (le scénario produit, RFC-0001).
    """
    return (
        s.prompt.has_math
        or s.conversation.seen_math
        or s.conversation.seen_reasoning
        or "demonstration" in s.prompt.keyword_flags
    )


def _light_transform(s: Signals) -> bool:
    """Résumé/traduction courts, contexte de conversation encore petit.

    Transformations légères : les guides fournisseurs les confient aux
    petits modèles — à condition que le prompt ET le contexte restent
    modestes (un résumé de contexte massif n'est plus « léger »).
    """
    flags = set(s.prompt.keyword_flags)
    return (
        bool(flags & _LIGHT_TRANSFORM_FLAGS)
        and s.prompt.token_est < 800
        and s.conversation.context_token_est < 4000
    )


def _short_simple(s: Signals) -> bool:
    """Prompt court, conversation courte, aucun flag lourd : le cas le plus fréquent.

    Atteinte SEULEMENT si aucune des règles prioritaires (code, raisonnement,
    transformation légère) n'a matché — donc ici `has_code` est déjà faux et
    `code` absent des flags, pas besoin de le revérifier.
    """
    flags = set(s.prompt.keyword_flags)
    return (
        s.prompt.token_est < 300
        and not (flags & _HEAVY_FLAGS)
        and s.conversation.msg_count <= 6
        and s.conversation.context_token_est < 2000
    )


def _complex_task(s: Signals) -> bool:
    """Flag lourd (contrat/analyse) OU prompt long OU contexte de conversation long."""
    flags = set(s.prompt.keyword_flags)
    return (
        bool(flags & _HEAVY_FLAGS)
        or s.prompt.token_est > 800
        or s.conversation.context_token_est > 4000
    )


def _always(_: Signals) -> bool:
    return True


_RULES: tuple[_Rule, ...] = (
    _Rule("heuristic:code_context", _code_context, lambda _s: ("claude-sonnet-5", 0.70)),
    _Rule(
        "heuristic:reasoning_context",
        _reasoning_context,
        lambda s: ("claude-sonnet-5", _reasoning_confidence(s)),
    ),
    _Rule("heuristic:light_transform", _light_transform, lambda _s: ("claude-haiku-4-5", 0.70)),
    _Rule("heuristic:short_simple", _short_simple, lambda _s: ("claude-haiku-4-5", 0.80)),
    _Rule("heuristic:complex_task", _complex_task, lambda _s: ("claude-opus-4-8", 0.65)),
    _Rule("heuristic:default_balanced", _always, lambda _s: ("claude-sonnet-5", 0.55)),
)


class HeuristicRouter(Router):
    """v0 : parcourt `_RULES` dans l'ordre, retient la PREMIÈRE qui matche.

    `heuristic:default_balanced` matche toujours (`_always`) : la liste est
    donc totale, `decide()` retourne systématiquement une décision — c'est
    aussi le routeur de repli de `SafeRouter` (il doit être pur et total).
    """

    def decide(self, signals: Signals) -> Decision:
        for rule in _RULES:
            if rule.predicate(signals):
                model, confidence = rule.decide(signals)
                return Decision(model=model, confidence=confidence, rule=rule.name)
        # Inatteignable : heuristic:default_balanced matche toujours (_always).
        raise AssertionError("aucune règle heuristique n'a matché — _RULES est mal formée")
