# Rapport final de l'orchestrateur — Routeur IA Sobrio (v0 → v1)

Mission « PROMPT CLAUDE CODE — ROUTEUR IA SOBRIO » menée en boucle de
convergence adversariale (§4) : chaque chantier construit, prouvé par
artefacts, jugé par des panels indépendants à contexte neuf, consigné dans
`router/CONVERGENCE_LEDGER.md` (qui fait foi), jusqu'à 2 rondes vertes
CONSÉCUTIVES (plafond 8). Sortie conforme au §8 du prompt de mission.

## 1. Livré — architecture effective

Classifieur à DEUX étages, sans LLM à l'inférence :
- **Étage 1** (défaut) : LightGBM ml_v05 — 22 features de signaux (jamais le
  texte), split par signature, calibration isotonique conservatrice,
  p95 ≈ 0,05 ms (budget ≤ 5 ms). PROMU : gate PASS 9/9, exactitude pondérée
  0,8978 vs 0,7320 (heuristique), ECE 0,0417, sous-dim 0,0331, bande 0,0093.
- **Étage 2** (opt-in, ÉTEINT) : embeddings e5-small ONNX — infrastructure
  complète et VERROUILLÉE (triple verrou env+policy+texte, plafond de
  confiance 0,74, cascade fail-soft : API 200 même sans modèle, texte en
  mémoire seulement). Le modèle N'EST PAS téléchargé : premier fetch =
  geste fondateur (voir §7).
- **Filets** : SafeRouter (repli heuristique inconditionnel, timeout 50 ms),
  gate de promotion fail-closed à effet cliquet, rotation
  candidate/promoted/previous + rollback, gardes de dérive intégrales,
  robustesse clone-frais prouvée par simulations, RUNBOOK opérateur.
- **Suite** : 673 tests router+api verts + 4 skips légitimes (723 + 4 en
  make test complet avec artefacts locaux ; zéro échec partout) ; format et
  lint verrouillés par make lint ; CI sans réseau, sans flags, sans dépense.

## 2. Bilan des rondes (7 chantiers, tous convergés)

| Chantier | Objet | Rondes consommées | Vertes consécutives |
|---|---|---|---|
| R1 | Socle + v0 heuristique | 4 (r0-r3) | r2 & r3 |
| R2 | Golden set 181 (juge de paix) | 4 (r0-r3) | r2 & r3 |
| R3 | Harnais d'éval + gate | 7 (r0-r6) | r5 & r6 |
| R4 | Corpus 30k démarrage à froid | 6 (r0-r5) | r4 & r5 |
| R5 | Pipeline train + ml_v05 | 6 (r0-r5) | r4 & r5 |
| R6 | Étage 2 embeddings verrouillé | 5 (r0-r4) | r3 & r4 |
| R7 | Recalibration, monitoring, ops | 2 (r0-r1) | r0 & r1 |

Panels archivés dans `router/panels/` (R5-r3 → R7-r1), verdicts
complets par juge. Aucun verdict n'a jamais été fabriqué : quand la
plateforme a bloqué des sentinelles (transitoire, R6-r4), le panel a été
repris jusqu'à obtenir de vrais verdicts.

## 3. Ce que le processus adversarial a attrapé (échantillon des ~25 défauts réels)

- **Intégrité d'évaluation** : golden partiellement brûlé (sélection de
  calibration sur le set de test) — consigné, règles « de peu » quantifiées
  (≤ 0,005 ou ≤ 1 SE), futures décisions sur données tenues à l'écart.
- **Corrections fantômes** (2×) : revendications du ledger sans code
  correspondant — attrapées par les juges, réparées, jurisprudence :
  toute revendication doit se prouver dans les fichiers.
- **Tests qui ne testaient rien** : cas bit-exact, garde tautologique
  (fichier comparé à lui-même), mutants survivants — mutation testing
  systématisé (5/5 sites tués sur le gate).
- **Robustesse clone-frais** : 6 tests dépendant de la machine de référence
  (corpus/lightgbm absents → faux négatifs) — gardes + simulations.
- **Privacy** : formulations quasi-prompt dans le ledger (purgées, règle
  « rien qui RESSEMBLE à un prompt, même inventé ») ; chemins d'erreur API
  422/500 échoïsant le texte (caviardage structurel + no-leak E2E).
