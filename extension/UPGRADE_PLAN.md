# Plan de rattrapage V0 → Extension complète

> Audit du code V0 existant face au référentiel produit
> (`PROMPT_CLAUDE_CODE_EXTENSION_COMPLETE.md`). Boucle 1.
> État de référence : **121 tests verts, bundle 36 KB** (commit d'audit).

Légende : ✅ conforme · 🔶 partiel · ❌ manquant · 🔁 à changer

## Décision transverse actée (fondateur, 2026-07-17)

L'**auto-apply** (changement de modèle dans claude.ai) est **conservé et
industrialisé** (défaut activé, désactivable au popup). La règle 2 reste
« lecture seule PAR DÉFAUT sauf auto-apply » (amendement des 2026-07-16, cf.
`docs/decisions.md`). Le référentiel décrit une règle 2 stricte ; cet écart
est assumé et documenté — il ne sera pas « corrigé » en supprimant l'auto-apply.

## Boucle par boucle

### Boucle 2 — Migration du harnais de test

- 🔁 `dev/testpage/` + `dev/serve.mjs` + entrypoint `testpage.content.ts` +
  script `dev:page` : **à supprimer**.
- ❌ Fixtures DOM headless `test/fixtures/*.html` (nominal, alt1, alt2, broken) :
  **à créer**. Aujourd'hui les tests robustesse lisent `dev/testpage/*.html`.
- 🔁 `pnpm dev` : retirer `SOBRIO_TESTPAGE`, cibler claude.ai seul, documenter.
- 🔶 `filterEntrypoints` : simplifier une fois testpage retiré.

### Boucle 3 — Cycle de vie SPA & mémoire par conversation

- 🔶 `conversationMemory.ts` : mémoire mono-instance avec reset sur changement
  de `threadId`. **Manque** : registre multi-conversations (clé = URL), états
  distincts conservés en navigation entre fils, purge, re-scan paresseux à
  l'arrivée au milieu d'un fil.
- ❌ Détection de navigation SPA (history/URL) : le content actuel ne réagit
  qu'aux mutations DOM, pas aux changements d'URL sans rechargement.

### Boucle 4 — Sélecteurs durcis + diagnostic

- ✅ `selectors.ts` : stratégies ordonnées + repli « plus grand éditable » +
  détecteur de casse `selector_broken`.
- ❌ Bouton popup « Tester la détection sur cet onglet » (diagnostic sans DevTools).
- 🔶 Détachement des observers : fait sur `pagehide` ; à couvrir par un test.

### Boucle 5 — Panneau complet & modes

- ✅ Panneau : reco, confiance, fourchettes, budget, Utiliser/Déroger, Pourquoi,
  bandeau conversation longue, note ambiguë.
- ❌ Prise en compte du `mode` (eco/equilibre/qualite) sur le ton des messages.
- 🔶 i18n : messages FR centralisés + surcharge config ; structure EN à expliciter.
- ❌ Accessibilité : navigation clavier, aria-labels systématiques, contrastes,
  test « aucun style ne fuit hors shadow DOM ».

### Boucle 6 — Config distante industrialisée

- 🔶 `createConfigCache` : TTL 5 min. **À porter** à 1 h + rafraîchissement
  silencieux.
- ✅ Kill-switch `enabled=false`.
- ❌ `min_extension_version` : auto-désactivation si version locale inférieure +
  message popup.
- 🔶 Hors-ligne : dernier état connu conservé ; à couvrir explicitement.

### Boucle 7 — Télémétrie industrialisée

- 🔶 `sendWithRetry` : retry en mémoire (perdu au rechargement). **À changer** :
  file **persistante** (`chrome.storage`) + retry exponentiel + reprise.
- ✅ Schéma strict `RecoEvent` (test de forme).
- ❌ Opt-in télémétrie piloté par config d'org.
- ❌ Compteur diagnostic popup (envoyés / en attente).
- 🔶 Pas d'envoi si kill-switch : à garantir et tester.

### Boucle 8 — Performance & robustesse

- ❌ Script de garde de taille (< 2 Mo, échec du build sinon).
- ❌ Greps automatisés : `console.log` de contenu, permissions en trop, réseau
  hors des 3 endpoints.
- ✅ Debounce/throttle en place.

### Boucle 9 — Packaging & livraison

- 🔶 Version : `0.1.0` → **`1.0.0`**.
- ❌ `CHANGELOG.md`.
- 🔶 README : refonte finale (dev + politique entreprise DSI, diagnostic, limites).
- ❌ `RECETTE_5MIN.md`.
- ✅ Icônes placeholder (garder, ok « sobres définitives »).

## Structure de dossiers cible

```
extension/
├── src/                     # inchangé pour l'essentiel, + conversationRegistry, spaLifecycle, telemetryQueue, diagnostics
├── entrypoints/
│   ├── content.ts           # claude.ai (prod)
│   └── popup/               # + bouton diagnostic, + compteur télémétrie, + message maj
├── test/fixtures/*.html     # NOUVEAU (remplace dev/testpage)
├── tests/*.test.ts          # portés sur les fixtures
├── public/icon/             # inchangé
├── scripts/check-bundle-size.mjs   # NOUVEAU (garde de taille)
├── CHANGELOG.md             # NOUVEAU
├── RECETTE_5MIN.md          # NOUVEAU
└── UPGRADE_PLAN.md          # ce fichier (soldé en fin de parcours)
```

## Suivi (coché au fil des boucles)

- [x] B2 migration harnais · [x] B3 SPA & mémoire · [x] B4 sélecteurs & diagnostic
- [x] B5 panneau & modes · [ ] B6 config distante · [ ] B7 télémétrie
- [ ] B8 perf & robustesse · [ ] B9 packaging
