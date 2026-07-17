# Rapport de finition orchestrée multi-agents — Extension Sobrio V2

**Chef d'orchestre :** boucle de convergence autonome (construire → prouver →
juger par agents INDÉPENDANTS à contexte neuf → consigner → décider).
**Date de sortie :** 2026-07-17 · **Version :** 1.3.0 · **Contrat :** openapi v1.1 (RFC-0003).

## 1. Résultat

Les **trois chantiers** ont convergé selon le critère **2 rondes vertes
consécutives** (§2 du prompt), sans jamais waiver un FAIL `privacy-sentinel`.

| Chantier | Sujet                                                  | Convergence | Rondes |
| -------- | ------------------------------------------------------ | ----------- | ------ |
| **C**    | Catalogue de modèles à jour (gamme courante, RFC-0002) | ✅ 2/2      | 0→2    |
| **A**    | Refonte graphique du panneau (charte §4, thèmes)       | ✅ 2/2      | 0→5    |
| **B**    | Bascule instantanée + `assist_mode` (RFC-0003)         | ✅ 2/2      | 0→7    |

Preuves finales (commit de sortie) : `make test` **vert** (72 Python + 218
extension), `make lint` vert, `tsc --noEmit` propre, `pnpm build` vert (bundle
~75 Ko < 2 Mo, permissions minimales `storage` + `https://claude.ai/*`), capture
des **10 états × 2 thèmes** archivée
(`test/visual/out/final/panneau-clair-sombre-v1.3.0.png`).

## 2. Ce que le dispositif adversarial a réellement attrapé

La valeur du dispositif : des agents à **contexte neuf** ont trouvé des défauts
que l'auteur aurait livrés. Les plus marquants :

- **[Chantier C, ronde 0]** Régression **inter-lots** : changer les ids du
  catalogue partagé cassait les 4 lots Python (`make test` = 22 échecs). J'avais
  déclaré vert sur la seule suite extension → `make test` complet devient le critère.
- **[Chantier A, ronde 0]** Capture d'écran **tronquée** (4 états sur 6) : le mode
  `--screenshot` de Chrome clippe au viewport → capture pleine page.
- **[Chantier A, ronde 2]** **Blocking lint** : journal édité APRÈS le dernier
  lint → `prettier` rouge. Discipline « linter après toute édition » instaurée.
- **[Chantier A, ronde 3]** Faille de **sincérité budget** : un dépassement >100 %
  s'affichait « 100 % » → barre bornée mais libellé réel (« 118 % »).
- **[Chantier B, rondes 0→5]** Une **cascade de concurrence** de plus en plus fine,
  chaque ronde révélant un défaut réel sous le précédent :
  - r0 course « Annuler pendant la bascule » (télémétrie mensongère, modèle non
    déterministe) → jeton d'annulation + restauration sérialisée ;
  - r1 **cycle-vie conversation** (bascule sur le mauvais fil) + **timing
    télémétrie** (double événement) → `isCurrent` + acceptation différée ;
  - r2 **flux concurrents** (acceptation orpheline) → jeton `flowGeneration` ;
  - r3 **sérialisation DOM inter-flux** → verrou module-level `switchQueue` ;
  - r4 **action DOM non gardée** (clic terminal sur le mauvais fil) → `isCurrent`
    threadé jusqu'au clic ;
  - r5 **faux `selector_broken`** (introduit par le fix r4) → signal seulement si
    `isCurrent`.

Chaque correctif a été prouvé par un test dédié (courses simulées à `applyModel`
lent, garde de currency, sérialisation, faux-signal, filet de poll fake-timers).

## 3. Livré (contrat §3, charte §4)

- **Chantier C** — catalogue `2026-07.2` aligné sur la gamme Anthropic vérifiée
  en ligne (Haiku 4.5 / Sonnet 5 / Opus 4.8 / Fable 5, ids d'API) ; RFC-0002 ;
  tous les consommateurs (extension + api/connector/warehouse/report) alignés.
- **Chantier A** — `panelStyle.ts` source unique de la CSS ; thèmes clair/sombre ;
  charte §4 (accent sauge unique, grille 8, 12 px rayon, badge 22 px, fourchettes
  en tiret demi-cadratin) ; a11y (progressbar, `aria-valuetext`, reduced-motion) ;
  capture pleine page mono-source.
- **Chantier B** — `assist_mode` (`auto`/`one_click`/`guide`) + seuil, RFC-0003,
  openapi v1.1 (champs optionnels, compat ascendante). UI **optimiste** (bascule
  perçue < 300 ms) + **Annuler** (restaure le précédent) ; **acceptation différée**
  (exactement un événement net par reco) ; garde `isCurrent` (télémétrie ET action
  DOM) ; verrou DOM (sérialisation) ; repli silencieux `guide` + `selector_broken`
  (émis seulement sur vraie casse) ; badge **honnête** selon le mode ; kill-switch
  org `guide`.

## 4. Résidus documentés (TODO V2 — non bloquants)

- `runRecommendationFlow` concentre la machine à états d'acceptation différée
  (lisibilité ; invariants couverts par tests) — extraction possible.
- Match de modèle par **famille** (la gamme actuelle n'a qu'une version par
  famille ; sinon préférer un abandon à un choix ambigu).
- Harnais de capture = miroir manuel du markup (seule `PANEL_CSS` est mono-source ;
  garde de classes en place).
- `createThrottle.cancel()` (timer terminal bénin au pagehide).
- `budget=None` en production (peuplement Lot B) ; fusion `messages` superficielle
  (Lot B) ; EN_MESSAGES partiel (i18n V2).

## 5. Gouvernance

RFC dédiées (`RFC-0002` catalogue, `RFC-0003` assist_mode ; `RFC-0001`
préexistante) + `contracts/CHANGELOG.md` (catalogue 2026-07.2, openapi v1.1) +
`docs/decisions.md`. Le journal de
convergence (`CONVERGENCE_LEDGER.md`) trace ronde par ronde les verdicts des
agents indépendants — la preuve que la boucle a réellement tourné.
