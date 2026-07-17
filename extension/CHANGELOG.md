# Journal des versions — Extension Sobrio

Format inspiré de [Keep a Changelog](https://keepachangelog.com/fr/).

## 1.0.0 — 2026-07-17

Première version complète (productisation de la V0, 9 boucles).

### Ajouté

- **Cycle de vie SPA** : détection de changement de conversation sans
  rechargement (History + popstate) ; **mémoire de signaux par conversation**
  (clé d'URL), restituée en navigant entre fils, reconstruite à l'arrivée au
  milieu d'un fil, indépendante entre onglets.
- **Diagnostic intégré** au popup : « Tester la détection sur cet onglet »
  (stratégie de détection, sans DevTools).
- **Panneau complet** : jauges confiance/budget, fourchettes coût/énergie,
  « Utiliser [modèle] », dérogation, « Pourquoi ? », bandeau conversation
  longue, note de mode (eco/equilibre/qualite).
- **i18n-ready** : messages FR complets, squelette EN (repli FR), surcharge par
  `config.messages`.
- **Accessibilité** : panneau nommé non modal (focus jamais piégé), jauge
  `progressbar`, fermeture clavier (Échap), focus visibles.
- **Config distante industrialisée** : cache persistant TTL 1 h,
  rafraîchissement silencieux, dernier état connu hors-ligne, kill-switch,
  `min_extension_version` (auto-désactivation + message popup).
- **Télémétrie industrialisée** : file persistante avec retry exponentiel
  (max 3) puis abandon silencieux, schéma strict, opt-out d'organisation,
  compteur (envoyés / en attente) dans le popup.
- **Application automatique du modèle** (amendement règle 2, activée par
  défaut, désactivable) : navigation des sous-menus de claude.ai, résultat
  vérifié, abandon silencieux au moindre doute.
- **Gardes de qualité** : bundle < 2 Mo (échec du build sinon), revue
  d'hygiène (permissions minimales, réseau confiné aux 3 endpoints, aucun
  console de contenu).

### Changé

- Harnais de test : page d'entraînement locale remplacée par des **fixtures
  DOM headless** (nominal / alt1 / alt2 / broken) ; `pnpm dev` cible claude.ai
  en auto-rechargement.
- Version : 0.1.0 → **1.0.0**.

### Sécurité / conformité

- Règle 1 (aucun texte transmis), règle 4 (aucun secret), règle 6 (permissions
  minimales) vérifiées par des tests automatisés dédiés.

## 0.1.0 — 2026-07-16

- V0 « loop engineering » : signaux locaux, mémoire de conversation, client
  mock/api jamais bloquant, badge + panneau, popup, robustesse sélecteurs,
  packaging initial.
