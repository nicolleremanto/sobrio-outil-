# Lot E — Rapport mensuel PDF (squelette Lot 0)

Livrable central de la Phase 1 : un rapport mensuel PDF **à deux volets**
(économique + environnemental/RSE), généré par `generate.py` à partir des
requêtes SQL versionnées de `queries/` et du gabarit `templates/report.html.j2`
(Jinja2 → WeasyPrint, A4).

## Commande canonique

```sh
make report
# équivaut à :
.venv/bin/python report/generate.py --org demo --month 2026-06
```

Options : `--database-url` (défaut : env `DATABASE_URL`, puis base de dev
locale) et `--out` (défaut : `report/out/rapport_<org>_<month>.pdf`).

## Règles non négociables rappelées ici

- **Règle n°3** — tout chiffre d'impact est une **fourchette min–max avec
  périmètre**. Jamais d'équivalents grand public, ni dans le gabarit ni dans
  le code (test dédié : `tests/test_report_antigreenwashing.py`). Conformité
  directive UE 2024/825 (anti-écoblanchiment).
- **Règle n°4** — deux blocs environnementaux **distincts**, aux libellés
  exacts, jamais fusionnés ni comparés :
  - « Empreinte totale mesurée (100 % de l'usage) » — source connecteur ;
  - « Empreinte évitée — périmètre : chat navigateur uniquement » — source
    extension (estimation contrefactuelle).

## Calendrier (règle n°6)

Pas de temps réel : l'usage/coût se rafraîchit en ~4–24 h et se réconcilie
jusqu'à **J+30** (fenêtre J-30 glissante, versionnage par `snapshot_ts`).
Le rapport du mois M se génère à **J+10 du mois M+1** — c'est tracé en pied
de page et en annexe de chaque PDF.

## Architecture

```
report/
├── generate.py            # CLI : requêtes -> contexte -> HTML -> PDF (AUCUN SQL inline)
├── queries/               # LA source des chiffres : 1 fichier .sql par chiffre,
│   ├── monthly_total.sql  #   en-tête obligatoire (mesure, périmètre, limites),
│   ├── by_model.sql       #   paramètres nommés SQLAlchemy (:org_id, :month, :month_next)
│   ├── by_workspace.sql
│   ├── reco_adoption.sql
│   ├── reco_savings.sql       # TODO(LotE) : baseline exacte du contrefactuel
│   └── footprint_avoided.sql  # TODO(LotE) : idem, même périmètre
├── templates/report.html.j2   # Gabarit A4 (page de garde, I–IV, pied de page tracé)
├── out/                        # PDF générés (non versionnés)
└── tests/                      # test_report_*.py — voir checklist
```

## Checklist Lot 0

- [x] Chaque chiffre provient d'une requête versionnée dans `queries/`
      (garde-fou testé : pas de mot-clé SQL dans `generate.py`).
- [x] Gabarit à deux volets, blocs environnementaux distincts (libellés exacts testés).
- [x] Fourchettes min–max partout ; test anti-écoblanchiment (termes interdits).
- [x] Traçabilité : `catalog_version` (agrégation + courant), version du code
      (`CODE_VERSION`), date de génération, rappel J+10/J+30.
- [x] Échec propre si `monthly_agg` est vide pour le mois demandé.
- [x] Tests d'intégration sur base dédiée `sobrio_test_report` (jamais la base
      partagée `sobrio`).
- [ ] TODO(LotE) : baseline exacte des économies / de l'empreinte évitée.
- [ ] TODO(LotE) : `git describe` pour la version du code ; source de taux
      de change datée (constante `EUR_PER_USD = 0.92` en attendant).
- [ ] TODO(LotE) : identité visuelle définitive du gabarit.

## Tests

```sh
.venv/bin/pytest report/tests     # depuis la racine ; recrée sobrio_test_report
.venv/bin/ruff check report
```
