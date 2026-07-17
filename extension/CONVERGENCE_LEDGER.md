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
| A        | Refonte graphique du panneau      | 2/2 (rondes 3 & 4)         | **CONVERGÉ** |
| B        | Bascule instantanée + assist_mode | 0/2 (ronde 0 RED course)   | en cours     |

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

## Chantier A — round 0 (commit d3d9a53)

| agent               | scores                                                                      | blocking | major | verdict    |
| ------------------- | --------------------------------------------------------------------------- | -------- | ----- | ---------- |
| design-critic       | layout 5 · couleur 5 · typo 4 · grille 4 · couverture 2 · parité 4 · a11y 5 | 0        | 1     | **YELLOW** |
| product-conformance | ton 5 · fourchettes 5 · mémoire 5 · démontre 5 · nouv-conv 5 · budget 4     | 0        | 0     | **GREEN**  |
| qa-auditor          | couv 4 · contrat 5 · erreurs 5 · clarté 4 · régressions 5                   | 0        | 0     | **GREEN**  |
| privacy-sentinel    | —                                                                           | PASS     | —     | **PASS**   |

→ Ronde **YELLOW**. À corriger avant ronde 1 :

- **[MAJOR design]** Capture TRONQUÉE : 4 états sur 6 visibles (`--headless --screenshot`
  clippe au viewport). Les états `ambigu` et `basculee` jamais vus. → capturer la
  PLEINE page (fenêtre plus haute), régénérer, re-soumettre.
- **[minor design]** `.why` sans margin-top (rupture grille 8). · ombre sombre `.32`
  vs charte `.08` → documenter l'écart. · `mode-note`/`hint` en 11 px → 12 px.
- **[minor produit]** jauge budget sans `role=progressbar`/aria-valuenow. · %
  confiance/budget non bornés dans le libellé.
- **[minor qa]** markup du harnais dupliqué (seule la CSS est source unique) →
  documenter/aligner. · `harness.html` committé + prettier → gitignorer (généré). ·
  branche luminance de `detectHostTheme` non testée.

## Chantier A — round 1 (commit 5aa1b45, capture pleine page régénérée)

| agent               | scores                                                                      | blocking | major | verdict   |
| ------------------- | --------------------------------------------------------------------------- | -------- | ----- | --------- |
| design-critic       | layout 4 · couleur 5 · typo 4 · grille 4 · couverture 4 · parité 5 · a11y 5 | 0        | 0     | **GREEN** |
| product-conformance | ton 5 · fourchettes 5 · mémoire 5 · démontre 5 · nouv-conv 5 · budget 5     | 0        | 0     | **GREEN** |
| qa-auditor          | couv 4 · contrat 5 · erreurs 5 · clarté 5 · régressions 5                   | 0        | 0     | **GREEN** |
| privacy-sentinel    | —                                                                           | PASS     | —     | **PASS**  |

→ Ronde **VERTE (1/2)**. Le MAJOR de la ronde 0 (capture tronquée) est levé :
les 6 états sont désormais jugés sur pleine page, clair ET sombre. Minors
(non bloquants) — quatre corrigés avant la ronde 2, le reste documenté :

- **corrigé** `prefers-reduced-motion` absent (qa, WCAG 2.3.3) → media query
  neutralisant apparition + transition badge, + test.
- **corrigé** ombrage de variable `note` dans `panel.ts` (product) → renommée
  `ambiguousNote`.
- **corrigé** eyebrow « SOBRIO » 11 px hors échelle typo (design) → documenté
  comme OVERLINE assumé (le titre 13 px de la carte est le nom du modèle).
- **corrigé** badge 22 px absent de la capture (design) → ajouté clair+sombre
  au harnais, + garde de test sur l'extraction PANEL_CSS.
- **documenté (TODO V2)** ordre libellé→barre de la jauge de confiance ;
  jauges confiance/budget au rendu identique (sémantique) — la charte interdit
  toute couleur supplémentaire, différenciation par le libellé, RFC si besoin ;
  script de capture hors suite de tests (smoke-run CI) ; EN_MESSAGES partiel.

## Chantier A — round 2 (commit 700addd)

| agent               | scores                                                                        | blocking | major | verdict  |
| ------------------- | ----------------------------------------------------------------------------- | -------- | ----- | -------- |
| design-critic       | layout 5 · couleur 5 · typo 5 · grille 4,5 · couverture 5 · parité 5 · a11y 5 | 0        | 0     | GREEN    |
| product-conformance | ton 5 · fourchettes 5 · mémoire 5 · démontre 5 · nouv-conv 5 · budget 5       | 0        | 0     | GREEN    |
| qa-auditor          | couv 4 · contrat 4 · erreurs 5 · clarté 5 · régressions 2                     | 1        | 0     | **RED**  |
| privacy-sentinel    | —                                                                             | PASS     | —     | **PASS** |

