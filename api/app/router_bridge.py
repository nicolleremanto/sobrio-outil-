"""Construit le routeur EFFECTIF par organisation (chantiers R1, R5, R6).

Le contrat `/v1/recommend` est INCHANGÉ : cette fonction ne fait que choisir
QUELLE instance de `sobrio_router.Router` sert une organisation, à partir de
la clé `router_version` de `policy_json` (mécanisme interne, hors schéma
`ExtensionConfig` — pas exposé à l'extension).

R5 : `router_version="ml_v05"` résout vers `SafeRouter(MLRouter(promoted))`.
R6 : `router_version="embed_v0"` résout vers
`SafeRouter(TwoStageRouter(MLRouter(promoted), EmbedRouter | None))` — étage 2
opt-in DERRIÈRE le verrou d'environnement `SOBRIO_EMBED_STAGE2` (§3.1) et
fail-soft intégral (§2.2) : chaîne de repli du plus fin au plus grossier,
étage 2 KO → étage 1 (rule étage 1) → étage 1 KO → heuristique
(`fallback:heuristic`) → heuristique KO → repli codé en dur du SafeRouter.

CANARY PER-ORG (patron R5) : le défaut RESTE `heuristic` — `ml_v05` et
`embed_v0` s'activent org par org via `policy_json.router_version`
(décision fondateurs, hors code). Artefact manquant/corrompu/deps absentes :
la garde de construction sert `SafeRouter(primary=None)` — API verte,
`rule="fallback:heuristic"` (invariant §5.2). Limite lru_cache inchangée :
changement d'env/artefact => redémarrage API (TODO R7 : rechargement à chaud).
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from sobrio_router import HeuristicRouter, Router, SafeRouter, TwoStageRouter

# Version par défaut ET repli silencieux pour toute valeur absente, inconnue
# ou mal typée de `router_version` — même posture défensive que
# `get_extension_config` (routes.py) vis-à-vis de `policy_json` (règle 3) :
# une politique mal saisie ne doit jamais faire échouer /v1/recommend.
_DEFAULT_VERSION = "heuristic"

# Versions reconnues (R6) : l'étage 2 embed_v0 s'ajoute à ml_v05 (spec §2.2).
_KNOWN_VERSIONS = frozenset({_DEFAULT_VERSION, "ml_v05", "embed_v0"})

# Verrou 1 du triple verrou (§3.1, patron SOBRIO_ALLOW_DATASET_DOWNLOAD) :
# doit valoir EXACTEMENT "1". Absent/autre valeur → l'étage 2 n'est JAMAIS
# construit, quelle que soit la politique. Jamais posé en CI.
_EMBED_STAGE2_ENV = "SOBRIO_EMBED_STAGE2"


def _stage2_env_on() -> bool:
    """Verrou 1 — environnement serveur (§3.1) : ouvert ssi la valeur est "1"."""
    return os.environ.get(_EMBED_STAGE2_ENV) == "1"


def _stage2_unlocked(policy_json: object) -> bool:
    """Verrous 1 ET 2 (§3.3) : l'extraction du texte n'est permise que si
    l'environnement (`SOBRIO_EMBED_STAGE2="1"`) ET la politique de l'org
    (`router_version == "embed_v0"` ET `send_prompt_text == True`) l'ouvrent.

    Pure et DÉFENSIVE (règle 3 du bridge) : policy non-dict, clé absente ou
    mal typée (`send_prompt_text="yes"`, `1`, …) → verrou FERMÉ, jamais de
    500. `is True` est volontairement STRICT (True est un int en Python :
    `1 == True` passerait un opt-in jamais consenti).
    """
    if not _stage2_env_on():
        return False
    policy = policy_json if isinstance(policy_json, dict) else {}
    return policy.get("router_version") == "embed_v0" and policy.get("send_prompt_text") is True


def _build_primary(version: str) -> Router:
    """Construit le routeur primaire d'une version — PEUT lever (artefact).

    `ml_v05` : import DIFFÉRÉ de `sobrio_router.ml` (lightgbm y est lui-même
    paresseux, §7.1) et chargement de l'artefact PROMU — qui peut échouer si
    l'artefact est manquant/corrompu : c'est précisément pourquoi l'appelant
    enveloppe cette construction d'un try/except (invariant §5.2, correction
    ronde 0 : un échec au CHARGEMENT contournerait sinon le SafeRouter).
    `ml.PROMOTED_DIR` est lu À L'APPEL (attribut de module, pas une valeur
    figée) : testable par monkeypatch, surcharge env TODO R7.

    `embed_v0` (R6, cascade fail-soft §2.2) :
    1. verrou d'env FERMÉ → construit comme `ml_v05` (l'étage 2 n'est JAMAIS
       instancié : OFF par env prime sur la politique) ;
    2. `EmbedRouter()` sous try/except Exception → `stage2=None` en cas
       d'échec — modèle absent (cas NOMINAL tant que le geste fondateur n'a
       pas eu lieu), artefact de tête absent, dérive, dépendances manquantes ;
    3. `MLRouter(PROMOTED_DIR)` : un échec PROPAGE — le lru_cache de
       l'appelant sert alors `SafeRouter(primary=None)` = repli heuristique
       intégral (patron R1 inchangé) ;
    4. `TwoStageRouter(stage1, stage2)` — arbitrage §5, replis fins compris.
    """
    if version == "embed_v0":
        if not _stage2_env_on():
            return _build_primary("ml_v05")  # étage 2 jamais instancié (§2.2.1)
        from sobrio_router import embed  # import différé (§7.1)

        try:
            stage2: Router | None = embed.EmbedRouter()
        except Exception:
            stage2 = None  # échec de l'étage 2 : l'étage 1 seul répond (§2.2.2)
        from sobrio_router import ml  # import différé (§7.1)

        stage1 = ml.MLRouter(ml.PROMOTED_DIR)  # un échec ICI propage (§2.2.3)
        return TwoStageRouter(stage1, stage2)
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
    lève (artefact ML manquant/corrompu au chargement — R5/R6), on sert un
    `SafeRouter(primary=None)` : chaque décision part du repli heuristique,
    marquée `fallback:heuristic`, sans jamais faire un 500. Le repli est
    MÉMORISÉ par le lru_cache : un artefact réparé (ou un changement d'env
    `SOBRIO_EMBED_STAGE2`) exige un redémarrage du service (assumé v0 —
    TODO R7 : rechargement à chaud avec invalidation).

    `timeout_s=0.050` du SafeRouter INCHANGÉ (5 + 30 ms p95 < 50 ms) : un
    étage 2 qui PEND déclenche le timeout → heuristique — jamais
    d'indisponibilité (§2.2).
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
