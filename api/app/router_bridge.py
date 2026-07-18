"""Construit le routeur EFFECTIF par organisation (chantier R1).

Le contrat `/v1/recommend` est INCHANGÉ : cette fonction ne fait que choisir
QUELLE instance de `sobrio_router.Router` sert une organisation, à partir de
la clé `router_version` de `policy_json` (mécanisme interne, hors schéma
`ExtensionConfig` — pas exposé à l'extension).

v0 : toute valeur de `router_version` résout vers le même
`SafeRouter(HeuristicRouter(), HeuristicRouter())` — la vraie sélection
(v0.5 classifieur, v1 recalibré par org) arrivera aux chantiers suivants
(docs/decisions/ROUTEUR_CLASSIFIEUR.md, séquence produit).
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

# Versions reconnues en R1 : une seule. Le dict existe déjà (plutôt qu'un
# simple `if`) pour que R5/R7 ajoutent une entrée sans toucher la fonction
# de résolution ci-dessous.
_KNOWN_VERSIONS = frozenset({_DEFAULT_VERSION})


@lru_cache(maxsize=8)
def _router_for_version(version: str) -> Router:
    """Singleton de routeur par version reconnue — réutilisé entre requêtes.

    Un `SafeRouter` neuf par requête recréerait un `ThreadPoolExecutor` à
    chaque appel (coûteux, et sans intérêt : cf. `sobrio_router.safe`).
    """
    # v0 : le "primary" EST déjà l'heuristique (rien d'autre à essayer) ;
    # l'enveloppe SafeRouter reste en place pour l'invariant §5.2 dès qu'un
    # vrai routeur ML remplacera le primary (v0.5, R5).
    return SafeRouter(primary=HeuristicRouter(), fallback=HeuristicRouter())


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
