# Sobrio — instructions projet (monorepo Phase 1)

## Contexte

Sobrio aide les entreprises européennes à maîtriser le coût et l'empreinte environnementale
de leur IA générative. Phase 1 :

1. **Extension navigateur** (Lot A) : recommande sur claude.ai le modèle adapté à chaque
   prompt — elle **affiche et conseille, n'automatise JAMAIS**.
2. **Connecteur de facturation** (Lot C) : **LECTURE SEULE** sur l'API d'administration
   Anthropic (Usage & Cost, Analytics).
3. **Rapport mensuel PDF** (Lot E) : deux volets — économique + environnemental/RSE,
   conforme directive UE 2024/825 anti-greenwashing.

En support : API backend (Lot B), entrepôt Postgres — métadonnées uniquement (Lot D),
module d'impact en fourchettes (`sobrio_impact`, Lot D), ops (Lot F).

## Les 7 règles non négociables (à encoder dans le code, pas seulement en doc)

1. **Jamais de contenu de prompt stocké ni loggé** (ni base, ni logs, ni Sentry).
   On manipule des *features* (longueur, langue, flags) et des hash salés.
2. **Extension en lecture seule PAR DÉFAUT** vis-à-vis de claude.ai : elle affiche, ne
   clique pas, ne pré-sélectionne rien, ne modifie pas le DOM fonctionnel. Aucun secret
   dans le bundle. *Amendements du 2026-07-16 (décisions fondateur, voir
   `docs/decisions.md`)* : l'application automatique du modèle choisi est **activée
   par défaut** (désactivable dans le popup — décochée, retour à la lecture seule
   stricte), déclenchée au clic de l'utilisateur dans le panneau Sobrio (mode
   `one_click` ; voir l'amendement RFC-0003 ci-dessous pour le mode `auto` sans
   clic), implémentée dans le SEUL module `extension/src/modelSwitcher.ts`
   (résultat vérifié, échec ⇒ abandon silencieux). Gating par politique org
   (`allow_auto_apply`) proposé dans la RFC-0001. *Amendement du 2026-07-17
   (RFC-0003)* : le mode `assist_mode: auto` bascule le modèle **sans clic** (si
   confiance ≥ seuil), avec confirmation discrète et **Annuler** (restaure le
   précédent) ; gaté par la politique org (`assist_mode`) ET l'opt-in local ;
   `one_click` = bascule au clic ; `guide` = repli SANS contact page (kill-switch
   prudence CGU) ; repli `guide` si sélecteurs cassés. Le badge et le panneau
   l'annoncent honnêtement (pas de « n'agit jamais » en auto). Voir
   `docs/rfc/RFC-0003-assist-mode.md`.
3. **Tout chiffre d'impact est un intervalle min–max avec périmètre** (type `Range`).
   Jamais d'équivalents grand public (litres, arbres, km) dans le code ou les gabarits.
4. **Rapport : deux blocs distincts, jamais fusionnés** — empreinte totale MESURÉE
   (connecteur, 100 % de l'usage) et économies OBTENUES (extension, périmètre chat navigateur).
5. **Clé d'administration Anthropic = actif critique** : lue depuis l'environnement
   uniquement, jamais commitée, jamais loggée.
6. **Pas de temps réel** : usage/cost se rafraîchit en ~4-24 h, réconciliation jusqu'à J+30 ;
   fenêtre J-30 glissante, versionnage par `snapshot_ts` ; rapport à J+10 du mois suivant.
7. **Tout changement de contrat passe par une RFC** (`docs/rfc/`) + version dans
   `contracts/CHANGELOG.md`.

## Contrats = source de vérité

Les fichiers de `contracts/` (`openapi.yaml`, `db_schema.sql`, `model_catalog.yaml`,
`CHANGELOG.md`) sont **figés en v1.0**. Toute modification de `contracts/` exige une RFC
dans `docs/rfc/` (gabarit : `docs/rfc/TEMPLATE.md`) **et** un incrément de version dans
`contracts/CHANGELOG.md`. Pas d'exception.

## Stack imposée

| Domaine | Outils |
|---------|--------|
| Extension | WXT + TypeScript + pnpm (eslint + prettier + vitest) |
| API | FastAPI + pydantic v2 |
| Entrepôt | SQLAlchemy 2 + Alembic, Postgres 16 |
| Connecteur | httpx |
| Rapport | Jinja2 + WeasyPrint |
| Qualité Python | ruff + pytest |

## Conventions de travail

- **Venv racine partagé** : `.venv` (Python 3.12). Utiliser `.venv/bin/python`,
  `.venv/bin/pytest`, `.venv/bin/ruff` depuis la racine. Chaque package Python garde son
  `requirements.txt` (compatible venv racine) et un `pyproject.toml`
  (`[tool.ruff] line-length = 100`).
- `warehouse/sobrio_impact` est installé en éditable :
  `from sobrio_impact import Range, estimate, catalog_version` fonctionne partout.
- **Tests depuis la racine** : `.venv/bin/pytest <lot>/tests`. Préfixer les fichiers de test
  par le nom du lot (`test_api_*.py`, `test_connector_*.py`, …).
- **Jamais de secret commité** : `.env` est gitignoré, `.env.example` ne contient que des
  valeurs factices. La clé `ANTHROPIC_ADMIN_KEY` reste vide dans l'exemple (règle n°5).
- Auth API : `orgs.api_token_hash = sha256(token)`. Org de dev : `demo`,
  token depuis `DEMO_ORG_TOKEN` (défaut `demo-token-not-a-secret`).
- Conversion coût : prix catalogue en USD ; constante `EUR_PER_USD = 0.92`
  (TODO : brancher une vraie source de taux).
- Mois de démo canonique : **2026-06** (seed ~60 jours, 2026-05-12 → 2026-07-10).
- Commentaires, docstrings et documentation **en français**. Logique métier hors Lot 0
  marquée `TODO(LotA)`…`TODO(LotF)`.

## Commandes make

| Commande | Effet |
|----------|-------|
| `make dev` | Postgres + Adminer + API (docker) + migrations Alembic + seed démo |
| `make test` | pytest (api, connector, warehouse, report) puis `pnpm -C extension test` |
| `make lint` | ruff (api, connector, warehouse, report) puis `pnpm -C extension lint` |
| `make sync-fixtures` | ingestion connecteur depuis les fixtures locales |
| `make report` | rapport PDF org `demo`, mois 2026-06 |
| `make migrate` / `make seed` | migrations seules / seed seul |
| `make demo` | résumé des points d'entrée de la démo |

## Carte des lots

| Lot | Dossier | Périmètre |
|-----|---------|-----------|
| A | `extension/` | Extension navigateur (recommandation affichée, jamais automatisée) |
| B | `api/` | API FastAPI : `/v1/recommend`, `/v1/telemetry/reco_event`, `/v1/extension/config` |
| C | `connector/` | Connecteur Anthropic Admin, lecture seule, fenêtre J-30, `snapshot_ts` |
| D | `warehouse/` | Entrepôt Postgres (métadonnées uniquement) + module `sobrio_impact` |
| E | `report/` | Rapport mensuel PDF deux volets (mesuré ≠ économisé) |
| F | `ops/` | Prod, sécurité, CI, sauvegardes |
