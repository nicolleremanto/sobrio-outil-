"""SafeRouter — invariant §5.2 : le routeur ne rend JAMAIS l'API indisponible.

`decide()` exécute le routeur primaire dans un thread avec timeout, puis
VALIDE sa sortie (correction ronde 0, ml-architect) : un primaire qui renvoie
sans lever un modèle hors catalogue visible (ex. artefact ML corrompu qui
prédit `claude-fable-5` ou une étiquette étrangère) ou une confiance hors
[0, 1] déclenche le repli exactement comme une exception — sinon la réponse
partirait au contrat et un `confidence > 1` ferait un 500 pydantic.

Toute exception, dépassement de `timeout_s` OU sortie invalide ⇒ repli sur le
routeur heuristique de secours, avec `rule` REMPLACÉ par
`"fallback:heuristic"` — on distingue ainsi explicitement « la règle
heuristique a normalement décidé ceci » de « le routage primaire a échoué et
on est retombé sur ceci ». (La sous-règle heuristique du repli n'est pas
conservée dans `rule` : le libellé `fallback:heuristic` est FIGÉ par
l'invariant §5.2 — observabilité fine du repli : TODO V2.)

`primary=None` couvre l'ÉCHEC AU CHARGEMENT (correction ronde 0) : un
artefact ML manquant/corrompu échoue typiquement à la CONSTRUCTION du
routeur, pas dans `decide()`. Le pont API (`router_bridge`) construit alors
`SafeRouter(primary=None, ...)` : chaque décision part directement du
fallback, marquée `fallback:heuristic`, sans thread ni exception.

`decide()` elle-même ne lève JAMAIS.
"""

from __future__ import annotations

import concurrent.futures
import math

from .heuristic import VISIBLE_MODELS, HeuristicRouter
from .interface import Router
from .types import Decision, Signals

# Dernier filet, codé en dur : si même le fallback heuristique lève (ne doit
# JAMAIS arriver — HeuristicRouter est pure et totale, cf. heuristic.py), on
# répond sans dépendre d'AUCUNE logique métier susceptible d'échouer à son tour.
_HARDCODED_FALLBACK = Decision(model="claude-sonnet-5", confidence=0.5, rule="fallback:heuristic")


class SafeRouter(Router):
    """Enveloppe un routeur primaire avec repli heuristique borné dans le temps.

    Le `ThreadPoolExecutor` est créé UNE FOIS par instance (pas par appel à
    `decide()`) : en créer un par requête serait coûteux pour rien.

    Note sur la saturation (`max_workers=2`) : si un appel primaire reste
    bloqué indéfiniment (deadlock, boucle infinie, dépendance externe qui ne
    répond jamais), il occupe un worker en permanence. Les appels suivants se
    partagent le second worker jusqu'à ce qu'il soit lui aussi occupé ; au-delà,
    chaque nouveau `decide()` attend une place dans la file du pool avant même
    de démarrer son propre chronomètre de timeout — sous rafale extrême, la
    latence peut donc dépasser `timeout_s`. Mais chaque appel finit TOUJOURS
    par renvoyer une décision (celle du fallback, dans le pire cas) : jamais
    d'exception propagée, donc jamais d'indisponibilité de l'API — seulement,
    au pire, une dégradation de latence. C'est exactement l'invariant §5.2.
    """

    def __init__(
        self,
        primary: Router | None,
        fallback: HeuristicRouter | None = None,
        timeout_s: float = 0.050,
        allowed_models: frozenset[str] | None = None,
    ) -> None:
        self._primary = primary
        self._fallback = fallback if fallback is not None else HeuristicRouter()
        self._timeout_s = timeout_s
        # Étiquettes acceptées d'un primaire : par défaut les ids VISIBLES du
        # catalogue (jamais claude-fable-5 — RFC-0002). Injectable pour tests.
        self._allowed_models = allowed_models if allowed_models is not None else VISIBLE_MODELS
        # Aucun executor si le primaire est absent (échec au chargement) :
        # decide() court-circuite directement vers le fallback.
        self._executor = (
            concurrent.futures.ThreadPoolExecutor(max_workers=2) if primary is not None else None
        )

    def _validated(self, decision: Decision) -> Decision | None:
        """Valide la sortie du primaire ; None si elle est inutilisable.

        TOUS les champs sont validés (corrections rondes 0 ET 1) :
        - modèle : DOIT appartenir aux ids visibles du catalogue ;
        - rule : DOIT être une chaîne non vide (un `rule=None` transmis tel
          quel ferait un 500 pydantic au contrat — trou trouvé par qa r1) ;
        - confiance : DOIT être un nombre RÉEL FINI — `math.isfinite` rejette
          NaN ET ±inf, et `bool` est explicitement exclu (True est un int en
          Python — trou trouvé par ml-architect r1). Un débordement FINI est
          ensuite clampé à [0, 1] (léger défaut de calibration, pas une panne).
        """
        if decision.model not in self._allowed_models:
            return None
        if not isinstance(decision.rule, str) or not decision.rule:
            return None
        confidence = decision.confidence
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not math.isfinite(float(confidence))
        ):
            return None
        clamped = min(1.0, max(0.0, float(confidence)))
        if clamped == decision.confidence:
            return decision
        return Decision(model=decision.model, confidence=clamped, rule=decision.rule)

    def decide(self, signals: Signals) -> Decision:
        if self._primary is not None and self._executor is not None:
            try:
                future = self._executor.submit(self._primary.decide, signals)
                candidate = self._validated(future.result(timeout=self._timeout_s))
                if candidate is not None:
                    return candidate
                # Sortie invalide (modèle hors catalogue, confiance NaN…) :
                # même traitement qu'une exception — repli silencieux.
            except Exception:
                # concurrent.futures.TimeoutError (délai dépassé, le thread
                # primaire continue en arrière-plan sans qu'on l'attende) OU
                # toute exception levée par le routeur primaire lui-même :
                # repli silencieux, jamais de propagation vers l'appelant.
                pass

        try:
            decision = self._fallback.decide(signals)
        except Exception:
            # Ne doit jamais arriver : HeuristicRouter est pure et totale.
            # Filet de tout dernier recours, indépendant de toute logique.
            return _HARDCODED_FALLBACK

        return Decision(
            model=decision.model, confidence=decision.confidence, rule="fallback:heuristic"
        )
