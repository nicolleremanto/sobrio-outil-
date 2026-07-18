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

## §5 — Invariants (incarnés par privacy-sentinel et cost-guard, non waivables)

> Les renvois du code (« §5.2 », « §5.3 »…) pointent vers les items numérotés
> ci-dessous ; les budgets chiffrés sont en §7.

**§5.1** Aucun texte de prompt stocké ni loggé, nulle part (base, logs, artefacts, rapports —
   les rapports citent des ids, jamais des textes).
**§5.2** **Repli heuristique systématique** : artefact manquant, erreur, timeout interne
   > 50 ms ⇒ réponse via la v0 heuristique, silencieusement, `rule="fallback:heuristic"`.
   Le routeur ML ne peut JAMAIS rendre l'API indisponible.
**§5.3** **Gate de promotion** : un artefact n'est promu que s'il bat les heuristiques ET
   l'artefact précédent sur le golden set figé, avec calibration acceptable.
**§5.4** **Coûts** : tout appel API payant (distillation, étiquetage) en dry-run par défaut ;
   l'exécution réelle exige `SOBRIO_ALLOW_PAID_CALLS=1` + cap `SOBRIO_MAX_SPEND_USD`
   (défaut 20). La CI ne dépense jamais un centime.
**§5.5** **Licences** : registre `router/data/LICENSES.md` rempli AVANT usage de tout dataset.
**§5.6** **Reproductibilité** : seeds fixés, versions épinglées, `metadata.json` par artefact.

## Gate de promotion (§5.3) — seuils chiffrés et rationnels (chantier R3)

- **Exactitude pondérée** `1 − (2·sous + sur) / (2n)` : le SOUS-dimensionnement
  compte double. Réconciliation avec la mission de sobriété (revue r0) : le
  sur-dimensionnement est le gaspillage que Sobrio combat, mais un routeur qui
  SOUS-sert détruit la confiance produit et pousse l'utilisateur à
  sur-provisionner en permanence — pire pour la sobriété à terme. Le
  sur-dimensionnement reste pénalisé (1x) ET gardé par le critère dédié de
  non-régression du sous-dim + le reporting brut (les deux exactitudes
  figurent au rapport ; le score pondéré n'est pas une « exactitude » au sens
  strict, c'est un score à coût asymétrique).
- **ECE ≤ 0.10 (absolu)** : plafond d'hygiène — marge au-dessus de la baseline
  heuristique vivante (0.0934) pour ne pas rendre la première promotion
  impossible, MAIS complété par la **non-régression** `ece(candidat) ≤
  ece(référence) + 0.01` vs baseline ET previous : la calibration ne peut
  jamais dériver silencieusement vers la borne (revue r0). NB (revue r1) :
  pour la baseline courante (0.0934 + 0.01 = 0.1034 > 0.10), le plafond
  ABSOLU est le critère liant ; la non-régression devient liante dès qu'une
  référence mieux calibrée (< 0.09) est promue (effet cliquet voulu).
- **Sous-dimensionnement non-régressif** : `taux(candidat) ≤ min(baseline,
  previous) + 0.02` — LE coût produit ne se dégrade pas même si l'agrégat
  monte, ni vs l'heuristique ni vs l'artefact promu (aligné r2).
- **Bande d'auto-bascule (confiance ≥ 0.75, RFC-0003)** : l'ECE global à bins
  égaux peut masquer une sur-confiance précisément là où le produit agit SANS
  clic. Découverte r0, chiffres PRÉCIS (revue ml r1) : la RÈGLE
  `reasoning_context` long (confiance 0.75 pile) n'est correcte qu'à
  **51,5 %** (n=33) ; la BANDE ≥ 0.75 dans son ensemble est à 65,15 %
  (confiance moyenne 0.775, écart 0.1235 — `short_simple`@0.80 est bien
  calibrée à 78,8 %). Le harnais mesure `calibration_bande_auto.ecart` (+
  un diagnostic informatif PAR valeur de confiance) et le gate exige la
  non-régression (`+ 0.02`, vs baseline ET previous). La recalibration de
  fond de la tranche 0.75 est un objectif R5.
- **Latence : budget ABSOLU** (p95 ≤ 5 ms étage 1, ≤ 30 ms étage 2) — pas de
  critère relatif : le contrat de latence est le budget, pas l'artefact
  précédent (décision assumée, revue qa r0).
- **Épinglage** : les rapports comparés doivent porter le hash CANONIQUE du
  golden figé (`GOLDEN_SHA256`) — injecté par la CLI, pas seulement l'accord
  interne candidat/baseline.
- **Tolérances** (0.01 ECE, 0.02 taux) : marges d'estimation sur n=181 points
  (n effectif ≈ 55 gabarits) — cf. limites_statistiques du coverage_report.
  Arithmétique (revue r1) : SE ≈ √(p(1−p)/n_eff) ≈ 0.054 pour p≈0.2 à
  n_eff=55 ; tol 0.02 ≈ 0.37 SE — bande de non-régression CONSERVATRICE
  (penche vers le blocage), choix assumé.
- **Références de non-régression** (tranché r1, avant R5) : sous-dim, bande
  auto ET ECE sont gardés vs baseline ET previous (le min des deux + tol) —
  un candidat ne peut jamais régresser vers le plancher heuristique une fois
  un artefact ML promu. Précision (défaut prouvé r2) : pour la bande auto,
  seules les références à bande MESURÉE (n > 0) bornent le min — l'écart 0.0
  d'une bande vide est une convention (« rien à dégrader »), pas une mesure,
  et rejetait à tort un candidat mieux calibré que l'heuristique.
  TODO(R5) : le critère bande reste RELATIF (sans plafond absolu) — ancré
  aujourd'hui par la bande heuristique toujours mesurée (n=66, plafond
  effectif 0.1435) ; si une baseline non-heuristique à bande vide devient
  possible, envisager un plafond absolu d'écart (analogue au 0.10 d'ECE).
  Les bornes référence+tolérance sont arrondies à 10 décimales : ≤ inclusif
  garanti à la limite exacte (l'addition flottante brute ne l'était pas
  pour ~4,9 % des références à 4 décimales — qa r3).

## §7 — Budgets (miroir du ledger)

Étage 1 p95 < 5 ms CPU · Étage 2 p95 < 30 ms CPU · `/v1/recommend` p95
< 150 ms · RAM < 1 Go · artefacts : étage 1 < 20 Mo, étage 2 < 500 Mo ·
dépense API : 0,00 $.

## Alternatives rejetées

- **LLM auto-hébergé comme routeur** : hors périmètre (latence, RAM VPS, coût).
- **Routage côté extension** : contredit « l'intelligence est côté serveur ».
- **Envoyer/stocker le texte pour l'étage 1** : interdit (règle n°1).

## Contrainte machine notée (2026-07-18)

Le poste de développement a ~4 Gi de disque libre : l'export ONNX **n'utilisera pas
torch** (≈ 2 Gi) — l'étage 2 s'appuie sur un modèle **pré-exporté ONNX** téléchargé
derrière flag (cache fixtures en CI), avec `onnxruntime` + `tokenizers` seuls.
