# connector/ — connecteur de facturation Anthropic (Lot C)

Connecteur **LECTURE SEULE** vers l'API d'administration Anthropic
(Usage & Cost, Analytics). Il alimente l'entrepôt Postgres (`usage_daily`,
`sync_runs`) qui sert au rapport mensuel. État actuel : **squelette Lot 0** —
le mode `--fixtures` fonctionne de bout en bout sans réseau ; les appels réels
sont posés avec des `TODO(LotC)`.

---

> ## ⚠️ Clé d'administration Anthropic = ACTIF CRITIQUE (règle n°5)
>
> Anthropic n'offre **pas de permission fine** : la clé d'administration lit
> **tout le compte** (usage, coûts, membres, workspaces). En conséquence :
>
> - lue depuis l'environnement **uniquement** (`ANTHROPIC_ADMIN_KEY`) ;
> - **jamais commitée** (le dépôt n'en contient aucune, `.env` est gitignoré) ;
> - **jamais loggée** ni exposée : `repr(client)` la masque, les tests
>   `test_connector_secrets.py` cassent la CI en cas de fuite ;
> - confinée dans `connector/client.py` — aucun autre module ne la manipule.
>
> **Procédure de rotation** (compromission suspectée ou rotation périodique) :
> 1. révoquer la clé dans la console d'administration Anthropic ;
> 2. générer une nouvelle clé et remplacer la variable d'environnement
>    (`.env` local, secrets du déploiement) — nulle part ailleurs ;
> 3. relancer le sync (`python -m connector.sync --org <org>`) et vérifier le
>    statut du run dans `sync_runs`.

---

## Périmètre du lot

| Module | Rôle |
|---|---|
| `client.py` | `AnthropicAdminClient` (httpx, GET uniquement, pagination générique `has_more`/`next_page`) et `FixturesClient` (même interface, rejoue `fixtures/anthropic/*.json`). |
| `normalize.py` | Réponses Anthropic → lignes `usage_daily` du schéma (`contracts/db_schema.sql`, aucun champ hors schéma). Mapping modèles Anthropic → ids du catalogue. Pseudonymisation salée des emails (règle n°1). |
| `sync.py` | Fenêtre **J-30 glissante** versionnée par `snapshot_ts`, ingestion **idempotente** (`INSERT ... ON CONFLICT DO NOTHING`), trace dans `sync_runs`. CLI. |
| `tests/` | Base dédiée `sobrio_test_connector` (jamais la base partagée `sobrio`). |

## Fraîcheur des données (règle n°6 — pas de temps réel)

Les chiffres d'usage/coût Anthropic se stabilisent en **~4 à 24 h** et peuvent
être réconciliés **jusqu'à J+30**. Le connecteur re-tire donc
**systématiquement** une fenêtre J-30 glissante à chaque run, versionnée par
`snapshot_ts` :

- mode réel : `snapshot_ts` = début du run ;
- mode `--fixtures` : `snapshot_ts` **déterministe** (max des `ending_at` des
  fixtures) ⇒ deux exécutions produisent le même état final.

Le rapport mensuel est produit à J+10 du mois suivant, sur des données ainsi
consolidées.

## Limitation documentée — angle mort Bedrock / Vertex

L'API d'administration Anthropic ne couvre **que** l'usage passant par le
compte Anthropic direct. L'usage des modèles Claude via **AWS Bedrock** ou
**Google Vertex AI** n'y apparaît **pas** : c'est un angle mort de la mesure,
à mentionner explicitement dans le volet méthodologie du rapport.
TODO(LotC) : évaluer des connecteurs Bedrock/Vertex dédiés.

## Commandes

```bash
# Depuis la racine du monorepo, venv partagé .venv.

# Sync en mode fixtures (sans réseau, sans clé) sur une base au choix :
DATABASE_URL=postgresql+psycopg://sobrio:sobrio_dev_password@localhost:5432/sobrio \
PSEUDONYM_SALT=dev-salt-change-me \
.venv/bin/python -m connector.sync --org demo --fixtures

# Options : --org <org_id> --fixtures --database-url <url>

# Tests (recrée la base dédiée sobrio_test_connector) :
.venv/bin/pytest connector/tests

# Lint :
.venv/bin/ruff check connector
```

## Checklist Lot 0

- [x] `FixturesClient` : pagination `has_more`/`next_page` rejouée depuis `fixtures/anthropic/`
- [x] `AnthropicAdminClient` : clé env uniquement, `repr` masqué, en-têtes `x-api-key` + `anthropic-version`
- [x] Normalisation vers `usage_daily` (aucun champ hors schéma), mapping modèles → catalogue
- [x] Pseudonymisation salée (`PSEUDONYM_SALT` obligatoire, jamais d'email en clair)
- [x] Fenêtre J-30 glissante, `snapshot_ts` déterministe en mode fixtures
- [x] Idempotence (`ON CONFLICT DO NOTHING`, testée compte + somme de contrôle)
- [x] Run tracé dans `sync_runs` (fenêtre, lignes, statut)
- [x] Tests : pagination, pseudonymisation, idempotence, non-fuite de la clé
- [ ] TODO(LotC) : URLs/params réels, retry/backoff, mapping modèles complet,
      répartition fine des coûts, devises non-USD, fenêtre passée aux endpoints,
      dégradé propre sans plan Enterprise (Analytics), connecteurs Bedrock/Vertex

## Ce que ce connecteur ne fait JAMAIS

- écrire quoi que ce soit côté Anthropic (GET uniquement) ;
- stocker ou logger un email en clair (hash salé tronqué, sel obligatoire) ;
- stocker ou logger du contenu de prompt (l'API admin n'en expose pas — et le
  schéma `usage_daily` n'a de toute façon aucune colonne pour ça) ;
- logger ou committer la clé d'administration.
