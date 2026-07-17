# Recette 5 minutes — sur claude.ai réel

> Le seul geste laissé aux fondateurs, quand vous le souhaitez. Tout le reste
> est vérifié automatiquement (173 tests, gardes de build). Cette recette
> confirme le comportement sur le vrai claude.ai, que le code ne peut pas
> tester tout seul.

## Préparation (1 min)

1. `cd extension && pnpm install && pnpm build`
2. `chrome://extensions` → activer « Mode développeur » → « Charger l'extension
   non empaquetée » → dossier `extension/.output/chrome-mv3`.
3. Ouvrir **https://claude.ai** et recharger l'onglet.

## Checklist (4 min)

- [ ] **Badge** : un « S » discret apparaît dans la barre de saisie (à droite).
- [ ] **Panneau** : tapez « Quelle heure est-il à Tokyo ? », marquez une pause
      (~1 s) → un panneau propose un modèle léger, avec confiance et
      **fourchettes** coût/énergie (jamais une valeur unique).
- [ ] **Mémoire de conversation (le test clé)** : dans une conversation qui
      contient déjà des maths (posez d'abord une question mathématique et
      laissez Claude répondre), tapez juste « démontre-le » → la reco **n'est
      pas** le modèle le plus léger (la mémoire du fil a parlé). « Pourquoi ? »
      l'explique.
- [ ] **Dérogation** : « Choisir un autre modèle… » → l'événement est tracé
      (visible dans le popup : compteur « envoyés / en attente » en mode API).
- [ ] **Application automatique** (activée par défaut) : « Utiliser [modèle] »
      → le sélecteur de modèle de claude.ai change réellement (via « Plus de
      modèles » si besoin). Pour revenir en lecture seule : décocher la case du
      popup, recharger l'onglet → « Utiliser » ne touche plus la page.
- [ ] **Diagnostic** : popup → « Tester la détection sur cet onglet » → affiche
      la stratégie de détection (utile si claude.ai change son interface).
- [ ] **Kill-switch** (mode API) : passer `enabled=false` côté config d'org →
      recharger → l'extension devient invisible, aucune erreur.
- [ ] **API coupée** (mode API) : arrêter le backend → aucun panneau, **silence
      total**, la saisie sur claude.ai n'est jamais ralentie.
- [ ] **Navigation SPA** : passer d'une conversation à une autre sans recharger
      → le panneau de la conversation précédente disparaît ; chaque fil garde
      sa propre mémoire.

## En cas de souci

- Le badge n'apparaît pas ou « Utiliser » n'agit pas : popup → « Tester la
  détection » (si « non détectée », claude.ai a probablement changé son DOM →
  signaler pour mise à jour des sélecteurs).
- Rien ne s'affiche : c'est **volontaire** en cas d'échec/timeout (règle
  « jamais bloquant »). Vérifier la config du popup (mode, URL, token).