→ Ronde **RED** — le streak retombe (ronde 1 verte, ronde 2 rouge). Le juge qa a
attrapé un blocking RÉEL que mon étape « prouver » avait manqué : j'ai lancé
`pnpm lint` AVANT d'éditer `CONVERGENCE_LEDGER.md`, puis j'ai commité le journal
(tableau à accents + `·`) sans re-linter → `prettier --check .` échoue →
`pnpm lint` RED. Design et produit GREEN, privacy PASS. Défauts retenus :

- **[blocking qa]** `pnpm lint` RED : `CONVERGENCE_LEDGER.md` non conforme
  prettier (largeurs de colonnes faussées par les caractères accentués/`·`). →
  `prettier --write`, re-vérifier `pnpm lint` vert, discipliner l'ordre
  prouver→commit (linter APRÈS toute édition, journal compris).
- **[minor design]** `.model small` (« recommandé ») rendu à ~10,8 px hors échelle
  typo → **corrigé** `font-size: 12px`. · marge jauge 4 px (demi-pas) →
  **documentée** comme appariement assumé. · ombre sombre 0,32 / jauge budget même
  vert → écarts déjà assumés, aucune action.
- **[minor produit]** valeurs du harnais non alignées sur la logique de décimales
  de `formatRange` (« 0,05–0,21 » vs réel « 0,050–0,210 ») → **corrigé** : STATES
  en nombres bruts + `formatRange` mirroir, `formatRange` exporté + testé.
- **[minor qa]** assertion reduced-motion couplée au formatage exact → **corrigée**
  en regex tolérante. · miroir markup non gardé → **ajout** d'une garde (classes
  clés présentes dans `panel.ts`).

## Chantier A — round 3 (commit 02cbc7e)

| agent               | scores                                                                      | blocking | major | verdict   |
| ------------------- | --------------------------------------------------------------------------- | -------- | ----- | --------- |
| design-critic       | layout 5 · couleur 5 · typo 5 · grille 5 · couverture 5 · parité 5 · a11y 5 | 0        | 0     | **GREEN** |
| product-conformance | ton 5 · fourchettes 5 · mémoire 5 · démontre 5 · nouv-conv 5 · budget 5     | 0        | 0     | **GREEN** |
| qa-auditor          | couv 5 · contrat 4 · erreurs 5 · clarté 5 · régressions 5                   | 0        | 0     | **GREEN** |
| privacy-sentinel    | —                                                                           | PASS     | —     | **PASS**  |

→ Ronde **VERTE (1/2)** — nouveau streak. Le blocking lint de la ronde 2 est
levé (`pnpm lint` vert, confirmé par qa). design : **5 partout, zéro minor**.
Deux minors substantiels (relevés par product ET qa) corrigés avant la ronde 4,
le reste documenté :

- **corrigé** sincérité budget (product) : `pct_used` était borné à 100 pour la
  barre ET le libellé → un dépassement (> 100 %) afficherait « 100 % utilisé ».
  Désormais la barre borne à 100 % mais le libellé montre la valeur réelle
  (« 118 % »), + attribut `data-sobrio-budget-over`, + test.
- **corrigé** parité `formatRange` (product + qa) : la copie du harnais n'était
  liée par aucun test → extraction dans `scripts/lib/format.mjs` (module pur
  importé par le harnais ET un test de parité stricte vs `panel.ts`).
- **corrigé** garde de dérive markup rendue **symétrique** (panel.ts ↔ harnais).
- **corrigé** `.close` 16 px commenté comme glyphe d'icône (écart typo assumé).

## Chantier A — round 4 (commit 0b27634)

| agent               | scores                                                                      | blocking | major | verdict   |
| ------------------- | --------------------------------------------------------------------------- | -------- | ----- | --------- |
| design-critic       | layout 5 · couleur 5 · typo 5 · grille 5 · couverture 4 · parité 5 · a11y 5 | 0        | 0     | **GREEN** |
| product-conformance | ton 5 · fourchettes 5 · mémoire 5 · démontre 5 · nouv-conv 5 · budget 5     | 0        | 0     | **GREEN** |
| qa-auditor          | couv 5 · contrat 5 · erreurs 5 · clarté 5 · régressions 5                   | 0        | 0     | **GREEN** |
| privacy-sentinel    | —                                                                           | PASS     | —     | **PASS**  |

→ Ronde **VERTE (2/2 consécutive)** — **CHANTIER A CONVERGÉ** (rondes 3 & 4).
Toutes dimensions ≥ 4, zéro blocking/major, privacy PASS aux deux rondes.

Bilan de la boucle A : ronde 0 YELLOW (capture tronquée) → 1 verte → 2 RED
(blocking lint attrapé par qa) → 3 verte → 4 verte. Le dispositif a attrapé en
chemin : capture tronquée, blocking lint, faille de sincérité budget, dérive de
parité `formatRange`.

Minors non bloquants de la ronde 4 traités en **finition post-convergence**
(commit ronde 5) — chaque changement re-jugé (ronde 5 de clôture) pour ne rien
livrer de non-jugé, puis résidus triviaux → TODO(V2) :

- **corrigé** état « budget dépassé » (>100 %) absent de la capture (design docke
  couverture à 4 ; product) → nouvel état `budget-depasse` (118 %) + budget du
  harnais paramétré → sincérité budget prouvée à l'œil, clair ET sombre.
