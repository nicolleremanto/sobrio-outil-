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
  Réserve « ECE bins / confiances discrètes » (r0) LEVÉE par R5 : les
  confiances CONTINUES de ml_v05 (softmax calibré isotonique conservateur)
  peuplent désormais les 10 bins — la résolution de l'ECE est pleinement
  utilisée sur les rapports ml.
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
  TRANCHÉ (R5, ex-TODO) : le critère bande porte désormais AUSSI un
  **plafond ABSOLU d'écart 0.10** (critère 7-bis, CLI `--bande-ecart-max`,
  borne ≤ inclusive, comparaison directe sans arrondi), évalué dès que la
  bande candidate est mesurée (n > 0). Rationnel : (1) ferme le vrai trou —
  si baseline ET previous ont une bande vide, le chemin « rien contre quoi
  régresser » laissait passer un candidat à écart ARBITRAIRE (atteignable
  dès qu'un artefact promu à bande vide devient previous ET qu'un rapport
  baseline dégénéré circule) ; (2) cohérence de motif : même architecture
  absolu-plus-relatif que l'ECE ; (3) durcissement assumé : 0.10 est plus
  strict que le plafond relatif hérité (0.1235 + 0.02 = 0.1435) — la
  recalibration de la bande est L'OBJECTIF R5, marge mesurée du candidat
  ml_v05 : écart 0.0093, soit ~10x sous le plafond.
  Les bornes référence+tolérance sont arrondies à 10 décimales : ≤ inclusif
  garanti à la limite exacte (l'addition flottante brute ne l'était pas —
  4,93 % des références à 4 décimales pour tol 0.02, 2,68 % pour tol 0.01 ;
  qa r3/r4). Chacun des 5 sites d'arrondi est tué par mutation testing
  (retirer un round() fait échouer un cas dédié, garde-fou anti-cas-inutile
  inclus — le volet ECE initial utilisait 0.07+0.01, bit-exact en IEEE-754,
  et ne testait rien : attrapé par qa en r4).

## Intégrité de l'évaluation — statut du golden set (R5, ronde 0)

- **Le golden est PARTIELLEMENT BRÛLÉ comme set de sélection** (major eval
  R5 r0, assumé et tracé) : deux choix de conception de v0.5 — la méthode de
  calibration (min conservateur retenu contre température et isotonique
  pleine) et la pondération de la val d'early stopping — ont été tranchés en
  comparant les métriques GOLDEN de ~6 variantes. Les chiffres golden de
  v0.5 (dont l'écart de bande 0,0093) sont donc des estimateurs OPTIMISTES
  (minimum sélectionné sur le set de test). Atténuations vérifiées par le
  panel : toutes les variantes mesurées passaient le gate (le verdict de
  promotion est invariant à la sélection) ; le min conservateur a un
  rationnel produit a priori ; la spec divulguait ces mesures ouvertement.
- **Règles en conséquence** : (1) toute décision FUTURE de méthode de
  calibration/architecture se prend sur une tranche tenue à l'écart ou sur
  données fraîches (télémétrie v1) — plus jamais sur le golden ; (2) les
  bornes cliquet issues de v0.5 (ex. bande previous + tol = 0,0293) se
  traitent avec prudence : un futur candidat qui échoue DE PEU sur une borne
  cliquet héritée d'un chiffre sélectionné mérite un examen humain, pas un
  rejet aveugle (le gate reste la règle ; l'examen est une revue de la borne,
  pas un waiver du candidat).
- **Plafond absolu de bande (7-bis, 0,10) — caractère BILATÉRAL documenté**
  (minor eval r0) : l'écart |justesse − confiance| plafonne aussi la
  SOUS-confiance (direction produit-sûre, coût = un clic) et, à n < 25, le
  bruit binomial peut dépasser 0,10 sans défaut réel. Assumé comme hygiène
  fail-closed d'une action SANS clic ; à réexaminer si un candidat sûr mais
  timide échoue uniquement là-dessus.
- **Val in-sample pour le calibrateur** (minor dq r0) : les métriques VAL
  (ece, bande) du rapport de train sont mesurées sur les données qui ont
  ajusté le calibrateur — indicatives seulement ; l'éval qui fait foi est le
  harnais sur le golden.

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
