# warehouse/ — Lot D : entrepôt Postgres + module d'impact

Entrepôt de **métadonnées uniquement** (règle n°1 : jamais de contenu de
prompt, ni en base, ni en logs) et module d'impact en fourchettes.

## Périmètre du Lot D

| Élément | Rôle |
| --- | --- |
| `sobrio_impact/` | Module d'impact : `Range`, `estimate()`, `catalog_version()` (installé en editable) |
| `alembic.ini` + `alembic/` | Migrations — la 0001 applique `contracts/db_schema.sql` VERBATIM |
| `seed.py` | Données de démo déterministes et idempotentes (org `demo`, 60 jours d'usage, ~300 événements) |
| `aggregate.py` | Stub d'agrégation mensuelle `usage_daily` → `monthly_agg` |
| `tests/` | Tests structurels (règle n°3) + intégration sur base dédiée `sobrio_test_warehouse` |

Hors périmètre (stubs marqués `TODO(LotX)`) : réconciliation J+30 complète
(`TODO(LotD)`), tarification réelle du cache (`TODO(LotC)`), vraie source de
taux de change (`TODO(LotB)`), recalibrage des facteurs d'énergie
(`TODO(LotD)`).

## Commandes (toujours DEPUIS LA RACINE du repo)

```bash
# 1. Migration (DATABASE_URL lu depuis l'env, défaut : base locale sobrio)
.venv/bin/alembic -c warehouse/alembic.ini upgrade head

# 2. Seed de démonstration (déterministe, relançable sans effet)
.venv/bin/python warehouse/seed.py --org demo

# 3. Agrégation du mois de démo canonique
.venv/bin/python warehouse/aggregate.py --org demo --month 2026-06

# Tests et lint
.venv/bin/pytest warehouse/tests
.venv/bin/ruff check warehouse
```

Les tests créent et détruisent leur propre base `sobrio_test_warehouse` ;
ils ne touchent jamais à la base partagée `sobrio`.

## Règle n°3 — rappel non négociable

Tout chiffre d'impact est un **intervalle min–max avec périmètre** (`Range`)
— jamais un scalaire. `estimate()` retourne structurellement un `Range`
(annotation vérifiée par test, `Range` non convertible en nombre, min > max
refusé).

**Interdits absolus dans le code et les gabarits** : les équivalents grand
public (litres d'eau, arbres, km en voiture…). Directive UE 2024/825 —
aucune conversion « parlante » n'est tolérée, seules les fourchettes Wh avec
périmètre et source le sont.

## Checklist Lot D

- [x] Migration Alembic 0001 = `contracts/db_schema.sql` verbatim (source de vérité, règle n°7)
- [x] `downgrade` supprime les 5 tables dans l'ordre des dépendances
- [x] Seed déterministe (`random.Random(42)`, UUID dérivés du générateur)
- [x] Seed idempotent (`ON CONFLICT DO NOTHING`)
- [x] `snapshot_ts` fixe 2026-07-11T03:00:00Z (règle n°6 : pas de temps réel)
- [x] `user_pseudonym` = hash salé (règle n°1)
- [x] `features_json` = schéma `Features` du contrat, sans texte (règle n°1)
- [x] Fourchettes d'impact via `sobrio_impact.estimate` (règle n°3)
- [x] Coût : prix du catalogue ; EUR via constante `EUR_PER_USD = 0.92` (TODO(LotB))
- [x] Agrégat : dimension `total` = sentinelle `*` (dim_value ∈ PK)
- [x] Agrégat idempotent : DELETE (org, mois) puis INSERT
- [x] `catalog_version()` tracée dans chaque ligne de `monthly_agg`
- [x] Tests structurels règle n°3 + migration + seed + agrégat
