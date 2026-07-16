# Extension Sobrio — Lot A (squelette Lot 0)

Extension navigateur (Chrome/Edge, Manifest V3, [WXT](https://wxt.dev) + TypeScript) qui
recommande sur **claude.ai** le modèle adapté à chaque prompt. Elle **affiche et
conseille, n'automatise JAMAIS**.

## Rappel — règle n°2 (non négociable)

L'extension est en **lecture seule** vis-à-vis de claude.ai :

- elle **affiche** une recommandation, ne clique pas, ne pré-sélectionne rien ;
- elle ne modifie **jamais** le DOM fonctionnel de claude.ai — le panneau vit dans un
  hôte dédié + Shadow DOM ajouté à côté (`src/panel.ts`) ;
- **aucun secret dans le bundle** : URL de l'API, `org_id` et token sont saisis dans le
  popup et stockés dans `browser.storage.local`.

Et règle n°1 : le texte du prompt reste **local**. Il est réduit en _features_
(`src/features.ts`) et seules ces features partent vers l'API — jamais le texte,
jamais dans les logs (`prompt_text` est omis en v0).

## Périmètre Lot A (Lot 0 = squelette)

| Fichier                  | Rôle                                                                                                                                                                                                               |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `entrypoints/content.ts` | Content script `https://claude.ai/*` : observe la saisie (debounce 600 ms), features locales, `POST /v1/recommend` (timeout 400 ms), panneau Shadow DOM. Échec/timeout ⇒ **rien n'est affiché** (jamais bloquant). |
| `entrypoints/popup/`     | Popup : config (URL API, org, token → storage), état (`GET /v1/extension/config`, kill-switch, mode), lien support placeholder.                                                                                    |
| `src/selectors.ts`       | Module dédié des sélecteurs claude.ai, fallbacks, résolution `null` sans throw (dégradation silencieuse).                                                                                                          |
| `src/features.ts`        | Fonctions pures : `char_len`, `token_est` (≈ chars/4), `lang` fr/en/other, `has_code`, `has_attachment_hint`, `keyword_flags` (liste fermée du contrat).                                                           |
| `src/api.ts`             | Client typé des 3 endpoints de `contracts/openapi.yaml` (source de vérité), Bearer, AbortController 400 ms.                                                                                                        |
| `src/panel.ts`           | Panneau isolé : modèle + confiance + fourchettes coût/énergie (min–max, périmètre — règle n°3), boutons « je suis la reco » / « déroger » (télémétrie stricte).                                                    |

La logique métier finale est hors Lot 0 — voir les marqueurs `TODO(LotA)` dans le code
(tokenizer réel, i18n, cache du kill-switch, opt-in `send_prompt_text`, UX finale…).

## Commandes

```bash
pnpm install   # dépendances (pnpm ≥ 10 ; postinstall lance `wxt prepare`)
pnpm dev       # développement (rechargement à chaud, profil Chrome dédié)
pnpm build     # build production → .output/chrome-mv3
pnpm test      # tests unitaires (vitest, features + sélecteurs)
pnpm lint      # eslint + prettier --check
pnpm format    # prettier --write
```

## Démo humaine V0 — page d'entraînement (boucle 3)

Aucune dépendance à claude.ai : tout se joue en local, en mode **mock** (défaut).

```bash
pnpm dev:page   # terminal 1 — sert le faux chat sur http://localhost:8788
pnpm dev        # terminal 2 — Chrome dédié avec l'extension (matche aussi le faux chat)
```

Scénario complet à dérouler sur `http://localhost:8788` :

1. **Reco simple** — taper « Quelle heure est-il à Tokyo ? », attendre ~600 ms :
   le panneau propose **Claude Haiku 4.5** (règle `mock:short_simple`), avec
   jauge de confiance, fourchettes coût/énergie (min–max) et jauge budget.
2. **Mémoire de conversation (LE scénario)** — cliquer « + bulle maths », puis
   taper « démontre-le » : la reco passe à **Claude Sonnet 4.6**
   (`mock:reasoning_context`) alors que le prompt est court — la mémoire du fil
   a parlé. « Pourquoi ? » explique la règle en langage clair.
3. **Dérogation** — dans le panneau, « Choisir un autre modèle… » → Opus :
   accusé discret, événement `followed=false, overridden_to=opus-4-8` capturé
   par le mock (visible dans les tests ; en mode api : `events_reco`).
4. **Suivi** — « Utiliser Claude Sonnet 4.6 » : note l'intention (aucune action
   sur la page — règle 2) et télémètre `followed=true`.
5. **Fil long** — cliquer « + fil long (20 bulles) », retaper un mot : bandeau
   discret « Conversation longue — repartir de zéro coûtera probablement moins ».
6. **Nouvelle conversation** — cliquer « Nouvelle conversation » : la mémoire se
   réinitialise, « démontre-le » seul repart sur un signal ambigu (ton humble).
7. **Jamais bloquant** — couper `pnpm dev:page`… la page disparaît, mais pour
   simuler l'API muette : popup → mode `api` avec une URL invalide → plus AUCUN
   panneau, aucune erreur visible, la saisie reste fluide.

## Checklist de validation (démo Lot A)

- [ ] La reco s'affiche sur claude.ai après une pause de saisie (~600 ms), dans un
      panneau isolé, sans toucher au DOM fonctionnel de la page.
- [ ] La dérogation est télémétrée (`followed=false`, `overridden_to` = modèle choisi) ;
      le suivi aussi (`followed=true`, `overridden_to=null`).
- [ ] La configuration (URL API, org, token) se fait via le popup et atterrit dans
      `browser.storage.local` — rien en dur dans le bundle.
- [ ] Jamais bloquant : API coupée ou lente (> 400 ms) ⇒ aucun panneau, aucune erreur
      visible, la saisie sur claude.ai n'est jamais ralentie.
- [ ] Zéro secret dans le bundle : vérifier `.output/chrome-mv3` (pas de token, pas
      de clé, pas d'URL d'API en dur).

## Notes

- Contrat d'API : `contracts/openapi.yaml` (v1.0, figé) — tout changement passe par une
  RFC (`docs/rfc/`) + `contracts/CHANGELOG.md` (règle n°7).
- L'appel `fetch` du content script vers l'API suppose que l'API autorise l'origine
  `https://claude.ai` (CORS, côté Lot B). En cas de refus : dégradation silencieuse.
- Permissions minimales : `storage` uniquement ; le content script est limité à
  `https://claude.ai/*`.
