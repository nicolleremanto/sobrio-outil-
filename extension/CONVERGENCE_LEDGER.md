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
| B        | Bascule instantanée + assist_mode | 1/2 (ronde 6 verte)        | en cours     |

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

## Chantier B — round 1 (commit a7896a1)

| agent               | scores                                                                  | blocking | major | verdict   |
| ------------------- | ----------------------------------------------------------------------- | -------- | ----- | --------- |
| robustness-redteam  | dégrad 3 · crash 4 · repli 3 · spa 2 · observers 5                      | 1        | 1     | **RED**   |
| product-conformance | ton 5 · fourchettes 5 · mémoire 4 · démontre 5 · nouv-conv 5 · budget 5 | 1        | 0     | **RED**   |
| qa-auditor          | couv 5 · contrat 4 · erreurs 4 · clarté 5 · régressions 5               | 0        | 0     | **GREEN** |
| privacy-sentinel    | —                                                                       | PASS     | —     | **PASS**  |

→ Ronde **RED**. Mon patch ronde 0 n'avait traité qu'une facette : les juges ont
trouvé la racine plus profonde (deux blocking convergents). Défauts retenus :

- **[blocking redteam + product]** Cycle de vie conversation : le flux en vol
  rendait le panneau + basculait APRÈS l'`await recommend()` sans re-valider le
  fil actif → nav SPA pendant le fetch = panneau ressuscité + **bascule auto sur
  le mauvais fil** + followed:true. → **corrigé** jeton `isCurrent` (clé de
  conversation figée au lancement, re-vérifiée avant render, avant applyModel et
  avant tout commit) + test de garde SPA.
- **[blocking product]** Timing télémétrie : `followed:true` émis dès le succès
  → une bascule réussie PUIS Annuler émettait DEUX événements contradictoires
  (parcours conçu, pas une course rare) + `recos_followed` corrompu. → **corrigé**
  ACCEPTATION DIFFÉRÉE : `followed:true` n'est émis qu'à l'acceptation (écarter le
  panneau sans annuler : fermeture/Échap/nav/flux suivant) ; `onCancel` est le
  SEUL émetteur en cas d'annulation → exactement un événement net. Registre
  `pendingAutoAccept` + garde `outcomeCommitted`. Tests réécrits (les anciens
  entérinaient le double-événement).
- **[minor]** FastAPI `main.py` version → 1.1 ; `policy_json` invalide (seuil hors
  0..1) → repli défauts (plus de 500) + test ; libellé « déjà sur {modèle} » quand
  auto et modèle déjà courant ; en-têtes de sources « v1.1 » ; test guide non trivial.

## Chantier B — round 2 (commit 38f7ddc)

| agent               | scores                                                                  | blocking | major | verdict    |
| ------------------- | ----------------------------------------------------------------------- | -------- | ----- | ---------- |
| robustness-redteam  | dégrad 4 · crash 5 · repli 5 · spa 3 · observers 5                      | 0        | 1     | **YELLOW** |
| product-conformance | ton 3 · fourchettes 5 · mémoire 5 · démontre 5 · nouv-conv 5 · budget 5 | 0        | 1     | **YELLOW** |
| qa-auditor          | couv 3 · contrat 5 · erreurs 3 · clarté 4 · régressions 3               | 1        | 0     | **RED**    |
| privacy-sentinel    | —                                                                       | PASS     | —     | **PASS**   |

→ Ronde **RED**. Le cycle-vie + l'acceptation différée tiennent ; les juges
descendent d'un cran : **flux CONCURRENTS de la même conversation** (debounce
600 ms < bascule lente ~2,7 s). Défauts retenus :

- **[blocking qa + major redteam]** Deux flux auto se chevauchent : `pendingAutoAccept`
  écrasé sans flush → acceptation ORPHELINE (committée 0 fois) pour la reco
  supplantée. → **corrigé** jeton de génération `flowGeneration` : un flux plus
  ancien qui se résout après avoir été supplanté committe SON acceptation
  (`commitAccept()`) au lieu d'écraser le pending du plus récent + test de
  concurrence (F1 lent supplanté par F2 → chacune committée exactement une fois).
- **[major product]** Titre du badge « n'agit jamais à votre place » FAUX en auto
  (règle 7). → **corrigé** `badge_title_auto` honnête, passé selon le mode effectif.
