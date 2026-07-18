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
| R1       | Socle du routeur & v0 heuristique branchée         | 2/2 (r2 & r3) | **CONVERGÉ** |
| R2       | Golden set (juge de paix)                          | 0/2           | en cours |
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

## R1 — round 1 (commit 93bdd97)

| agent            | scores                                                            | blocking | major | verdict    |
| ---------------- | ----------------------------------------------------------------- | -------- | ----- | ---------- |
| qa-auditor       | couv 3 · contrat 4 · erreurs 2 · clarté 4 · régressions 5         | 0        | 1     | **YELLOW** |
| ml-architect     | règles 4,5 · seuils 4 · interface 4,5 · repli-ml 3,5 · explic 4,5 | 0        | 1     | **YELLOW** |
| privacy-sentinel | 1 violation REPRODUITE (repr/str)                                 | —        | —     | **FAIL**   |
| cost-guard       | — (17 preuves, zéro dépense)                                      | PASS     | —     | **PASS**   |

→ Ronde **RED** (FAIL sentinel, non waivable). Les juges ont trouvé des trous
DANS MES CORRECTIONS de la ronde 0 — tous reproduits par exécution, tous
corrigés :

- **[FAIL privacy]** `PromptSignals.prompt_text` (champ réservé r0) sortait en
  clair dans `repr()`/`str()` du dataclass (reproduit avec SECRET_LEAK_TEST) :
  un log de debug/exception sérialiserait le prompt dès que l'étage 2
  l'alimentera — en contradiction avec le contrat documenté SUR la classe. →
  **corrigé** `field(default=None, repr=False)` + test (repr/str/f-string de
  PromptSignals ET Signals sans le texte ; champ lisible en accès direct).
- **[major qa]** `_validated` ne validait pas `rule` : `rule=None` transmis →
  500 pydantic REPRODUIT via TestClient. → **corrigé** : rule doit être une
  chaîne non vide, sinon repli + 3 tests (None/int/vide).
- **[major ml]** confiance ±inf et bool passaient le filtre NaN (`inf` clampé
  à 1.0 avec rule primaire conservée = artefact corrompu maquillé en décision
  sûre, danger seuil auto 0.75). → **corrigé** `math.isfinite` + exclusion
  bool + 3 tests (+inf/-inf/True).
- **[minor ml]** borne contexte : `> 4000` laissait le point 4000 filer sur
  default_balanced alors que l'invariant annoncé disait `>= 4000`. →
  **corrigé** borne inclusive en miroir exact du `< 4000` des règles légères
  + test au point de couture.

Preuves après correction : 86 tests router+api verts (+8), make test complet
vert, ruff/lint verts, bench p95 0,0115 ms.

## R1 — round 2 (commit 05446ec)

| agent            | scores                                                              | blocking | major | verdict   |
| ---------------- | ------------------------------------------------------------------- | -------- | ----- | --------- |
| qa-auditor       | couv 4 · contrat 5 · erreurs 5 · clarté 4 · régressions 5           | 0        | 0     | **GREEN** |
| ml-architect     | règles 4,5 · seuils 5 · interface 4,5 · repli-ml 4,5 · explic 4,5   | 0        | 0     | **GREEN** |
| privacy-sentinel | — (protocole SECRET_LEAK re-reproduit : repr/str/f-string/traceback) | PASS     | —     | **PASS**  |
| cost-guard       | — (12 preuves, zéro dépense)                                        | PASS     | —     | **PASS**  |

→ Ronde **VERTE (1/2)** — 1re du streak. Minors polis avant la ronde 3 :

- **corrigé** test end-to-end API du primaire corrompu (qa) : monkeypatch d'un
  primaire SAIN à la construction renvoyant Decision corrompue (rule=None,
  conf=inf, modèle fable) → 200 + fallback:heuristic — le chemin complet
  bridge→SafeRouter→pydantic est verrouillé (le juge l'avait reproduit 6/6).
- **corrigé** symétrie bool : confidence=False testée (comme True) → repli.
- **corrigé** commentaire obsolète (référence test_router_catalog.py).
- **RÉSIDU DOCUMENTÉ (privacy, à surveiller en R6)** : `dataclasses.asdict/
  astuple/vars()` exposent `prompt_text` (repr=False ne protège que
  repr/str/f-string). AUCUN code de production n'appelle ces fonctions sur
  les signaux (grep vérifié par le sentinel) et le champ vaut toujours None
  en v0. EXIGENCE R6 : le panel étage 2 devra vérifier qu'aucun chemin
  n'introduit asdict/astuple/pickle sur PromptSignals/Signals.

## R1 — round 3 (commit b5afd27)

| agent            | scores                                                            | blocking | major | verdict   |
| ---------------- | ----------------------------------------------------------------- | -------- | ----- | --------- |
| qa-auditor       | couv 5 · contrat 5 · erreurs 5 · clarté 5 · régressions 5         | 0        | 0     | **GREEN** |
| ml-architect     | règles 4,5 · seuils 5 · interface 4,5 · repli-ml 4,5 · explic 4,5 | 0        | 0     | **GREEN** |
| privacy-sentinel | — (16 preuves, protocole complet re-déroulé, sentinelle fraîche)  | PASS     | —     | **PASS**  |
| cost-guard       | — (18 preuves, zéro dépense)                                      | PASS     | —     | **PASS**  |

→ Ronde **VERTE (2/2 consécutive)** — **CHANTIER R1 CONVERGÉ** (rondes 2 & 3).
Zéro minor résiduel aux deux juges notés. Note d'orchestration : l'agent
cost-guard de la ronde 3 a d'abord échoué sur une erreur TECHNIQUE transitoire
(classifieur) — panel repris (resume, 3 verdicts servis du cache), verdict
cost-guard AUTHENTIQUE obtenu au second passage ; aucun verdict n'a été
fabriqué.

**Bilan R1 : r0 YELLOW (2 majors ml) → r1 RED (FAIL privacy repr + 2 majors)
→ r2 VERTE → r3 VERTE.** Le dispositif a attrapé : validation absente de la
sortie du primaire (500 pydantic), échec au chargement contournant SafeRouter,
transformations légères longues → Opus, bande morte 800, fuite repr() du champ
réservé prompt_text, rule=None → 500, ±inf/bool maquillés en confiance saine,
couture à 4000. Aucune dépense (0,00 $) sur tout le chantier.
