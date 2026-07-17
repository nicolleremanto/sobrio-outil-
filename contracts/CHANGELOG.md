# Contrats — journal des versions

Les fichiers de `contracts/` sont la **source de vérité** des interfaces entre lots.
Toute modification exige une **RFC** (`docs/rfc/`) et une incrémentation de version ici.

## catalogue 2026-07.2 (2026-07-17) — gamme de modèles à jour

- `model_catalog.yaml` : gamme alignée sur la documentation officielle Anthropic
  (vérifiée en ligne le 2026-07-17) — **Claude Haiku 4.5** (`claude-haiku-4-5`,
  1/5 $/Mtok), **Claude Sonnet 5** (`claude-sonnet-5`, 3/15 ; intro 2/10 jusqu'au
  2026-08-31), **Claude Opus 4.8** (`claude-opus-4-8`, 5/25), **Claude Fable 5**
  (`claude-fable-5`, 10/50). Ids = identifiants d'API Anthropic.
- Retrait de la gamme obsolète (`sonnet-4-6`, ids courts). Impacts des nouveaux
  modèles (Sonnet 5, Fable 5) marqués `extrapolated: true` + TODO(recalibration
  Lot D). Version du catalogue `2026-07` → `2026-07.2`.

## v1.0 (2026-07-16) — contrats initiaux, figés pour la Phase 1

- `openapi.yaml` : 3 endpoints (`POST /v1/recommend`, `POST /v1/telemetry/reco_event`,
  `GET /v1/extension/config`), auth Bearer, télémétrie STRICTE (champ inconnu ⇒ 422).
- `db_schema.sql` : `orgs`, `usage_daily`, `events_reco`, `sync_runs`, `monthly_agg`.
- `model_catalog.yaml` : catalogue v2026-07 (haiku-4-5, sonnet-4-6, opus-4-8),
  impacts en fourchettes min–max uniquement.
