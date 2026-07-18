"""SafeRouter — invariant §5.2 : le routeur ne rend JAMAIS l'API indisponible.

`decide()` exécute le routeur primaire dans un thread avec timeout. Toute
exception OU dépassement de `timeout_s` déclenche un repli sur le routeur
heuristique de secours, avec `rule` REMPLACÉ par `"fallback:heuristic"` —
on distingue ainsi explicitement « la règle heuristique a normalement décidé
ceci » de « le routage primaire a échoué et on est retombé sur ceci ».
`decide()` elle-même ne lève JAMAIS.
"""

from __future__ import annotations

import concurrent.futures

from .heuristic import HeuristicRouter
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
        primary: Router,
        fallback: HeuristicRouter | None = None,
        timeout_s: float = 0.050,
    ) -> None:
        self._primary = primary
        self._fallback = fallback if fallback is not None else HeuristicRouter()
        self._timeout_s = timeout_s
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)

    def decide(self, signals: Signals) -> Decision:
        try:
            future = self._executor.submit(self._primary.decide, signals)
            return future.result(timeout=self._timeout_s)
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
