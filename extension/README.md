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