- **Fautes de l'orchestrateur lui-même, consignées sans fard** : bytecode
  mutant résiduel (pyc même-seconde/même-taille → ronde ROUGE méritée,
  règle durcie : mutations en copie tmp uniquement) ; libellés de commit
  dépassant le périmètre livré (rectifiés) ; NameError sur édition inline.

## 4. Incidents & règles durcies

- `rm -rf` d'un juge sur artefacts locaux (R6-r0) : dégâts nuls
  (déterminisme re-prouvé — sha bit-identiques), interdiction explicite de
  suppression ajoutée aux mandats.
- Bytecode mutant servi par la machine (R6-r2) : FAIL privacy légitime,
  purge + règle « le code qui tourne est le code jugé ».
- Blocages du classificateur de sécurité : téléchargement de modèle par un
  agent (entériné → geste fondateur) ; exécution codex non supervisée
  (résolu par validation fondateur explicite du mode).
- Daemon Docker zombie de 6 jours (recyclé) ; disque plein (nettoyé,
  5,1 Gi libérés) — consignés au RUNBOOK.

## 5. Dépense

**0,00 $ d'API payante sur toute la mission** (7 chantiers, ~30 panels et
vérifications). Les seuls coûts sont les abonnements existants (Claude,
puis ChatGPT pour les builders codex à partir de R7 — décision fondateur
2026-07-24). La CI ne dépense jamais ; tout appel payant est dry-run par
défaut derrière SOBRIO_ALLOW_PAID_CALLS=1 + cap 20 $ fail-closed.

## 6. Résidus TODO (aucun FAIL sentinelle — tous consignés)

- **TODO(V1)** : tête d'étage 2 réelle + recalibration mensuelle sur
  télémétrie v1 (outillage livré, refuse tant que les données n'existent
  pas) ; chiffrer l'impact du bruit 3 % du corpus ; choix int8 vs fp32 sur
  données réelles ; retrait éventuel du plafond 0,74.
- **TODO(V2)** : observabilité fine des replis dans `rule` ; rootdir pytest
  cosmétique.
- **Conditionnels** : adaptateur features→signals (à l'adoption RFC-0001) ;
  revue humaine de LICENSES.md AVANT toute activation des adaptateurs
  datasets (statut : NON UTILISÉ ×3).

## 7. LES 4 GESTES FONDATEURS (seules décisions qui vous appartiennent)

1. **Revue humaine du golden set** — `router/eval/golden/HUMAN_REVIEW_WELCOME.md`.
   181 exemples, ~30 min. Non bloquant mais recommandé : le golden est le
   juge de paix de toutes les promotions.
2. **Décision distillation** — l'étiquetage teacher du corpus coûterait
   ~59,90 $ (re-mesuré), au-dessus du cap de 20 $. Options : teacher moins
   cher, sous-échantillon ≤ 20 $, relever le cap, ou renoncer (le corpus
   synthétique actuel suffit au v0.5). Le client API n'est livré qu'avec
   cette décision. Commande : `make router-distill-dry-run` pour re-chiffrer.
3. **Choix des orgs canary** — l'activation de ml_v05 (et plus tard
   embed_v0) se fait org par org via `policy_json.router_version` (défaut :
   heuristique). Désigner 1-2 orgs pilotes ; procédure au RUNBOOK.
4. **Premier fetch du modèle e5 (étage 2)** — décision entérinée : aucun
   agent ne choisit la source. Pas à pas complet au
   `router/RUNBOOK.md` § « Geste fondateur » : approuver le dépôt
   exportateur de l'ONNX int8 → renseigner manifest + littéraux + pin
   (le test croisé force la cohérence) → `make router-embed-model` →
   spike max_tokens → `make router-embed-bench` (p95 ≤ 30 ms, RSS < 1 Go)
   → verdict licence dans LICENSES.md → activation canary.

## 8. Régimes d'orchestration (traçabilité)

- R1→R4 : panels multi-modèles puis directive « tout Fable » (2026-07-18).
- R5→R6 : 100 % claude-fable-5 (vérifié transcripts), frontmatter agents
  en `inherit`.
- R7+ : régime codex/Opus (décision fondateur 2026-07-24) — builders GPT
  via codex exec supervisé, vérifieurs/juges Opus, orchestrateur sans
  écriture de code, graphe graphify pour chercher (jamais pour prouver).

*Rapport rédigé par l'orchestrateur (Claude) le 2026-07-24. Le ledger
`router/CONVERGENCE_LEDGER.md` et les archives `router/panels/` font foi.*
