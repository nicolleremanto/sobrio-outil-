# Sobrio — Makefile racine (Lot 0).
# Toutes les commandes se lancent depuis la racine du monorepo.
# Venv partagé : .venv (Python 3.12). Extension : pnpm (Node 22).

# Charge .env (s'il existe) et exporte ses variables vers toutes les commandes
# (PSEUDONYM_SALT, DATABASE_URL, DEMO_ORG_TOKEN, ...).
-include .env
export

# pnpm : sur le PATH si disponible, sinon installation locale utilisateur.
PNPM ?= $(shell command -v pnpm 2>/dev/null || echo "$(HOME)/.local/bin/pnpm")

PY      := .venv/bin/python
PYTEST  := .venv/bin/pytest
RUFF    := .venv/bin/ruff
ALEMBIC := .venv/bin/alembic

.PHONY: dev test lint demo report sync-fixtures migrate seed

## dev : environnement complet (Postgres + Adminer + API --reload) + migrations + seed
dev:
	test -f .env || cp .env.example .env
	docker compose -f docker-compose.dev.yml up -d --build
	$(ALEMBIC) -c warehouse/alembic.ini upgrade head
	$(PY) warehouse/seed.py --org demo

## migrate : applique les migrations Alembic (entrepôt)
migrate:
	$(ALEMBIC) -c warehouse/alembic.ini upgrade head

## seed : données de démonstration (org "demo", ~60 jours autour de 2026-06)
seed:
	$(PY) warehouse/seed.py --org demo

## test : tests Python (tous les lots) puis tests de l'extension
test:
	$(PYTEST) api/tests connector/tests warehouse/tests report/tests
	$(PNPM) -C extension test

## lint : ruff (Python) puis eslint/prettier (extension)
lint:
	$(RUFF) check api connector warehouse report
	$(PNPM) -C extension lint

## report : génère le rapport mensuel PDF du mois de démo (2026-06)
report:
	$(PY) report/generate.py --org demo --month 2026-06

## sync-fixtures : ingestion connecteur depuis les fixtures locales (aucun appel réseau)
sync-fixtures:
	$(PY) -m connector.sync --org demo --fixtures

## demo : résumé des points d'entrée de la démonstration
demo:
	@echo "=== Sobrio — démo Lot 0 ==="
	@echo "API           : http://localhost:8000 (docs interactives sur /docs)"
	@echo "Adminer (DB)  : http://localhost:8080"
	@echo "Extension     : cd extension && pnpm dev"
	@echo "Connecteur    : make sync-fixtures"
	@echo "Rapport PDF   : make report"