- **corrigé** a11y budget en dépassement (qa) : `aria-valuetext` porte la valeur
  réelle (le lecteur d'écran entend « 118 % », plus seulement 100) + test.
- **corrigé** garde anti-régression `ambiguous_note` (product) : test verrouillant
  l'absence de tout nom de modèle en dur.
- **corrigé** écart `--track` sombre non documenté (design) → commenté (parité
  avec l'ombre). · garde de dérive markup élargie à 17 classes (qa).
- **documenté** libellé a11y du harnais (qa) : le harnais reflète FR_MESSAGES
  (« Fermer le panneau ») ; seule PANEL_CSS est mono-source par ailleurs.

## Chantier A — round 5 (commit 61072e4) — validation de la finition post-convergence

| agent               | scores                                                                      | blocking | major | verdict   |
| ------------------- | --------------------------------------------------------------------------- | -------- | ----- | --------- |
| design-critic       | layout 5 · couleur 5 · typo 5 · grille 5 · couverture 5 · parité 5 · a11y 5 | 0        | 0     | **GREEN** |
| product-conformance | ton 5 · fourchettes 5 · mémoire 5 · démontre 5 · nouv-conv 5 · budget 5     | 0        | 0     | **GREEN** |
| qa-auditor          | couv 5 · contrat 5 · erreurs 5 · clarté 4 · régressions 5                   | 0        | 0     | **GREEN** |
| privacy-sentinel    | —                                                                           | PASS     | —     | **PASS**  |

→ Ronde **VERTE** — 3ᵉ verte consécutive (rondes 3-4-5). La finition
post-convergence est validée : `couverture_etats` remonte à 5 (état budget
dépassé désormais visible), a11y budget confirmée. **CHANTIER A définitivement
clos.** Deux minors triviaux :

- **corrigé** commentaire périmé « 6 états » → « 7 états » (product + qa, la
  seule cause du clarté 4 de qa) dans `capture-visual.mjs`.
- **TODO(V2)** (design, optionnel) : `data-sobrio-budget-over` est émis mais
  aucune règle CSS ne le consomme — le dépassement se lit dans le chiffre, pas
  visuellement. Le juge confirme que c'est **conforme** (décision assumée « jauge
  budget même accent ») ; piste V2 : indice DANS l'accent (libellé 600 ou liseré
  interne) sans introduire de 2ᵉ couleur.

**Bilan Chantier A : 0 YELLOW → 1 verte → 2 RED → 3 verte → 4 verte (convergé)
→ 5 verte (finition validée).** Aucun FAIL privacy sur toute la boucle.

## Chantier B — round 0 (commit 857f5c5)

| agent               | scores                                                                  | blocking | major | verdict    |
| ------------------- | ----------------------------------------------------------------------- | -------- | ----- | ---------- |
| robustness-redteam  | dégrad 2 · crash 4 · repli 2 · spa 2 · observers 4                      | 2        | 0     | **RED**    |
| product-conformance | ton 5 · fourchettes 5 · mémoire 5 · démontre 5 · nouv-conv 5 · budget 5 | 0        | 1     | **YELLOW** |
| qa-auditor          | couv 4 · contrat 4 · erreurs 4 · clarté 5 · régressions 5               | 0        | 1     | **YELLOW** |
| privacy-sentinel    | —                                                                       | PASS     | —     | **PASS**   |

→ Ronde **RED**. Le redteam a attrapé une VRAIE faille de concurrence que mes
tests masquaient (ils cliquaient Annuler APRÈS un `applyModel` mock instantané,
jamais pendant la bascule en vol). Défauts retenus :

- **[blocking redteam + major product/qa]** Course « Annuler pendant la
  bascule » : la bascule de fond résolvait `followed:true` INCONDITIONNELLEMENT,
  même après un clic Annuler → télémétrie mensongère ; + deux `applyModelInPage`
  concurrents se disputaient le menu → modèle final non déterministe. → **corrigé**
  jeton `cancelled` partagé (skip `followed:true` si annulé) + restauration
  SÉRIALISÉE après la bascule en vol (`switchInFlight.then(restore)`) → un seul
  événement net, modèle déterministe. + 2 tests de course (applyModel LENT).
- **[blocking redteam]** Fuite de panneau : sur échec de bascule, re-render APRÈS
  `removePanel()` (nav SPA) → panneau obsolète réapparaît. → **corrigé** garde
  `isPanelPresent()` avant le re-render + test SPA.
- **[minor redteam]** `readCurrentModel()` null n'émettait pas `selector_broken`
  → **corrigé** + test.
- **[minor product]** libellé guide « Utiliser {modèle} » trompeur (aucune action)
  → **corrigé** « J'utiliserai {modèle} » (`use_model_guide`).
- **[minor qa]** `schemas.py` seuil sans borne 0..1 → **corrigé** `Field(ge=0, le=1)`.
  · `openapi.info.version` resté « 1.0 » → **corrigé** « 1.1 ».
