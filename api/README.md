# Sobrio API — Lot B (squelette)

API FastAPI de la Phase 1 : recommandation de modèle, télémétrie,
configuration de l'extension. **L'API stub est le mock officiel du Lot A** :
réponses stub mais strictement conformes à `contracts/openapi.yaml`, avec une
recommandation qui varie selon les features pour que la démo soit vivante.

## Périmètre du Lot B (ce dossier uniquement)

- `app/main.py` — application FastAPI « Sobrio API » v1.0, monte les 3 routes.
- `app/schemas.py` — modèles pydantic v2 fidèles au contrat, `extra="forbid"`
  partout (tout champ inconnu ⇒ 422 — garde-fou anti-fuite, règle n°1).
- `app/auth.py` — Bearer : `sha256(token)` comparé à `orgs.api_token_hash`, 401 sinon.
- `app/router.py` — alternatives + estimation d'impact à partir de l'id de
  modèle recommandé (le routage lui-même vit dans le package `sobrio_router`,
  racine du repo — chantier R1, `docs/decisions/ROUTEUR_CLASSIFIEUR.md`).
- `app/router_bridge.py` — construit le routeur effectif par org
  (`policy_json.router_version`), singletons réutilisés entre requêtes.
- `app/routes.py` — les 3 routes du contrat (voir ci-dessous).
- `app/logging_conf.py` — logs JSON structurés SANS contenu + filtre de scrubbing.
- `app/db.py` — engine SQLAlchemy depuis `DATABASE_URL`, session par requête.
- `app/catalog.py` — lecture de `contracts/model_catalog.yaml` (prix, ids),
  `EUR_PER_USD = 0.92` (TODO(LotB) : vraie source de taux).

## Les 3 routes (contrat : `contracts/openapi.yaml`, figé v1.0 — règle n°7)

| Route | Comportement Lot 0 |
|---|---|
| `POST /v1/recommend` | Décision heuristique + INSERT réel dans `events_reco` (features uniquement, jamais `prompt_text`) |
| `POST /v1/telemetry/reco_event` | Schéma STRICT (champ inconnu ⇒ 422), UPDATE `followed`/`final_model`, 404 si inconnu, 204 en succès |
| `GET /v1/extension/config?org=` | Défauts sûrs fusionnés avec `orgs.policy_json` ; `send_prompt_text=false` PAR CONTRAT |

## Règles non négociables encodées ici

1. **Jamais de contenu de prompt stocké ni loggé** : `prompt_text` est traité
   en mémoire uniquement (ignoré en v0) ; `features_json` ne contient que les
   features du contrat ; schéma télémétrie strict ; filtre de scrubbing dans
   les logs ; test anti-fuite avec sentinelle (`tests/test_api_no_leak.py`).
2. **Fourchettes uniquement (règle n°3)** : énergie via `sobrio_impact.estimate`
   (Range min–max), coût en bande ±20 % (stub). Aucun scalaire d'impact.
3. **Aucun secret en dur** : token de démo lu depuis `DEMO_ORG_TOKEN`,
   `DATABASE_URL` depuis l'environnement.

## Commandes (depuis la racine du repo)

```bash
# Lint
.venv/bin/ruff check api

# Tests (crée/écrase la base dédiée sobrio_test_api sur le Postgres local)
.venv/bin/pytest api/tests

# Lancement local (Postgres requis, org demo présente en base)
cd api && ../.venv/bin/uvicorn app.main:app --reload --port 8000

# Via docker compose (depuis la racine)
docker compose -f docker-compose.dev.yml up api
```

## Checklist Lot 0

- [x] 3 routes conformes au contrat OpenAPI v1.0
- [x] Auth Bearer par hash sha256 en base
- [x] INSERT/UPDATE réels dans `events_reco`
- [x] Reco qui varie selon les features (mock vivant pour le Lot A)
- [x] Impact en fourchettes via `sobrio_impact` (jamais de scalaire)
- [x] Logs JSON sans contenu + filtre de scrubbing
- [x] Test anti-fuite (sentinelle : ni logs, ni stdout, ni base)
- [x] Routeur v0 heuristique branché via `sobrio_router` (repli câblé, chantier R1)
- [ ] TODO(LotB) : budgets d'équipe (`budget` reste `null`)
- [ ] TODO(LotB) : vraie source de taux EUR/USD
- [ ] TODO(LotB) : exploitation en mémoire de `prompt_text` quand l'org l'autorise
