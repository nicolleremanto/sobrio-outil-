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

.PHONY: dev test lint demo report sync-fixtures migrate seed router-bench router-eval \
	router-corpus router-corpus-check router-train router-gate router-promote router-rollback \
	router-embed-model router-embed-train router-embed-eval router-embed-gate \
	router-embed-promote router-embed-rollback router-embed-bench

# Routeur évalué par `router-eval` (registre : heuristic ; extensible R5 : ml_v05).
ROUTER ?= heuristic
# Tête évaluée par `router-embed-eval` (registre R6 : prior, head_candidate, head_promoted).
TETE ?= prior

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

## router-bench : preuve budget étage 1 (p95 < 5 ms CPU) ; écrit router/artifacts/bench/latest.json
router-bench:
	$(PY) router/bench.py

## router-eval : évalue ROUTER (défaut heuristic) sur le golden set figé ; écrit router/artifacts/eval/<ROUTER>-latest.json
router-eval:
	$(PY) router/eval/harness.py --router $(ROUTER)

## router-corpus : régénère le corpus synthétique 30k (démarrage à froid,
## chantier R4) + stats + rapport data-quality, affiche le verdict. DÉCISION
## (documentée ici, cf. .gitignore) : router/data/artifacts/ n'est JAMAIS
## commité (régénérable au seed près, seed figé DEFAULT_SEED=4242) — seuls
## le générateur (generate_corpus.py) et les petits JSON (metadata/stats/
## quality/bruit) d'un run de RÉFÉRENCE sont versionnés, copiés dans
## router/data/reference/ par cette cible. NORMALISATION (minor, correction
## ronde 0) : la copie de référence de metadata.json retire la clé VOLATILE
## `date_generation` (change à chaque régénération sans rapport avec le
## contenu) — la référence ne se salit plus dans git à chaque run ; le
## sha256_gz du .gz reste la SEULE vérité de contenu, inchangé par cette
## normalisation.
router-corpus:
	$(PY) router/data/generate_corpus.py --out-dir router/data/artifacts
	$(PY) router/data/quality_report.py \
		--corpus router/data/artifacts/corpus-v1.jsonl.gz \
		--out router/data/artifacts/corpus-v1.quality.json
	mkdir -p router/data/reference
	$(PY) -c "import json; from pathlib import Path; src = Path('router/data/artifacts/corpus-v1.metadata.json'); data = json.loads(src.read_text(encoding='utf-8')); data.pop('date_generation', None); Path('router/data/reference/corpus-v1.metadata.json').write_text(json.dumps(data, indent=2, ensure_ascii=False) + chr(10), encoding='utf-8')"
	cp router/data/artifacts/corpus-v1.stats.json router/data/reference/
	cp router/data/artifacts/corpus-v1.quality.json router/data/reference/
	cp router/data/artifacts/corpus-v1.bruit.json router/data/reference/

## router-corpus-check : boucle rapide — petit corpus (500 lignes, même seed
## de référence) + quality report + tests router/data (sortie dans un
## sous-répertoire séparé pour ne jamais écraser le run de référence 30k).
router-corpus-check:
	$(PY) router/data/generate_corpus.py --n 500 --out-dir router/data/artifacts/check
	$(PY) router/data/quality_report.py \
		--corpus router/data/artifacts/check/corpus-v1.jsonl.gz \
		--out router/data/artifacts/check/corpus-v1.quality.json
	$(PYTEST) router/tests -k "data" -q

## router-train : entraîne le candidat v0.5 depuis le corpus de référence -> router/artifacts/models/candidate/
router-train:
	$(PY) router/train/train_v05.py

## router-gate : évals fraîches (heuristic + candidat) puis gate R3 (previous injecté s'il existe)
router-gate:
	$(PY) router/eval/harness.py --router heuristic
	$(PY) router/eval/harness.py --router ml_v05_candidate
	$(PY) router/eval/gate.py \
	  --candidate router/artifacts/eval/ml_v05_candidate-latest.json \
	  --baseline router/artifacts/eval/heuristic-latest.json \
	  $$( [ -f router/artifacts/models/promoted/eval-report.json ] && \
	      echo "--previous router/artifacts/models/promoted/eval-report.json" )

## router-promote : promotion 1 commande (rejoue le gate, §5.3) ; rollback : make router-rollback
router-promote:
	$(PY) router/train/promote.py

router-rollback:
	$(PY) router/train/promote.py --rollback

## router-embed-model : récupère le modèle e5 pré-exporté (R6 §4.4). Le flag
## SOBRIO_ALLOW_MODEL_DOWNLOAD=1 est posé EXPLICITEMENT sur cette seule ligne
## (jamais en CI, jamais à l'import — patron SOBRIO_ALLOW_DATASET_DOWNLOAD).
## AVANT le geste fondateur (manifest à sources null), la CLI REFUSE exit 2.
router-embed-model:
	SOBRIO_ALLOW_MODEL_DOWNLOAD=1 $(PY) router/tools/fetch_embed_model.py

## router-embed-train : entraîne la tête v0 SYNTHÉTIQUE (D4 — mécanique, pas
## qualité) -> router/artifacts/embed/heads/candidate/
router-embed-train:
	$(PY) router/train/train_head_v0.py

## router-embed-eval : évalue TETE (défaut prior) sur les fixtures embed figées ;
## écrit router/artifacts/eval/embed-<TETE>-latest.json
router-embed-eval:
	$(PY) router/eval/harness_embed.py --router $(TETE)

## router-embed-gate : évals fraîches (prior + candidat) puis gate R3 réutilisé
## pur, --suite embed --budget-ms 30 (previous injecté s'il existe)
router-embed-gate:
	$(PY) router/eval/harness_embed.py --router prior
	$(PY) router/eval/harness_embed.py --router head_candidate
	$(PY) router/eval/gate.py --suite embed --budget-ms 30 \
	  --candidate router/artifacts/eval/embed-head_candidate-latest.json \
	  --baseline router/artifacts/eval/embed-prior-latest.json \
	  $$( [ -f router/artifacts/embed/heads/promoted/eval-report.json ] && \
	      echo "--previous router/artifacts/embed/heads/promoted/eval-report.json" )

## router-embed-bench : preuve budget étage 2 (p95 ≤ 30 ms INCLUSIF, RSS < 1 Go)
## du pipeline COMPLET tokenise→encode→tête (§11) ; écrit
## router/artifacts/bench/embed-latest.json (exigé par la garde D8 de la
## promotion). AVANT le geste fondateur (deps/modèle absents, recadrage
## ledger 2026-07-23) : REFUS exit 2 propre — jamais un défaut ni un acte de CI.
router-embed-bench:
	$(PY) router/bench_embed.py

## router-embed-promote : promotion 1 commande de la tête (gate frais + garde
## bench D8 — REFUS avant geste fondateur : heads/promoted/ reste vide en prod, D4)
router-embed-promote:
	$(PY) router/train/promote_embed.py

router-embed-rollback:
	$(PY) router/train/promote_embed.py --rollback

## test : tests Python (tous les lots) puis tests de l'extension
test:
	$(PYTEST) router/tests api/tests connector/tests warehouse/tests report/tests
	$(PNPM) -C extension test

## lint : ruff (Python) puis eslint/prettier (extension)
lint:
	$(RUFF) check router api connector warehouse report
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
