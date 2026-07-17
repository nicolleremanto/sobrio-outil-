# RFC-0003 — assist_mode : bascule de modèle encadrée (auto / one_click / guide)

- **Auteur·e :** chef d'orchestre (finition orchestrée, Chantier B)
- **Date :** 2026-07-17
- **Statut :** acceptée (mise en œuvre)

## Motif

Le Chantier B rend la bascule de modèle **instantanée et encadrée**. Jusqu'ici,
l'application du modèle est un opt-in LOCAL binaire (`settings.autoApplyModel`,
règle 2 amendée le 2026-07-16). Il manque une **politique côté organisation**
pour piloter le niveau d'assistance sans redéployer l'extension, et surtout un
**kill-switch de prudence CGU** permettant à l'org de forcer un mode sans aucun
contact avec la page (`guide`).

On introduit donc `assist_mode` dans la configuration distante
(`GET /v1/extension/config`) :

- `auto` : bascule immédiate si `confidence ≥ auto_confidence_threshold`
  (défaut 0,75), avec confirmation discrète et **Annuler** (restaure le modèle
  précédent) ;
- `one_click` : bascule uniquement au clic « Utiliser {modèle} » (comportement
  par défaut actuel) ;
- `guide` : AUCUN contact page — l'extension affiche seulement, l'utilisateur
  sélectionne à la main (mode de repli et kill-switch prudence).

Le mode EFFECTIF est l'intersection du consentement local et de la politique
org : `autoApplyModel=false` ⇒ `guide` quelle que soit la config ; échec des
sélecteurs au runtime ⇒ **repli silencieux `guide`** + signal `selector_broken`.

La règle n°7 (`CLAUDE.md`) impose une RFC pour tout changement de contrat.

## Impact

- **Contrat modifié** : `contracts/openapi.yaml` (schéma `ExtensionConfig`).
- **Lot A (extension)** : `api.ts` (type `ExtensionConfig` + `AssistMode`),
  `modelSwitcher.ts` (`readCurrentModel`), `panel.ts` (état « basculé » + Annuler),
  `content-main.ts` (orchestration : `resolveAssistMode`, UI optimiste, télémétrie),
  `messages.ts` (libellés), `mockClient` (renvoie `assist_mode` + seuil). Tests dédiés.
- **Lot B (API)** : `schemas.py` (`ExtensionConfig` + deux champs optionnels),
  `routes.py` (défauts). Test api mis à jour.
- **Compatibilité ASCENDANTE** : les deux champs sont **optionnels**. Une config
  déployée sans eux ⇒ `assist_mode='one_click'`, seuil 0,75 (comportement inchangé
  pour l'existant). Aucune migration de données. Rapports déjà générés : non
  concernés (endpoint config uniquement).

## Contrats touchés

`contracts/openapi.yaml`, schéma `ExtensionConfig` — ajout de deux propriétés
OPTIONNELLES (hors `required`, pour compat ascendante) : `assist_mode`
(enum `auto|one_click|guide`, défaut `one_click`) et `auto_confidence_threshold`
(number 0..1, défaut 0.75).

## Version proposée

`contracts/CHANGELOG.md` : entrée **openapi v1.1** — `ExtensionConfig` gagne
`assist_mode` et `auto_confidence_threshold`, tous deux optionnels (compat
ascendante). Pilotage org de la bascule + kill-switch prudence `guide`.

## Alternatives

- **Réutiliser `mode` (eco/equilibre/qualite)** pour piloter la bascule : rejeté
  — `mode` infléchit le TON/le choix de modèle, orthogonal au NIVEAU
  d'assistance ; les surcharger créerait des combinaisons ambiguës.
- **Garder l'opt-in local seul** : rejeté — pas de kill-switch org, pas de
  pilotage de flotte sans redéploiement (exigence CGU/prudence du prompt).
- **Rendre les champs obligatoires** : rejeté — casserait les configs déjà
  déployées ; l'optionnalité + défauts préserve la compat ascendante.
- **Ne rien faire** : rejeté — le Chantier B exige `assist_mode` (contrat §3).

## Décision

Acceptée et mise en œuvre (Chantier B). Sécurité : `guide` reste le repli sûr
universel ; aucune action page hors sélection du modèle ; aucun texte ne quitte
le poste (règle 1 inchangée — la bascule ne touche que le sélecteur de modèle).
Reportée dans `docs/decisions.md`.
