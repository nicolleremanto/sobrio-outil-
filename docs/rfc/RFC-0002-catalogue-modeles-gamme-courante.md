# RFC-0002 — Catalogue de modèles : gamme Anthropic courante

- **Auteur·e :** chef d'orchestre (finition orchestrée, Chantier C)
- **Date :** 2026-07-17
- **Statut :** acceptée (mise en œuvre)

## Motif

`contracts/model_catalog.yaml` référençait une gamme obsolète (`haiku-4-5`,
`sonnet-4-6`, `opus-4-8`). La gamme Anthropic courante, **vérifiée en ligne le
2026-07-17** (platform.claude.com/docs/.../models/overview + référence
claude-api), est : Claude Haiku 4.5, Claude Sonnet 5, Claude Opus 4.8, Claude
Fable 5. Le catalogue est la **source de vérité inter-lots** ; le laisser périmé
fausse les recommandations, les libellés UI et le chiffrage du rapport RSE.

La règle n°7 (`CLAUDE.md`) impose une RFC pour tout changement de contrat.
Cette RFC acte formellement la mise à jour (le bump de version et le CHANGELOG
seuls ne suffisaient pas — défaut relevé par le juge `qa-auditor` en ronde 0).

## Impact

- **Contrat modifié** : `contracts/model_catalog.yaml` (version `2026-07` →
  `2026-07.2`).
- **Lot A (extension)** : ids d'API partout (`signals`, `mockClient`,
  `messages`, `mockRules`), libellés UI = sélecteur claude.ai,
  `normalizeModelLabel` par famille, tests alignés.
- **Lot B (API)** : `router.py` (Decision), `routes.py` (`models_visible`),
  `catalog.py` (`visible_model_ids`), tests.
- **Lot C (connecteur)** : `MODEL_NAME_MAP` — le nom brut du Sonnet précédent
  est rattaché au Sonnet courant (les fixtures synthétiques emploient encore
  `claude-sonnet-4-6`).
- **Lot D (entrepôt)** : `seed.py`, tests (dont `catalog_version`).
- **Lot E (rapport)** : fixtures de conftest (`catalog_version`).
- **Compatibilité** : `make test` (Python + extension) doit rester vert.

## Contrats touchés

`contracts/model_catalog.yaml` : ids = identifiants d'API (`claude-...`) ;
`visible: false` sur `claude-fable-5` (chiffrage oui, dérogation non) ; impacts
des nouveaux modèles (Sonnet 5, Fable 5) marqués `extrapolated: true` +
TODO(recalibration Lot D). Prix publics, aucun inventé.

## Version proposée

`contracts/CHANGELOG.md` : catalogue **2026-07.2** (entrée ajoutée).

## Alternatives

- Garder des ids courts internes + champ `api_id` : rejeté — moins fidèle à
  l'API réelle, et le prompt du chantier demande explicitement les ids
  `claude-...`.
- Exposer Fable 5 à la dérogation : rejeté — modèle le plus cher/impactant,
  contraire à l'argument de sobriété ; gardé pour le chiffrage seul.
- Afficher le prix d'introduction du Sonnet 5 (2/10) : rejeté — un outil de
  maîtrise de coût doit refléter le coût **durable** (3/15), pas un tarif
  promotionnel temporaire qui sous-estimerait le coût après le 2026-08-31.

## Décision

Acceptée et mise en œuvre (Chantier C). Le catalogue reste figé hors RFC pour
les évolutions ultérieures.
