# Décision d'architecture — Routeur de recommandation Sobrio (classifieur, PAS de LLM)

- **Date :** 2026-07-18 (matérialisée depuis le cadrage fondateur « ROUTEUR IA SOBRIO v0 → v1 » ;
  le document n'existait pas encore dans le repo — décision chef d'orchestre, cf. `docs/decisions.md`)
- **Statut :** actée

## Décision

Le moteur de recommandation de modèles (« routeur ») est un **classifieur à deux étages,
PAS un LLM** :

- **Étage 1 — gradient boosting (LightGBM)** sur les signaux structurés du contrat
  (`signals.prompt` + `signals.conversation`, RFC-0001) : multiclasse sur les ids du
  catalogue, **p95 < 5 ms CPU**, artefact < 20 Mo.
- **Étage 2 — embeddings multilingues (optionnel, opt-in par organisation)** :
  `multilingual-e5-small` exporté **ONNX** (int8 si la qualité est préservée) + tête
  calibrée. **p95 < 30 ms CPU.** Le texte est traité **en mémoire uniquement, jamais
  stocké** ; l'étage 2 REFUSE toute requête si la politique d'org a
  `send_prompt_text=false`. **Désactivé par défaut partout.**

## Séquence produit

**v0 heuristique (jour 1) → v0.5 classifieur pré-entraîné (corpus de démarrage à froid)
→ v1 recalibré mensuellement par organisation** sur notre télémétrie (`events_reco`).

L'interface `Router.decide(signals) -> Decision{model, confidence, rule}` est **stable** :
tout se branche derrière ; rien ne change côté extension ni côté contrat `/v1/recommend`.

## Invariants (incarnés par privacy-sentinel et cost-guard, non waivables)

1. Aucun texte de prompt stocké ni loggé, nulle part (base, logs, artefacts, rapports —
   les rapports citent des ids, jamais des textes).
2. **Repli heuristique systématique** : artefact manquant, erreur, timeout interne
   > 50 ms ⇒ réponse via la v0 heuristique, silencieusement, `rule="fallback:heuristic"`.
   Le routeur ML ne peut JAMAIS rendre l'API indisponible.
3. **Gate de promotion** : un artefact n'est promu que s'il bat les heuristiques ET
   l'artefact précédent sur le golden set figé, avec calibration acceptable.
4. **Coûts** : tout appel API payant (distillation, étiquetage) en dry-run par défaut ;
   l'exécution réelle exige `SOBRIO_ALLOW_PAID_CALLS=1` + cap `SOBRIO_MAX_SPEND_USD`
   (défaut 20). La CI ne dépense jamais un centime.
5. **Licences** : registre `router/data/LICENSES.md` rempli AVANT usage de tout dataset.
6. **Reproductibilité** : seeds fixés, versions épinglées, `metadata.json` par artefact.

## Alternatives rejetées

- **LLM auto-hébergé comme routeur** : hors périmètre (latence, RAM VPS, coût).
- **Routage côté extension** : contredit « l'intelligence est côté serveur ».
- **Envoyer/stocker le texte pour l'étage 1** : interdit (règle n°1).

## Contrainte machine notée (2026-07-18)

Le poste de développement a ~4 Gi de disque libre : l'export ONNX **n'utilisera pas
torch** (≈ 2 Gi) — l'étage 2 s'appuie sur un modèle **pré-exporté ONNX** téléchargé
derrière flag (cache fixtures en CI), avec `onnxruntime` + `tokenizers` seuls.
