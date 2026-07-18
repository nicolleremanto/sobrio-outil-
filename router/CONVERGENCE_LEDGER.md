# Journal de convergence — Routeur IA Sobrio (v0 → v1)

> Chef d'orchestre : CONSTRUIRE (builders) → PROUVER (artefacts frais : tests, benchs,
> rapports d'éval JSON) → JUGER (agents INDÉPENDANTS à contexte neuf, en parallèle) →
> CONSIGNER → DÉCIDER. Convergence d'un chantier = **2 rondes vertes consécutives**.
> Plafond 8 rondes. Un FAIL de `privacy-sentinel` OU de `cost-guard` fait échouer la
> ronde et n'est JAMAIS waivable.

## Équipe & politique de modèles (méta-principe : le modèle le moins puissant qui suffit)

| Agent | Rôle | Modèle |
| --- | --- | --- |
| orchestrateur (thread principal) | planifie, découpe, dispatche, agrège, décide | inherit (fable) |
| builder-core | code non trivial (routeur, pipeline, serving) | sonnet |
| builder-mech | boilerplate, fixtures, scripts, conversions | haiku |
| ml-architect | revue ML : features, fuites, calibration, seuils | opus |
| eval-scientist | protocole d'éval, golden set, gate de promotion | opus |
| qa-auditor | code, tests, contrat, non-régressions | sonnet |
| privacy-sentinel | PASS/FAIL non waivable — zéro texte stocké/loggé | sonnet |
| cost-guard | PASS/FAIL non waivable — zéro dépense hors mode autorisé | haiku |
| data-quality-auditor | corpus : doublons, équilibre, FR, licences | sonnet |
| redteam-robustness | casse : signaux malformés, artefacts, timeouts, charge | sonnet |
| perf-auditor | mesure : latences p50/p95, RAM, tailles | sonnet |
| docs-scribe | README, runbook, decisions.md, docstrings | haiku |

Escalade ponctuelle : un agent léger qui échoue 2 fois monte d'un cran (noté ici), puis redescend.

## Budgets (§7)

Étage 1 p95 < 5 ms CPU · Étage 2 p95 < 30 ms CPU · `/v1/recommend` p95 < 150 ms ·
RAM < 1 Go · artefacts : étage 1 < 20 Mo, étage 2 < 500 Mo · dépense API : 0,00 $.

---

## État des chantiers

| Chantier | Sujet                                              | Rondes vertes | Statut  |
| -------- | -------------------------------------------------- | ------------- | ------- |
| R1       | Socle du routeur & v0 heuristique branchée         | 0/2           | en cours |
| R2       | Golden set (juge de paix)                          | 0/2           | à venir |
| R3       | Protocole d'évaluation & harnais + gate            | 0/2           | à venir |
| R4       | Corpus de démarrage à froid                        | 0/2           | à venir |
| R5       | Pipeline d'entraînement & classifieur v0.5         | 0/2           | à venir |
| R6       | Étage 2 embeddings (construit, ÉTEINT par défaut)  | 0/2           | à venir |
| R7       | Recalibration, monitoring & déploiement VPS        | 0/2           | à venir |

---

## Décisions d'orchestration (datées)

- **2026-07-18** — Le doc `ROUTEUR_CLASSIFIEUR.md` n'existait pas dans le repo : matérialisé
  dans `docs/decisions/ROUTEUR_CLASSIFIEUR.md` depuis le cadrage fondateur (architecture
  2 étages sans LLM). Le cadrage collé fait foi.
- **2026-07-18** — Contrat `/v1/recommend` INCHANGÉ (hors périmètre) : l'API accepte
  `features` v1.x ; le routeur consomme le bloc riche `signals` (RFC-0001) via un
  **adaptateur features→signals** (champs conversation neutres) — même patron que
  l'extension (`client.ts` mappe signals→features). Le jour où la RFC-0001 est adoptée,
  seul l'adaptateur saute.
- **2026-07-18** — Disque poste dev ~4 Gi libres ⇒ étage 2 SANS torch : ONNX pré-exporté
  téléchargé derrière flag, `onnxruntime`+`tokenizers` seuls, fixtures en CI.

---

## R1 — round 0 (commit 14cd884, construction builder-core/sonnet)

| agent            | scores                                                          | blocking | major | verdict    |
| ---------------- | --------------------------------------------------------------- | -------- | ----- | ---------- |
| qa-auditor       | couv 5 · contrat 5 · erreurs 5 · clarté 4 · régressions 5       | 0        | 0     | **GREEN**  |
| ml-architect     | règles 3,5 · seuils 3,5 · interface 3,5 · repli-ml 3 · explic 4 | 0        | 2     | **YELLOW** |
| privacy-sentinel | — (preuves : greps logs, bench numérique, events_reco features) | PASS     | —     | **PASS**   |
| cost-guard       | — (preuves : zéro motif réseau/API, deps=[], CI sans dépense)   | PASS     | —     | **PASS**   |

→ Ronde **YELLOW**. ml-architect (opus) a trouvé 2 majors réels que la
construction n'avait pas vus — corrigés par l'orchestrateur (correctifs
chirurgicaux spécifiés par les juges, arbitrage consigné) :

- **[major ml]** SafeRouter incomplet pour son propre scénario (§5.2) :
  (a) sortie du primaire NON validée (modèle hors catalogue / confiance 1.7
  → 500 pydantic) → **corrigé** : validation dans SafeRouter (ids visibles du
  catalogue via `VISIBLE_MODELS`, fable exclu, confiance finie clampée [0,1],
  NaN ⇒ repli) ; (b) échec au CHARGEMENT (artefact ML, `__init__`) contournait
  le SafeRouter via le lru_cache du bridge → **corrigé** : garde de
  construction ⇒ `SafeRouter(primary=None)` = repli direct marqué
  `fallback:heuristic` + test API (monkeypatch constructeur explosif → 200).
- **[major ml]** Transformations légères LONGUES → Opus (anti-guide, anti-
  sobriété) + bande morte à 800 → **corrigé** : `light_transform` ≤ 800 →
  Haiku ; nouvelle règle `light_transform_long` > 800 → PLAFOND Sonnet ;
  flag lourd simultané (« résume ce contrat ») → complex_task ; contexte
  ≥ 4000 → complex_task. Continuité testée au seuil.
- **[minors corrigés]** pièce jointe → drapeau lourd `analyse` (adaptateur) ·
  `prompt_text` réservé/documenté sur PromptSignals (étage 2 R6, contrat
  d'usage strict, inerte v0 + tests) · test ids ↔ catalogue yaml ·
  router/README.md + README racine · tests router_version mal typé (42/null).
- **[minors assumés/documentés]** reasoning_context DORMANTE côté serveur tant
  que RFC-0001 non adoptée (argument POUR la RFC, commenté dans l'adaptateur) ·
  confiance 0.75 = seuil auto extension : VOULU (commenté) · `rule` de repli
  figé `fallback:heuristic` (observabilité fine TODO V2) · rootdir pytest
  cosmétique (TODO V2).

Preuves après correction : 78 tests router+api verts (+18), make test complet
vert (128 py + 218 ext), ruff/lint verts, bench p95 0,0108 ms.
