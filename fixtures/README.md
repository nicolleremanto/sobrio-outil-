# fixtures/ — réponses Anthropic pour le développement hors ligne

> **AVERTISSEMENT — DONNÉES 100 % SYNTHÉTIQUES.**
> Tout le contenu de `fixtures/anthropic/` est **inventé** pour le développement :
> organisations, workspaces, clés API, volumes, coûts et utilisateurs
> (`*@exemple-client.eu`) sont fictifs et anonymes. Aucune donnée réelle,
> aucune donnée personnelle. Ne rien en déduire sur un client ou sur les
> prix/consommations réels.

Ces fichiers permettent au connecteur (Lot C) de tourner **sans réseau et sans
clé** : `python -m connector.sync --org demo --fixtures`.

## Structure des fichiers

Tous les fichiers suivent l'enveloppe de pagination de l'API d'administration
Anthropic : `{"data": [...], "has_more": bool, "next_page": str|null}`.
La page suivante d'un préfixe `X` est `X_p<N+1>.json` ; elle n'est lue que si
la page courante annonce `has_more=true` avec un `next_page` non nul.

| Fichier | Simule | Contenu |
|---|---|---|
| `anthropic/usage_report_messages_p1.json` / `_p2.json` | `GET /v1/organizations/usage_report/messages` | Buckets journaliers `{starting_at, ending_at, results[]}` du 2026-05-12 au 2026-07-08 (~60 jours), 3 modèles (`claude-haiku-4-5`, `claude-sonnet-4-6`, `claude-opus-4-8`), 2 workspaces (`wrkspc_alpha`, `wrkspc_beta`), 4 clés (`apikey_01`..`04`). Tokens : `uncached_input_tokens`, `cached_input_tokens` (lecture cache), `cache_creation_input_tokens`, `output_tokens`. Pagination simulée : p1 se termine par `has_more=true`. |
| `anthropic/cost_report_p1.json` | `GET /v1/organizations/cost_report` | Buckets journaliers de montants par workspace × modèle `{currency: "USD", amount: "123.4567"}`, cohérents en ordre de grandeur avec l'usage et les prix de `contracts/model_catalog.yaml`. Une seule page. |
| `anthropic/analytics_by_user_p1.json` | API Analytics (plan Enterprise) | Lignes journalières par utilisateur `{date, user_email, product (claude_ai/claude_code), model, input_tokens, output_tokens, requests}`, ~15 utilisateurs synthétiques. Une seule page. |

Volumes : quelques millions de tokens/mois — l'ordre de grandeur d'une PME.
Le mois de démonstration canonique du monorepo est **2026-06**.

## Enregistrer de vraies réponses plus tard

`fixtures/record_fixtures.py` est le point d'entrée prévu (stub Lot 0,
implémentation `TODO(LotC)`) :

```bash
ANTHROPIC_ADMIN_KEY=... .venv/bin/python fixtures/record_fixtures.py
```

Le script **refuse de tourner sans `ANTHROPIC_ADMIN_KEY`** et, une fois
implémenté, devra **anonymiser les emails AVANT toute écriture** sur disque
(règle n°1 : aucune donnée personnelle dans le dépôt).

## Rappel — règle n°5 (clé d'administration)

La clé d'administration Anthropic est un **actif critique** : pas de permission
fine chez Anthropic, elle lit **tout** le compte. Elle est lue depuis
l'environnement **uniquement**, jamais commitée, jamais loggée, jamais écrite
dans une fixture. Procédure de rotation : voir `connector/README.md`.
