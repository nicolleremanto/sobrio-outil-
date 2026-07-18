# `router/` — Routeur de recommandation Sobrio (classifieur, PAS de LLM)

Le moteur qui répond « quel modèle Claude suffit pour cette tâche ? » à partir
de **signaux sans contenu** (règle n°1 : aucun texte de prompt stocké ni
loggé). Architecture actée : `docs/decisions/ROUTEUR_CLASSIFIEUR.md` —
classifieur à deux étages (LightGBM < 5 ms, puis embeddings ONNX opt-in
< 30 ms), séquence **v0 heuristique → v0.5 classifieur pré-entraîné → v1
recalibré mensuellement par organisation**.

## Le package `sobrio_router` (R1 — stdlib seule)

| Module | Rôle |
| --- | --- |
| `types.py` | Dataclasses gelées : `PromptSignals`, `ConversationSignals`, `Signals`, `Decision` (schéma RFC-0001). `prompt_text` est un point d'extension RÉSERVÉ (étage 2, R6) — `None` partout en v0. |
| `interface.py` | `Router.decide(signals) -> Decision` — l'interface STABLE derrière laquelle tout se branche. |
| `heuristic.py` | `HeuristicRouter` v0 : règles nommées, ordonnées, commentées (le nom = champ `rule`). `VISIBLE_MODELS` = seules étiquettes autorisées (jamais `claude-fable-5`, RFC-0002). |
| `safe.py` | `SafeRouter` — invariant §5.2 : timeout 50 ms + validation de la sortie du primaire + mode `primary=None` (échec au chargement) ⇒ repli `rule="fallback:heuristic"`. Ne lève JAMAIS. |
| `adapter.py` | `features_to_signals` — pont TRANSITOIRE contrat v1.x (`features`) → `Signals` ; saute à l'adoption de la RFC-0001. |

Côté API : `api/app/router_bridge.py` résout le routeur effectif d'une org via
`policy_json.router_version` (défaut + repli silencieux `heuristic`), avec
garde de construction (artefact manquant ⇒ repli, jamais de 500).

## Commandes

```bash
.venv/bin/pip install -e router      # installation editable (une fois)
.venv/bin/pytest router/tests -q     # tests du lot
make router-bench                    # bench p95 (budget < 5 ms) → artifacts/bench/latest.json
```

## Journal

La convergence du chantier (rondes, verdicts des juges indépendants) est
consignée dans `CONVERGENCE_LEDGER.md`.
