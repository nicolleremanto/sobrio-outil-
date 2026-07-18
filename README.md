# Sobrio — outil Phase 1

Sobrio aide les entreprises européennes à maîtriser le coût et l'empreinte environnementale
de leur IA générative. La Phase 1 réunit une extension navigateur qui **recommande** (sans
jamais automatiser) le modèle adapté à chaque prompt sur claude.ai, un connecteur de
facturation **en lecture seule** sur l'API d'administration Anthropic, et un rapport mensuel
PDF à deux volets (économique + environnemental/RSE, conforme à la directive UE 2024/825
anti-greenwashing). Tout chiffre d'impact est une fourchette min–max avec périmètre, et aucun
contenu de prompt n'est jamais stocké ni loggé.

## Démarrage en 5 commandes

```bash
git clone <url-du-repo> sobrio-outil && cd sobrio-outil
cp .env.example .env
make dev            # Postgres + Adminer + API (docker) + migrations + seed
make sync-fixtures  # ingestion connecteur depuis les fixtures locales
make report         # rapport PDF du mois de démo (2026-06)
```

Puis `make demo` pour le résumé des points d'entrée (API sur http://localhost:8000,
docs interactives sur `/docs`, Adminer sur http://localhost:8080).

## Les lots

| Lot | Périmètre | Propriétaire | Commandes |
|-----|-----------|--------------|-----------|
| A | Extension navigateur (WXT + TS) — affiche la recommandation, ne modifie jamais le DOM fonctionnel | _(à remplir)_ | `cd extension && pnpm dev` · `pnpm -C extension test` · `pnpm -C extension lint` |
| B | API backend (FastAPI) — `/v1/recommend`, `/v1/telemetry/reco_event`, `/v1/extension/config` + **routeur** `router/` (classifieur, pas de LLM — `docs/decisions/ROUTEUR_CLASSIFIEUR.md`) | _(à remplir)_ | `make dev` · `.venv/bin/pytest api/tests router/tests` · `make router-bench` |
| C | Connecteur facturation Anthropic (lecture seule, Usage & Cost, Analytics) | _(à remplir)_ | `make sync-fixtures` · `.venv/bin/pytest connector/tests` |
| D | Entrepôt Postgres (métadonnées uniquement) + module d'impact `sobrio_impact` (fourchettes) | _(à remplir)_ | `make migrate` · `make seed` · `.venv/bin/pytest warehouse/tests` |
| E | Rapport mensuel PDF deux volets (Jinja2 + WeasyPrint) | _(à remplir)_ | `make report` · `.venv/bin/pytest report/tests` |
| F | Ops : déploiement, sécurité, CI, sauvegardes | _(à remplir)_ | voir `ops/README.md` · `.github/workflows/ci.yml` |

## Arborescence

```
sobrio-outil/
├── contracts/        # SOURCE DE VÉRITÉ : openapi.yaml, db_schema.sql,
│                     # model_catalog.yaml, CHANGELOG.md — modification = RFC obligatoire
├── extension/        # Lot A — extension navigateur (WXT + TypeScript + pnpm)
├── api/              # Lot B — API FastAPI (pydantic v2)
├── router/           # Lot B — routeur de recommandation (sobrio_router : classifieur, pas de LLM)
├── connector/        # Lot C — connecteur Anthropic Admin (httpx, lecture seule)
├── warehouse/        # Lot D — entrepôt (SQLAlchemy + Alembic) + module sobrio_impact
├── report/           # Lot E — rapport mensuel PDF (Jinja2 + WeasyPrint)
├── fixtures/         # données factices partagées (démo 2026-06)
├── ops/              # Lot F — squelette prod, notes de sécurité
├── docs/             # décisions, RFC (docs/rfc/)
├── docker-compose.dev.yml
├── Makefile
└── .venv/            # venv partagé Python 3.12 (gitignoré)
```

## Documentation

- Découpage détaillé de la Phase 1 : `docs/DECOUPAGE_DEV_PHASE1.md`
  _(non fourni au bootstrap — à ajouter)_.
- Journal des décisions : [`docs/decisions.md`](docs/decisions.md).
- Toute évolution des contrats (`contracts/`) exige une RFC
  ([gabarit](docs/rfc/TEMPLATE.md)) et une entrée dans
  [`contracts/CHANGELOG.md`](contracts/CHANGELOG.md).
