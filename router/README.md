# `router/` — Routeur de recommandation Sobrio (classifieur, PAS de LLM)

Le moteur qui répond « quel modèle Claude suffit pour cette tâche ? » à partir
de **signaux sans contenu** (règle n°1 : aucun texte de prompt stocké ni
loggé). Architecture actée : `docs/decisions/ROUTEUR_CLASSIFIEUR.md` —
classifieur à deux étages (LightGBM ≤ 5 ms, puis embeddings ONNX opt-in
< 30 ms), séquence **v0 heuristique → v0.5 classifieur pré-entraîné → v1
recalibré mensuellement par organisation**.

## Le package `sobrio_router` (stdlib seule — lightgbm PARESSEUX)

| Module | Rôle |
| --- | --- |
| `types.py` | Dataclasses gelées : `PromptSignals`, `ConversationSignals`, `Signals`, `Decision` (schéma RFC-0001). `prompt_text` porte le texte de l'étage 2 (livré R6) : `None` par défaut, `repr=False`, verrou `__reduce__` (sérialisation interdite porteur de texte, règle n°1). |
| `interface.py` | `Router.decide(signals) -> Decision` — l'interface STABLE derrière laquelle tout se branche. |
| `heuristic.py` | `HeuristicRouter` v0 : règles nommées, ordonnées, commentées (le nom = champ `rule`). `VISIBLE_MODELS` = seules étiquettes autorisées (jamais `claude-fable-5`, RFC-0002). |
| `safe.py` | `SafeRouter` — invariant §5.2 : timeout 50 ms + validation de la sortie du primaire + mode `primary=None` (échec au chargement) ⇒ repli `rule="fallback:heuristic"`. Ne lève JAMAIS. |
| `adapter.py` | `features_to_signals` — pont TRANSITOIRE contrat v1.x (`features`) → `Signals` ; saute à l'adoption de la RFC-0001. |
| `features.py` | R5 : `signals_to_vector` — 22 features FIGÉES (mesures + vocabulaire fermé, JAMAIS de texte, §5.1). Pur stdlib. |
| `ml.py` | R5 : `MLRouter` v0.5 — LightGBM (import PARESSEUX : le paquet s'importe SANS lightgbm) + calibration isotonique CONSERVATRICE (`min(brut, iso(brut))` : jamais de confiance au-dessus de la brute). Échec de chargement ⇒ `MLRouterLoadError` À LA CONSTRUCTION ; `rule="ml:v05"` constant. |
| `embed.py` | R6 : étage 2 — `EmbedHead` (tête calibrée stdlib pure, chaîne de confiance UNIQUE §5.2bis, plafond `confidence_cap` = 0,74 lu du metadata, fail-closed) + `EmbedRouter` (e5 ONNX, imports paresseux, `rule="embed:v0"`). Échec ⇒ `EmbedLoadError` à la construction ; sha normatifs `None` tant que le geste fondateur n'a pas eu lieu : TOUT encodeur local est refusé (fail-closed). |
| `twostage.py` | R6 : `TwoStageRouter` — l'étage 2 ne s'exécute que si conf étage 1 < 0,75, override seulement si conf2 > conf1, toute exception étage 2 ⇒ décision étage 1 (repli fin, silencieux). |

Côté API : `api/app/router_bridge.py` résout le routeur effectif d'une org via
`policy_json.router_version` (défaut + repli silencieux `heuristic`), avec
garde de construction (artefact manquant ⇒ repli, jamais de 500).
**Canary per-org (R5)** : une org bascule sur le classifieur via
`policy_json.router_version="ml_v05"` — le défaut RESTE `heuristic`
(activation org par org, décision fondateurs). Artefact promu/réparé ⇒
redémarrage API (lru_cache — rechargement à chaud : TODO R7).
**Étage 2 livré (R6)** : `router_version="embed_v0"` compose
`TwoStageRouter` en cascade FAIL-SOFT (étage 2 absent/KO ⇒ ml:v05 ; étage 1
KO ⇒ `fallback:heuristic` ; API 200 dans tous les cas). Le texte n'atteint
l'étage 2 que TRIPLE VERROU ouvert — env `SOBRIO_EMBED_STAGE2="1"` strict +
policy `send_prompt_text is True` + texte présent dans la requête — sinon il
est DÉTRUIT dès la route ; confiance plafonnée à 0,74 (`confidence_cap` du
metadata : jamais d'auto-bascule RFC-0003). Le PREMIER fetch du modèle est un
GESTE FONDATEUR (ledger, 2026-07-23) : tant qu'il n'a pas eu lieu, le manifest
reste à sources null, `heads/promoted/` reste vide et l'étage 1 seul répond.

## Runbook v0.5 (R5) : train → gate → promote → rollback

```bash
.venv/bin/pip install -r router/requirements-ml.txt  # lightgbm+numpy (entraînement)
make router-corpus     # si router/data/artifacts/ manque (corpus régénérable, seed figé)
make router-train      # candidat -> router/artifacts/models/candidate/ (déterministe bit-exact)
make router-gate       # évals fraîches (heuristic + candidat) + gate R3 — VERDICT PASS/FAIL
make router-promote    # rejoue le gate (§5.3) puis candidate/ -> promoted/ (ancien -> previous/)
make router-rollback   # previous/ -> promoted/ (1 commande, 1 niveau d'historique)
```

La promotion REFUSE sans gate PASS frais (aucun contournement) et refuse un
rapport candidat contaminé par le moindre repli `fallback:heuristic`
(`repartition_rules`). Les artefacts (`router/artifacts/models/`) ne sont
JAMAIS commités : l'identité versionnée vit dans `metadata.json` (sha corpus
épinglé, golden_sha, seed, versions, best_iteration).

## Commandes

```bash
.venv/bin/pip install -e router      # installation editable (une fois)
.venv/bin/pytest router/tests -q     # tests du lot
make router-bench                    # bench p95 (budget ≤ 5 ms) → artifacts/bench/latest.json
make router-eval ROUTER=ml_v05       # éval du promu sur le golden figé (aussi : heuristic, ml_v05_candidate)
```

## Journal

La convergence du chantier (rondes, verdicts des juges indépendants) est
consignée dans `CONVERGENCE_LEDGER.md`.
