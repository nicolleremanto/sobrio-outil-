"""Construit le routeur EFFECTIF par organisation (chantier R1).

Le contrat `/v1/recommend` est INCHANGÉ : cette fonction ne fait que choisir
QUELLE instance de `sobrio_router.Router` sert une organisation, à partir de
la clé `router_version` de `policy_json` (mécanisme interne, hors schéma
`ExtensionConfig` — pas exposé à l'extension).

R5 : `router_version="ml_v05"` résout vers `SafeRouter(MLRouter(promoted))`.
CANARY PER-ORG : le défaut RESTE `heuristic` — une org bascule sur ml_v05
via `policy_json.router_version="ml_v05"` (activation org par org, décision
fondateurs, hors code). Artefact manquant/corrompu/lightgbm absent : la
garde de construction sert `SafeRouter(primary=None)` — API verte,
`rule="fallback:heuristic"` (invariant §5.2). Limite lru_cache : artefact
promu/réparé => redémarrage API (TODO R7 : rechargement à chaud).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from sobrio_router import HeuristicRouter, Router, SafeRouter

# Version par défaut ET repli silencieux pour toute valeur absente, inconnue
# ou mal typée de `router_version` — même posture défensive que
# `get_extension_config` (routes.py) vis-à-vis de `policy_json` (règle 3) :
# une politique mal saisie ne doit jamais faire échouer /v1/recommend.
_DEFAULT_VERSION = "heuristic"

# Versions reconnues (R5) : le classifieur ml_v05 s'ajoute à l'heuristique.
_KNOWN_VERSIONS = frozenset({_DEFAULT_VERSION, "ml_v05"})


def _build_primary(version: str) -> Router:
    """Construit le routeur primaire d'une version — PEUT lever (artefact).

    `ml_v05` : import DIFFÉRÉ de `sobrio_router.ml` (lightgbm y est lui-même
    paresseux, §7.1) et chargement de l'artefact PROMU — qui peut échouer si
    l'artefact est manquant/corrompu : c'est précisément pourquoi l'appelant
    enveloppe cette construction d'un try/except (invariant §5.2, correction
    ronde 0 : un échec au CHARGEMENT contournerait sinon le SafeRouter).
    `ml.PROMOTED_DIR` est lu À L'APPEL (attribut de module, pas une valeur
    figée) : testable par monkeypatch, surcharge env TODO R7.
    """
    if version == "ml_v05":
        from sobrio_router import ml  # import différé (§7.1)

        return ml.MLRouter(ml.PROMOTED_DIR)
    return HeuristicRouter()


@lru_cache(maxsize=8)
def _router_for_version(version: str) -> Router:
    """Singleton de routeur par version reconnue — réutilisé entre requêtes.

    Un `SafeRouter` neuf par requête recréerait un `ThreadPoolExecutor` à
    chaque appel (coûteux, et sans intérêt : cf. `sobrio_router.safe`).

    GARDE DE CONSTRUCTION (invariant §5.2) : si la construction du primaire
    lève (artefact ML manquant/corrompu au chargement — R5), on sert un
    `SafeRouter(primary=None)` : chaque décision part du repli heuristique,
    marquée `fallback:heuristic`, sans jamais faire un 500. Le repli est
    MÉMORISÉ par le lru_cache : un artefact réparé exige un redémarrage du
    service (assumé v0 — TODO R7 : rechargement à chaud avec invalidation).
    """
    try:
        primary: Router | None = _build_primary(version)
    except Exception:
        primary = None  # échec au chargement ⇒ repli permanent, API verte
    return SafeRouter(primary=primary, fallback=HeuristicRouter())


def router_for_org(policy_json: dict[str, Any] | None) -> Router:
    """Résout le routeur effectif d'une org depuis `policy_json.router_version`.

    Défensif : `policy_json` peut ne pas être un dict (mal saisi côté DB),
    et `router_version` peut être absent, inconnu ou mal typé — dans tous
    ces cas, repli silencieux sur "heuristic" (jamais de 500).
    """
    policy = policy_json if isinstance(policy_json, dict) else {}
    version = policy.get("router_version")
    if not isinstance(version, str) or version not in _KNOWN_VERSIONS:
        version = _DEFAULT_VERSION
    return _router_for_version(version)