- **[minor]** clic badge → `removePanel` sans flush (acceptation orpheline) →
  **corrigé** (badge `onDismiss` = flush) ; `switched_back` affirmait un fait
  incertain → **reformulé** en intention ; `policy_json` partiellement invalide
  écrasait `guide` → **corrigé** assainissement clé par clé + test ; onDismiss
  pendant bascule en vol → **corrigé** (flush du pending, posé après succès seul).
- **[minor assumé]** nav SPA pendant la bascule → acceptation non committée
  (sous-comptage, sens sûr) : documenté comme choix conservateur.

## Chantier B — round 3 (commit 071fdd4)

| agent               | scores                                                                  | blocking | major | verdict    |
| ------------------- | ----------------------------------------------------------------------- | -------- | ----- | ---------- |
| robustness-redteam  | dégrad 4 · crash 5 · repli 5 · spa 5 · observers 5                      | 0        | 0     | **GREEN**  |
| product-conformance | ton 5 · fourchettes 5 · mémoire 5 · démontre 5 · nouv-conv 5 · budget 5 | 0        | 0     | **GREEN**  |
| qa-auditor          | couv 4 · contrat 4 · erreurs 4 · clarté 4 · régressions 4               | 0        | 1     | **YELLOW** |
| privacy-sentinel    | —                                                                       | PASS     | —     | **PASS**   |

→ Ronde **YELLOW**. redteam et product GREEN (spa remonte à 5) ; qa attrape un
major que le jeton de génération ne couvrait pas :

- **[major qa]** Sérialisation DOM INTER-flux : `switchInFlight` est local à un
  flux → deux flux concurrents pouvaient lancer deux `applyModelInPage` sur le
  même menu Radix → modèle final non déterministe, faux `selector_broken`. Le
  jeton corrige la télémétrie, pas l'opération DOM. → **corrigé** verrou
  module-level (`switchQueue`) dans `modelSwitcher.ts` : au plus une bascule DOM
  en vol, ordre déterministe (le dernier demandé gagne) + test de sérialisation.
- **[minor redteam]** arming du pending sans garde `isPanelPresent` (asymétrie) →
  **corrigé** (arme si panneau présent ET dernier, sinon committe). · `applyModel`
  sans try/catch → **corrigé** (défensif, jamais de rejet non géré).
- **[minor qa]** `policy_json` non-objet → 500 possible → **corrigé** (normalisation
  `isinstance dict`) + test.
- **[minor product]** badge one_click « n'agit jamais » ambigu → **corrigé**
  `badge_title_one_click` (« applique … à votre clic »). · silence télémétrie de
  « déjà sur le modèle » → **documenté** comme choix assumé (issue neutre).
- **[minor product, hors périmètre]** budget=None en prod (TODO Lot B).

## Chantier B — round 4 (commit 0268d65)

| agent               | scores                                                                  | blocking | major | verdict    |
| ------------------- | ----------------------------------------------------------------------- | -------- | ----- | ---------- |
| robustness-redteam  | dégrad 5 · crash 5 · repli 4 · spa 3 · observers 5                      | 0        | 1     | **YELLOW** |
| product-conformance | ton 5 · fourchettes 5 · mémoire 5 · démontre 5 · nouv-conv 5 · budget 5 | 0        | 0     | **GREEN**  |
| qa-auditor          | couv 5 · contrat 4 · erreurs 5 · clarté 4 · régressions 5               | 0        | 0     | **GREEN**  |
| privacy-sentinel    | —                                                                       | PASS     | —     | **PASS**   |

