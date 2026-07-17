# Recette 5 minutes — sur claude.ai réel (v1.3.0, `assist_mode`)

> Le seul geste laissé aux fondateurs, quand vous le souhaitez. Tout le reste
> est vérifié automatiquement (218 tests, gardes de build). Cette recette
> confirme le comportement sur le vrai claude.ai, que le code ne peut pas
> tester tout seul. Les 10 états du panneau (clair + sombre) sont archivés dans
> `test/visual/out/final/panneau-clair-sombre-v1.3.0.png`.

## Préparation (1 min)

1. `cd extension && pnpm install && pnpm build`
2. `chrome://extensions` → activer « Mode développeur » → « Charger l'extension
   non empaquetée » → dossier `extension/.output/chrome-mv3`.
3. Ouvrir **https://claude.ai** et recharger l'onglet.

## Checklist (4 min)

- [ ] **Badge** : un « S » discret apparaît dans la barre de saisie (à droite).
      Le survoler : le titre est **honnête selon le mode** (en `auto`, il
      n'affirme pas « n'agit jamais à votre place »).
- [ ] **Panneau** : tapez « Quelle heure est-il à Tokyo ? », marquez une pause
      (~1 s) → un panneau propose un modèle léger, avec confiance et
      **fourchettes** coût/énergie « 0,004–0,006 € » (jamais une valeur unique),
      dans le thème clair ou sombre suivant claude.ai.
- [ ] **Mémoire de conversation (le test clé)** : dans une conversation qui
      contient déjà des maths (posez d'abord une question mathématique et
      laissez Claude répondre), tapez juste « démontre-le » → la reco **n'est
      pas** le modèle le plus léger (la mémoire du fil a parlé). « Pourquoi ? »
      l'explique.

### Les trois modes d'assistance (RFC-0003)

- [ ] **`one_click`** (défaut) : « Utiliser [modèle] » → le sélecteur de modèle
      de claude.ai change réellement (via « Plus de modèles » si besoin), puis
      « Merci, c'est noté ».
- [ ] **`auto`** (confiance ≥ seuil 0,75) : le panneau s'ouvre **déjà en état
      « Basculé sur [modèle] »** (perçu < 300 ms) + bouton **Annuler**. Annuler
      → **le modèle précédent est restauré**. Écarter le panneau sans annuler →
      l'issue est acceptée (exactement **un** événement de suivi net). Déjà sur
      le modèle → « Déjà sur [modèle] — rien à faire ».
- [ ] **`guide`** (kill-switch prudence, ou case popup décochée) : le bouton
      dit « J'utiliserai [modèle] » + « À sélectionner dans le menu de Claude » ;
      cliquer **ne touche pas** la page (lecture seule stricte).
- [ ] **Dérogation** : « Choisir un autre modèle… » → l'événement est tracé
      (popup : compteur « envoyés / en attente » en mode API).

### Robustesse (règle « jamais bloquant »)

- [ ] **Navigation SPA rapide** pendant une bascule `auto` : pas de panneau
      obsolète, **pas de bascule sur le mauvais fil**, chaque conversation garde
      sa mémoire. Le panneau du fil précédent disparaît au changement.
- [ ] **Kill-switch** (mode API) : `enabled=false` côté config d'org → recharger
      → l'extension devient invisible, aucune erreur.
- [ ] **API coupée / réseau off** : aucun panneau, **silence total**, la saisie
      sur claude.ai n'est jamais ralentie.
- [ ] **Diagnostic** : popup → « Tester la détection sur cet onglet » → affiche
      la stratégie de détection (utile si claude.ai change son interface).

## En cas de souci

- Le badge n'apparaît pas ou la bascule n'agit pas : popup → « Tester la
  détection » (si « non détectée », claude.ai a probablement changé son DOM →
  signaler pour mise à jour des sélecteurs ; l'extension retombe alors en `guide`).
- Rien ne s'affiche : c'est **volontaire** en cas d'échec/timeout (règle
  « jamais bloquant »). Vérifier la config du popup (mode, URL, token).
