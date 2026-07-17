# Journal de convergence — Finition orchestrée multi-agents (V2)

> Chef d'orchestre : construit → prouve (lint/test/build/captures) → juge (agents
> INDÉPENDANTS à contexte neuf) → consigne → décide. Convergence d'un chantier =
> **2 rondes vertes consécutives**. Plafond 8 rondes. Un FAIL `privacy-sentinel`
> interdit de passer, non waivable.

Agents : `design-critic`, `qa-auditor`, `privacy-sentinel` (PASS/FAIL),
`robustness-redteam`, `product-conformance`, `perf-auditor`
(définitions dans `.claude/agents/`).

Vérification en ligne (2026-07-17) : gamme et tarifs Anthropic confirmés via
`platform.claude.com/docs/.../models/overview` et la référence claude-api —
Fable 5 (10/50), Opus 4.8 (5/25), Sonnet 5 (3/15 · intro 2/10), Haiku 4.5 (1/5).

---

## État des chantiers

| Chantier | Sujet                             | Rondes vertes consécutives | Statut       |
| -------- | --------------------------------- | -------------------------- | ------------ |
| C        | Catalogue de modèles à jour       | 2/2 (rondes 1 & 2)         | **CONVERGÉ** |
| A        | Refonte graphique du panneau      | 0/2                        | en cours     |
| B        | Bascule instantanée + assist_mode | 0/2                        | à venir      |

---

## Chantier C — round 0 (commit b440607)

| agent               | scores                                                                  | blocking | major | verdict  |
| ------------------- | ----------------------------------------------------------------------- | -------- | ----- | -------- |
| qa-auditor          | couv 3 · contrat 2 · erreurs 3 · clarté 4 · régressions 1               | 2        | 1     | **RED**  |
| privacy-sentinel    | —                                                                       | PASS     | —     | **PASS** |
| product-conformance | ton 5 · fourchettes 5 · mémoire 5 · démontre 5 · nouv-conv 5 · budget 4 | 0        | 0     | GREEN    |

→ Ronde **RED**. Défauts retenus (à corriger avant ronde 1) :

- **[blocking]** Régression inter-lots : le catalogue partagé a changé d'ids mais
  les consommateurs Python (api/router, warehouse/seed+aggregate,
  connector/normalize) n'ont pas suivi → `make test` rouge (11 failed + 11
  errors). J'avais lancé la seule suite extension.
- **[blocking]** Assertions Python obsolètes (catalog_version, ids attendus).
- **[major]** Changement de contrat sans RFC (règle n°7) → créer une RFC.
- **[minor]** Prix intro Sonnet 5 (2/10, en vigueur jusqu'au 2026-08-31) ignoré
  par le mock (surestime le coût ~50 %). · **[minor]** `claude-fable-5` exposé
  dans `models_visible`. · **[minor]** libellé nominal obsolète dans le test
  signals. · **[minor]** test « démontre-le » n'isole pas la mémoire (le prompt
  déclenche déjà le flag `demonstration`).

Décision chef d'orchestre : je corrige TOUT (blocking + major + minors) — le
catalogue étant un contrat partagé, la porte de non-régression §6 couvre bien
la suite complète `make test`, pas seulement l'extension.

## Chantier C — round 1 (commit 7839e77)

| agent               | scores                                                                  | blocking | major | verdict   |
| ------------------- | ----------------------------------------------------------------------- | -------- | ----- | --------- |
| qa-auditor          | couv 4 · contrat 5 · erreurs 5 · clarté 5 · régressions 5               | 0        | 0     | **GREEN** |
| privacy-sentinel    | —                                                                       | PASS     | —     | **PASS**  |
| product-conformance | ton 5 · fourchettes 5 · mémoire 5 · démontre 5 · nouv-conv 5 · budget 5 | 0        | 0     | **GREEN** |

→ Ronde **VERTE (1/2)**. `make test` complet re-vérifié vert par les juges.
Minors (non bloquants) retenus pour polissage avant la ronde 2 :

- Filtre Fable du mock non couvert par un test → ajouter une assertion.
- Sémantique `visible` du mock en dur (`!== 'claude-fable-5'`) → aligner sur un
  champ `visible` comme le catalogue/API.
- (produit) EN_MESSAGES partiel → `TODO(V2)`, hors périmètre Chantier C.

## Chantier C — round 2 (commit 90d1175)

| agent               | scores                                                                  | blocking | major | verdict   |
| ------------------- | ----------------------------------------------------------------------- | -------- | ----- | --------- |
| qa-auditor          | couv 5 · contrat 5 · erreurs 5 · clarté 5 · régressions 5               | 0        | 0     | **GREEN** |
| privacy-sentinel    | —                                                                       | PASS     | —     | **PASS**  |
| product-conformance | ton 5 · fourchettes 5 · mémoire 5 · démontre 5 · nouv-conv 5 · budget 5 | 0        | 0     | **GREEN** |

→ Ronde **VERTE (2/2 consécutive)** — **CHANTIER C CONVERGÉ.**
Minors optionnels non bloquants (documentés, non traités en C) :

- garde-fou anti-dérive `MOCK_CATALOG` ↔ `contracts/model_catalog.yaml` (le mock
  duplique volontairement le catalogue — choix documenté) ;
- `warehouse/seed.py` `models_visible` en dur (données de démo) ;
- `ambiguous_note` nomme « Sonnet » en dur → **reporté au Chantier A** (refonte
  du panneau, qui touche `messages.ts`/`panel.ts`).
