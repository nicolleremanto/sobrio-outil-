# Extension Sobrio — V0 (Lot A)

Extension navigateur (Chrome/Edge, Manifest V3, [WXT](https://wxt.dev) + TypeScript) qui
recommande sur **claude.ai** le modèle adapté à chaque prompt — coût et énergie **en
fourchettes**, budget d'équipe, suivi des recommandations. Elle **affiche et conseille,
n'automatise JAMAIS**.

La recommandation ne se fonde pas sur le seul dernier prompt : l'extension entretient une
**mémoire de signaux de la conversation** (`src/conversationMemory.ts`) — nombre de
messages, taille de contexte estimée, code/maths/raisonnement vus au fil des tours,
modèle courant, historique recos/dérogations — **jamais le texte**. Un « démontre-le »
court dans un fil mathématique ne part pas naïvement sur Haiku.

## Les règles non négociables (encodées dans le code et les tests)

1. **Aucun texte ne quitte le poste** — seuls des nombres et des drapeaux de listes
   fermées sont transmis (`tests/extension_zerotext.test.ts` l'atteste).
2. **Lecture seule** vis-à-vis de claude.ai — badge/panneau à nous (Shadow DOM), aucun
   clic simulé, aucune pré-sélection, aucun DOM fonctionnel modifié.
3. **Jamais bloquante** — timeout 400 ms, échec ⇒ silence total (aucun toast, rien).
4. **Aucun secret dans le bundle** — URL d'API + jeton vivent dans le storage (popup).
5. **Fourchettes obligatoires** — tout coût/énergie affiché est un min–max + périmètre.
6. **Permissions minimales** — `storage` + `https://claude.ai/*` uniquement (le zip de
   prod ne matche jamais la page d'entraînement).
7. **Ton humble** — « recommandé », « suffit probablement » ; signal ambigu ⇒ on le dit.

## Installation

```bash
pnpm install        # pnpm ≥ 10 (postinstall : wxt prepare)
```

**Dev (rechargement à chaud)** : `pnpm dev` — ouvre un Chrome dédié, extension chargée,
qui matche claude.ai **et** la page d'entraînement locale.

**V0 installable** : `pnpm zip` → `.output/sobrioextension-0.1.0-chrome.zip`. Dézipper,
puis `chrome://extensions` → mode développeur → « Charger l'extension non empaquetée »
→ pointer le dossier dézippé (ou directement `.output/chrome-mv3` après `pnpm build`).

## Modes de backend (commutables dans le popup)

| Mode               | Effet                                                                                                                                                                                                                                                                        |
| ------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `mock` (défaut V0) | `src/mockClient.ts` répond localement, conforme au contrat — tout se démontre **sans serveur**. Latence simulée, mode panne pour la recette.                                                                                                                                 |
| `api`              | API Sobrio réelle (`make dev` du monorepo, `http://localhost:8000`, org `demo`). Les signaux sont mappés vers les `features` v1.0 du contrat figé — le bloc `conversation` reste local tant que la RFC v1.1 n'est pas adoptée (`docs/rfc/RFC-0001-signals-conversation.md`). |

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
7. **Jamais bloquant** — popup → mode `api` avec une URL invalide → plus AUCUN
   panneau, aucune erreur visible, la saisie reste fluide.

Variantes de robustesse : `/variant-b.html` (markup alternatif, résolution par
heuristique de repli) et `/variant-broken.html` (extension totalement inerte).

## Recette manuelle sur claude.ai RÉEL (checklist V0)

- [ ] Badge « S » discret visible près de la zone de saisie après chargement.
- [ ] Panneau à la pause de saisie (~600 ms) : modèle recommandé + confiance +
      fourchettes ; **aucune** valeur unique affichée.
- [ ] Scénario mémoire : conversation contenant des maths, puis « démontre-le » →
      la reco n'est pas Haiku.
- [ ] Dérogation : « Choisir un autre modèle… » → accusé, événement
      `followed=false, overridden_to=…` (mode api : visible dans `events_reco`).
- [ ] Kill-switch : `enabled=false` dans la config org → extension invisible.
- [ ] API coupée (arrêter `make dev`) : silence total, zéro erreur console visible,
      saisie jamais ralentie.
- [ ] **Aucune interaction avec l'interface du site** : pas de clic, pas de
      pré-sélection de modèle, DOM fonctionnel intact (inspecter : seuls
      `#sobrio-badge-host` et `#sobrio-reco-host` sont ajoutés).
- [ ] Bundle : `pnpm build` puis vérifier `.output/chrome-mv3` — aucun secret,
      permissions `storage` + `https://claude.ai/*` uniquement.

## Commandes

```bash
pnpm dev        # dev Chrome dédié (matche claude.ai + page d'entraînement)
pnpm dev:page   # sert la page d'entraînement sur :8788
pnpm build      # build production (claude.ai uniquement)
pnpm build:dev  # build avec l'entrypoint page d'entraînement
pnpm zip        # artefact installable .output/sobrioextension-0.1.0-chrome.zip
pnpm test       # vitest (109 tests)
pnpm lint       # eslint + prettier --check
pnpm format     # prettier --write
node dev/make-icons.mjs  # régénère les icônes placeholder
```

## Architecture

| Module                                | Rôle                                                                                                                                           |
| ------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/signals.ts`                      | Bloc `signals` du contrat : mesures + drapeaux (listes fermées), `has_math`, normalisation du modèle courant vers le vocabulaire du catalogue. |
| `src/conversationMemory.ts`           | Mémoire par fil (session uniquement) : compteurs, drapeaux vus, historique recos/dérogations ; reset sur nouveau fil.                          |
| `src/mockRules.ts`                    | Règles de décision pures du mock (4 règles vivantes).                                                                                          |
| `src/mockClient.ts` / `src/client.ts` | Clients mock/api derrière une interface commune ; timeout 400 ms, debounce 600 ms, retry télémétrie ≤ 3, cache config + kill-switch.           |
| `src/panel.ts` / `src/messages.ts`    | Badge + panneau (Shadow DOM) ; textes FR centralisés, surchargeables par `config.messages.fr`, ton humble.                                     |
| `src/selectors.ts`                    | Sélecteurs ordonnés + repli « plus grand éditable visible » + détecteur de casse (`selector_broken`).                                          |
| `src/content-main.ts`                 | Orchestration (observer throttlé, nettoyage pagehide), injectable pour les tests.                                                              |
| `entrypoints/`                        | `content.ts` (prod, claude.ai), `testpage.content.ts` (dev uniquement, filtré du zip), `popup/`.                                               |
| `dev/`                                | Page d'entraînement + variantes robustesse + serveur statique + générateur d'icônes — hors bundle.                                             |

## Limites connues de la V0 (TODO(V1))

- `token_est` ≈ chars/4 (pas de tokenizer réel) ; langue/maths/code heuristiques.
- Le mode `api` n'envoie que les `features` v1.0 : la mémoire de conversation
  n'influence que le mock tant que la **RFC v1.1** n'est pas adoptée côté serveur
  (`signals`, `suggest_new_conversation`, `demonstration`, signal `selector_broken`).
- Sélecteurs claude.ai plausibles mais à valider en fumée manuelle (recette ci-dessus).
- `seen_reasoning` : heuristique grossière (maths, réponses longues, marqueurs).
- Pas de cache/rafraîchissement périodique du kill-switch au-delà du TTL de 5 min.
- i18n EN, Firefox/Safari : hors périmètre V0.