→ Ronde **YELLOW**. product + qa GREEN ; redteam attrape le dernier major
subtil : l'ACTION DOM n'était pas gardée par `isCurrent` (la télémétrie l'était).

- **[major redteam]** Pendant la navigation des menus (~2,7 s), une nav SPA
  pouvait faire atterrir le clic terminal sur la mauvaise conversation (sélecteur
  claude.ai global) → mutation silencieuse du mauvais fil. → **corrigé** : jeton
  `isCurrent` threadé jusqu'à `applyModelInPageExclusive`, re-vérifié juste avant
  le clic terminal (nav en vol → `tryCloseMenu` + false) + test de garde de currency.
- **[minor redteam]** try/catch `applyAndReport` non testé → **test** (applyModel
  rejette → pas de crash, selector_broken, repli). · preuve de sérialisation faible
  → **renforcée** (journal d'ordre des clics : haiku avant sonnet, sans entrelacement).
- **[minor qa]** en-têtes « v1.0 » périmés (schemas.py, api.ts) → **v1.1/RFC-0003**.
  · fusion `policy_json.messages` superficielle → TODO(LotB) documenté.
- **[minor product]** état « déjà sur le modèle » absent de la capture →
  **ajouté** (10 états). · KPI recos_followed/shown & libellé optimiste → assumés/documentés.

## Chantier B — round 5 (commit f7224e5)

| agent               | scores                                                                  | blocking | major | verdict    |
| ------------------- | ----------------------------------------------------------------------- | -------- | ----- | ---------- |
| robustness-redteam  | dégrad 4 · crash 5 · repli 4 · spa 4 · observers 5                      | 0        | 1     | **YELLOW** |
| product-conformance | ton 5 · fourchettes 5 · mémoire 4 · démontre 5 · nouv-conv 5 · budget 5 | 0        | 0     | **GREEN**  |
| qa-auditor          | couv 4 · contrat 5 · erreurs 3 · clarté 4 · régressions 5               | 0        | 1     | **YELLOW** |
| privacy-sentinel    | —                                                                       | PASS     | —     | **PASS**   |

→ Ronde **YELLOW**. product GREEN. redteam + qa attrapent le MÊME major — que ma
propre correction ronde 4 avait introduit :

- **[major redteam + qa]** Faux `selector_broken` : la garde de currency (ronde 4)
  renvoie `false`, indistinguable d'un vrai échec de sélecteurs → `applyAndReport`
  émettait le signal de santé sur un cas BÉNIN (nav SPA pendant la bascule),
  polluant le signal ops. → **corrigé** : `if (!ok && isCurrent()) signal`
  (nav → pas de faux signal ; vrai échec sur fil courant → signal conservé) +
  test « nav pendant la bascule → pas de selector_broken ».
- **[minor redteam]** `poll()` documenté comme filet mais non câblé → **câblé**
  (`ConversationController.pollIntervalMs` = 2 s, nettoyé au stop) ; doc alignée.
  · match par famille (2 versions d'une famille → clic du premier) → **documenté**
  TODO(V2) (gamme actuelle : une version par famille).
- **[minor product]** CLAUDE.md règle 2 disait « uniquement au clic » (contredit
  par auto) → **amendement RFC-0003** ajouté. · `recos_shown` sur « déjà sur le
  modèle » & harnais de capture ré-implémenté → documentés (résidus V2).

## Chantier B — round 6 (commit 5275897)

| agent               | scores                                                                  | blocking | major | verdict   |
| ------------------- | ----------------------------------------------------------------------- | -------- | ----- | --------- |
| robustness-redteam  | dégrad 5 · crash 5 · repli 5 · spa 5 · observers 4                      | 0        | 0     | **GREEN** |
| product-conformance | ton 5 · fourchettes 5 · mémoire 5 · démontre 5 · nouv-conv 5 · budget 5 | 0        | 0     | **GREEN** |
| qa-auditor          | couv 4 · contrat 5 · erreurs 5 · clarté 4 · régressions 5               | 0        | 0     | **GREEN** |
| privacy-sentinel    | —                                                                       | PASS     | —     | **PASS**  |

→ Ronde **VERTE (1/2)** — 1re du streak. Le faux `selector_broken` est levé, le
poll est câblé. Minors triviaux corrigés avant la ronde 7 :

- **corrigé** filet périodique (poll) non testé (redteam + qa) → **test fake-timers**
  (poll rattrape une nav bypass-History ; stop() nettoie l'intervalle).
- **corrigé** CLAUDE.md règle 2 « uniquement au clic » contredisait l'amendement
  auto → « au clic (mode one_click) » + renvoi RFC-0003.
- **corrigé** en-tête `main.py` « figée en v1.0 » (oubli du balayage r4) → v1.1.
- **assumé (documenté)** vraie casse de sélecteurs coïncidant avec une nav
  sortante = abandon silencieux (sous-comptage, sens sûr) ; harnais de capture ;
  recos_shown « déjà sur le modèle » ; budget=None prod (Lot B).
