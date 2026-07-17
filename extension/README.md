# Extension Sobrio — 1.0.0

Extension navigateur (Chrome/Edge, Manifest V3, [WXT](https://wxt.dev) +
TypeScript) qui recommande sur **claude.ai** le modèle Claude adapté à chaque
prompt — coût et énergie **en fourchettes**, budget d'équipe, suivi des
recommandations. Elle **conseille — et n'agit que si vous l'y autorisez**
(application automatique du modèle activée par défaut, désactivable au popup).

La recommandation ne se fonde pas sur le seul dernier prompt : l'extension
entretient une **mémoire de signaux par conversation** (`conversationMemory` +
`conversationRegistry`) — nombre de messages, contexte estimé,
code/maths/raisonnement vus au fil des tours, modèle courant, historique
recos/dérogations — **jamais le texte**. Un « démontre-le » court dans un fil
mathématique ne part pas naïvement sur le modèle le plus léger.

## Règles non négociables (encodées dans le code ET les tests)

| #   | Règle                                                                                            | Preuve automatisée                                                                                                             |
| --- | ------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------ |
| 1   | Aucun texte ne quitte le poste                                                                   | `extension_zerotext.test.ts`, `extension_hygiene.test.ts` (réseau confiné, aucun console de contenu), schéma télémétrie strict |
| 2   | Lecture seule **par défaut** de claude.ai ; auto-apply en opt-in (activé par défaut, décochable) | `extension_modelswitcher.test.ts` (sans opt-in : aucune action)                                                                |
| 3   | Jamais bloquante (timeout 400 ms → silence)                                                      | `extension_client.test.ts`, `extension_panel.test.ts`                                                                          |
| 4   | Aucun secret dans le bundle                                                                      | `extension_hygiene.test.ts` (aucune URL en dur), storage-only                                                                  |
| 5   | Fourchettes obligatoires (coût/énergie)                                                          | `extension_mock.test.ts`, `extension_ui.test.ts`                                                                               |
| 6   | Permissions minimales (`storage` + claude.ai)                                                    | `scripts/check-hygiene.mjs` (garde de build)                                                                                   |
| 7   | Ton humble                                                                                       | `extension_ui.test.ts` (note « signal ambigu », modes)                                                                         |

## Installation

### Développement

```bash
pnpm install     # pnpm ≥ 10 (postinstall : wxt prepare)
pnpm dev         # Chrome dédié, extension chargée, auto-rechargement claude.ai
```

`pnpm dev` ouvre un navigateur avec l'extension : **rechargez l'onglet
claude.ai** pour voir chaque changement.

### Extension installable (recette / production)

```bash
pnpm build       # → .output/chrome-mv3 (gardes taille + hygiène incluses)
pnpm zip         # → .output/sobrioextension-1.0.0-chrome.zip
```

`chrome://extensions` → « Mode développeur » → « Charger l'extension non
empaquetée » → dossier `.output/chrome-mv3` (ou dézipper l'artefact).

### Déploiement d'entreprise (pour la DSI)

Chrome/Edge permettent de forcer l'installation via politique d'entreprise
(`ExtensionInstallForcelist`) une fois l'extension publiée sur le Chrome Web
Store ou hébergée en interne. L'extension ne demande que la permission
`storage` et l'accès à `https://claude.ai/*` — aucune donnée de conversation
n'est lue ni transmise (règle 1). La configuration (URL API, jeton
d'organisation, mode) se fait par le popup ou, à terme, par politique gérée
(`managed storage` — `TODO(V2)`).

## Modes de backend (popup)

| Mode            | Effet                                                                                                                                                                                         |
| --------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `mock` (défaut) | Réponses locales conformes au contrat — tout se démontre **sans serveur**.                                                                                                                    |
| `api`           | API Sobrio réelle (`make dev` du monorepo). Les signaux sont mappés vers les `features` v1.0 du contrat figé ; le bloc `conversation` reste local tant que la **RFC-0001** n'est pas adoptée. |

## Diagnostic de détection

Popup → **« Tester la détection sur cet onglet »** : indique quelle stratégie a
résolu la zone de saisie (ou signale l'inertie). Outil de première ligne quand
claude.ai fait évoluer son interface — sans ouvrir les DevTools.

## Architecture

| Module                                                                      | Rôle                                                          |
| --------------------------------------------------------------------------- | ------------------------------------------------------------- |
| `signals.ts` / `features.ts`                                                | Signaux du prompt (mesures + drapeaux fermés, `has_math`).    |
| `conversationMemory.ts`                                                     | Mémoire d'un fil (compteurs/drapeaux, jamais le texte).       |
| `conversationRegistry.ts` / `spaLifecycle.ts` / `conversationController.ts` | Multi-conversations, détection SPA, mémoire active.           |
| `mockRules.ts` / `mockClient.ts` / `client.ts`                              | Décision mock, clients mock/api, timeout/debounce.            |
| `remoteConfig.ts`                                                           | Config distante (cache persistant TTL 1 h, versions).         |
| `telemetryQueue.ts`                                                         | File de télémétrie persistante + retry + schéma strict.       |
| `panel.ts` / `messages.ts`                                                  | Badge + panneau (shadow DOM), i18n, modes, a11y.              |
| `selectors.ts` / `diagnostics.ts`                                           | Détection durcie + diagnostic.                                |
| `modelSwitcher.ts`                                                          | Auto-apply (sous-menus, vérification, abandon silencieux).    |
| `content-main.ts`                                                           | Orchestration (SPA, télémétrie, cleanup pagehide).            |
| `test/fixtures/`                                                            | Instantanés DOM headless (remplacent la page d'entraînement). |

## Commandes

```bash
pnpm dev         # dev auto-rechargement claude.ai
pnpm build       # build prod + gardes taille/hygiène (échec si dépassement)
pnpm zip         # artefact installable 1.0.0
pnpm test        # vitest (173 tests)
pnpm lint        # eslint + prettier --check
pnpm check:size  # garde de taille seule (après build)
pnpm check:hygiene  # garde permissions/manifest seule (après build)
```

## Recette humaine

Voir **`RECETTE_5MIN.md`** : la checklist de 5 minutes sur claude.ai réel
(badge, panneau, scénario « démontre-le », dérogation, auto-apply, kill-switch,
API coupée, navigation SPA).

## Limites connues (`TODO(V2)`)

- `token_est` ≈ chars/4 (pas de tokenizer réel) ; langue/maths/code heuristiques.
- Mode `api` : la mémoire de conversation n'influence le routeur qu'après
  adoption de la **RFC-0001** (`signals`, `suggest_new_conversation`,
  `demonstration`, `selector_broken`, `allow_auto_apply`, `telemetry_enabled`).
- Sélecteurs claude.ai plausibles mais à confirmer en recette (outil de
  diagnostic fourni).
- i18n EN partielle (repli FR) ; Firefox/Safari hors périmètre.
- Config par `managed storage` d'entreprise non encore branchée.
