# Contrats — journal des versions

Les fichiers de `contracts/` sont la **source de vérité** des interfaces entre lots.
Toute modification exige une **RFC** (`docs/rfc/`) et une incrémentation de version ici.

## v1.0 (2026-07-16) — contrats initiaux, figés pour la Phase 1

- `openapi.yaml` : 3 endpoints (`POST /v1/recommend`, `POST /v1/telemetry/reco_event`,
  `GET /v1/extension/config`), auth Bearer, télémétrie STRICTE (champ inconnu ⇒ 422).
- `db_schema.sql` : `orgs`, `usage_daily`, `events_reco`, `sync_runs`, `monthly_agg`.
- `model_catalog.yaml` : catalogue v2026-07 (haiku-4-5, sonnet-4-6, opus-4-8),
  impacts en fourchettes min–max uniquement.
