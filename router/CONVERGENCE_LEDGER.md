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
| R2       | Golden set (juge de paix)                          | 2/2 (r2 & r3) | **CONVERGÉ** |
| R3       | Protocole d'évaluation & harnais + gate            | 0/2           | en cours |
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

---

## R2 — construction + double-revue + arbitrage (ronde 0)

**Génération** (builder-core/sonnet) : `generate_golden.py`, 52 gabarits → 172
entrées, 8 catégories équilibrées (19-25), 73,8 % FR, signaux cohérents par
construction, étiquetage AU FOND (jamais via l'heuristique), reproductible à
l'octet (seed 2026). Diagnostic anti-mimétisme : accord heuristique 72,1 %
(bande saine 70-90, loin du seuil 95 = mimétisme).

**Double-revue INDÉPENDANTE** (parallèle, sans se voir) :
- ml-architect (opus) : 172/172 relues, 2 désaccords (gabarits), verdict
  acceptable_apres_arbitrage. A confirmé indépendamment l'accord 72,1 %.
- eval-scientist (opus) : 172/172 relues, 3 désaccords, verdict
  acceptable_apres_arbitrage. Observations clés : n effectif ≈ 52 gabarits
  (pas 172), cellules opus minces, non-séparabilité étage 1 de 3 cellules
  (la distinction vit dans le TEXTE → argument pour l'étage 2/R6).

**Arbitrage orchestrateur (2/3, ma voix sur les 1-contre-1)** :
- gold-0077..79 traduction juridique officielle : opus→**sonnet** (ml accepté —
  plafond traduction, cohérence interne du set, l'enjeu probant ne monte pas
  de palier).
- gold-0155..57 synthèse fil long : opus→**sonnet** (ml accepté — le volume de
  contexte seul ne fait pas monter de palier, principe enseigné par le set).
- gold-0088..91 architecture complexe : **CONSERVÉ opus** (eval rejeté —
  frontière réelle Sonnet/Opus, conception multi-contraintes au-dessus du dev
  standard ; conserve la couverture opus de la catégorie code).
- gold-0167..69 fil mixte code+maths : opus→**sonnet** (eval accepté — prompt
  et contexte modestes, périmètre Sonnet).
- gold-0044..47 extraction fil très long : **CONSERVÉ haiku** (eval rejeté —
  le golden étiquette la SUFFISANCE du modèle, pas l'UX de bascule ; principe
  anti-volume). NB : ml avait cité ce gabarit en exemple POSITIF.
- AJOUT post-arbitrage : gabarit multi_tours opus HONNÊTE (gold-0173..75,
  preuve profonde en fil long — le fond, pas le volume) : les descentes
  d'arbitrage vidaient sinon la cellule opus de multi_tours. À re-regarder
  par le panel (eval-scientist propriétaire).
- Notes juridiques sans drapeau explicitées (cas réaliste : l'utilisateur ne
  nomme pas le document) — minor ml.

**FIGÉ** : 175 entrées, sha256 dc7e700a…7d58 (`GOLDEN_SHA256`), reviews
tracées par entrée (158 agree/agree · 9 amended · 8 contesté→conservé),
`coverage_report.json` (stats + arbitrages), `HUMAN_REVIEW_WELCOME.md`
(relecture fondateurs non bloquante), test `test_router_golden_frozen.py`
(hash + schéma + zéro prompt_text + ANTI-FUITE router/data/). Accord
heuristique final 69,1 % — le gate R3 a une marge réelle.
Preuves : 90 tests router+api verts, make test complet vert, ruff vert.

## R2 — round 0 (commit 22d4b11)

| agent                | scores                                                          | blocking | major | verdict    |
| -------------------- | --------------------------------------------------------------- | -------- | ----- | ---------- |
| eval-scientist       | étiquettes 4 · représent. 3 · double-revue 3 · figeage 3,5 · gate 3,5 | 0  | 3     | **YELLOW** |
| qa-auditor           | couv 5 · contrat 5 · erreurs 4 · clarté 5 · régressions 5       | 0        | 0     | **GREEN**  |
| data-quality-auditor | dédoublon 3 · équilibre 3 · FR 5 · cohérence 4 · provenance 2   | 0        | 3     | **YELLOW** |
| privacy-sentinel     | 3 violations (citations de formulations utilisateur)            | —        | —     | **FAIL**   |
| cost-guard           | — (zéro dépense)                                                | PASS     | —     | **PASS**   |

→ Ronde **RED** (FAIL sentinel). Les juges ont attrapé — entre autres — DEUX
fautes de L'ORCHESTRATEUR lui-même. Tout corrigé :

- **[FAIL privacy + major data]** 11 notes citaient entre guillemets des
  formulations utilisateur quasi-littérales (« relis ce texte », « rédige
  cette clause », « montre les étapes ») = amorces de prompt. DEUX de ces
  citations venaient de MA correction du minor flags de la double-revue. →
  **corrigé** : notes réécrites en description INDIRECTE, zéro citation.
- **[major eval — INTÉGRITÉ]** La trace de revue de gold-0173..75 (mon ajout
  post-arbitrage) affirmait agree/agree alors que la double-revue n'a JAMAIS
  vu ce gabarit : provenance FABRIQUÉE par le défaut du dataclass. →
  **corrigé** : provenance honnête (« non_soumis: ajout post-arbitrage… » /
  « valide_au_fond_panel_r2_r0… » — eval-scientist a réellement validé le
  fond en ronde 0). Leçon consignée : un défaut de champ ne doit jamais
  pouvoir affirmer une revue qui n'a pas eu lieu.
- **[major eval]** Cellules opus à 1 seul gabarit (pilier fragile) → **corrigé** :
  +2 gabarits opus DISTINCTS (code : bug de concurrence subtil ; multi_tours :
  synthèse de risques croisés juridiques), marqués « non_soumis — à revoir par
  le panel ronde 1 » (provenance honnête) + garde-fou d'équilibre dans
  _valider_gabarits (≥2 gabarits opus en code/multi_tours, catégories 15-32,
  FR>60 %) + LIMITES_STATISTIQUES versionnées dans coverage_report.json
  (n_eff≈gabarits ; opus en AGRÉGÉ/relatif seulement pour le gate R3 ;
  plafond de justesse étage 1 sur cellules non séparables → argument R6).
- **[major eval+qa]** coverage_report.json écrit à la main, non gardé →
  **corrigé** : généré par generate_golden.py (narratif DOUBLE_REVUE +
  limites en constantes versionnées), procédure HUMAN_REVIEW mise à jour.
- **[major data]** gold-0165 : recos_shown=10 > tours utilisateur possibles
  (9 messages) → **corrigé** : plafond recos_shown ≤ ceil(msg_count/2) dans
  le générateur.
- **[minors]** reviews des arbitrages ANCRÉES au label vu (« agree — avait
  relu le label INITIAL opus… ») · test anti-fuite : garde extraite +
  **fixture prouvant le déclenchement** + seuil 200 Mo commenté + dédup
  signaux documentée → R4/R5 · bande d'accord ajustée ~65-90 ·
  ruff format appliqué · pseudo-réplication documentée (limites).

**RE-FIGÉ** : 181 entrées (66 haiku / 85 sonnet / 30 opus), sha e795537a…,
75,1 % FR, accord heuristique 66,8 %, reproductible. Preuves : 91 tests
router+api verts, make test complet vert, ruff check+format verts.

## R2 — round 1 (commit cffc4f0)

| agent                | scores                                                              | blocking | major | verdict   |
| -------------------- | ------------------------------------------------------------------- | -------- | ----- | --------- |
| eval-scientist       | étiquettes 4,5 · représent. 4 · double-revue 4 · figeage 5 · gate 4,5 | 0      | 0     | **GREEN** |
| qa-auditor           | couv 5 · contrat 5 · erreurs 4 · clarté 4 · régressions 5           | 0        | 0     | **GREEN** |
| data-quality-auditor | dédoublon 5 · équilibre 5 · FR 5 · cohérence 5 · provenance 4       | 0        | 0     | **GREEN** |
| privacy-sentinel     | — (scan exhaustif 181 notes + gabarits : zéro citation)             | PASS     | —     | **PASS**  |
| cost-guard           | 1 « violation » : le 175 vs 181 de HUMAN_REVIEW (défaut DOC)        | —        | —     | **FAIL**  |

→ Ronde **ÉCHOUÉE** (FAIL cost-guard, non waivable — appliqué à la lettre).
Note d'orchestration TRANSPARENTE : le motif du FAIL est un défaut documentaire
réel (déjà en minor chez qa et data) mais HORS du mandat coût du garde — toutes
ses preuves de dépense sont vertes (0,00 $). La règle « un FAIL n'est jamais
waivable » s'applique quand même : la ronde échoue, le streak repart de zéro.

ACQUIS MAJEUR de la ronde : eval-scientist a rendu sa REVUE DE FOND FORMELLE
des 3 gabarits opus non_soumis — **tous VALIDÉS AU FOND** (gold-0173..75 preuve
profonde ; gold-0176..78 bug de concurrence, résidu non-séparabilité assumé ;
gold-0179..81 risques croisés juridiques, « le plus solide des trois »).

Corrections avant ronde 2 :
- **corrigé** HUMAN_REVIEW sans chiffre en dur (pointe coverage_stats.json:n) —
  le motif du FAIL.
- **corrigé** reviews mises à jour d'après le verdict RÉEL d'eval ronde 1
  (« valide panel ronde 1 (eval-scientist, contexte neuf) — verdict au
  ledger ») ; ml_architect reste honnêtement « non_soumis — relecture formelle
  au panel ronde 2 » : le panel ronde 2 inclut ml-architect en 6e juge pour
  compléter la symétrie de double-revue des 9 entrées opus.
- **corrigé** résidu d'hygiène : ruff format appliqué aux 3 fichiers R1
  (routes.py, test_router_adapter, test_router_corrections_r1) — repo
  format-clean intégral.

**RE-FIGÉ** : 181 entrées, sha 7782ec5d…, accord heuristique 66,8 %.
Preuves : 91 tests verts, make test complet vert, ruff check+format verts.

## R2 — round 2 (commit c168828, 6 juges — ml-architect complète la double-revue)

| agent                | scores                                                                | blocking | major | verdict   |
| -------------------- | --------------------------------------------------------------------- | -------- | ----- | --------- |
| eval-scientist       | étiquettes 4,5 · représent. 4 · double-revue 4 · figeage 5 · gate 4,5 | 0        | 0     | **GREEN** |
| ml-architect         | plausib. 4,5 · cohérence 5 · ancrage 5 · symétrie 5 · exploit. 4,5    | 0        | 0     | **GREEN** |
| qa-auditor           | couv 5 · contrat 5 · erreurs 5 · clarté 4,5 · régressions 5           | 0        | 0     | **GREEN** |
| data-quality-auditor | dédoublon 5 · équilibre 5 · FR 5 · cohérence 5 · provenance 5         | 0        | 0     | **GREEN** |
| privacy-sentinel     | — (scan programmatique 181 notes+reviews, zéro citation)              | PASS     | —     | **PASS**  |
| cost-guard           | — (mandat coût strict : zéro motif payant, 0,00 $)                    | PASS     | —     | **PASS**  |

→ Ronde **VERTE (1/2)** — nouveau streak. ACQUIS : ml-architect a rendu sa
revue de fond FORMELLE des 9 entrées opus — **les 3 gabarits VALIDÉS AU FOND**
(preuve profonde « ma spécialité » ; bug de concurrence « une des classes de
debug causal les plus dures » ; risques croisés « le plus solide — maintien
SOBRE, current_model déjà opus »). **Symétrie de double-revue COMPLÈTE** sur
les 181 entrées. Balayage anti-régression : ses 2 arbitrages opus→sonnet bien
appliqués, zéro régression, les 30 opus tous ancrés à des moteurs de
profondeur (jamais volume-seul).

Minors polis avant ronde 3 : reviews ml mises à jour d'après son verdict RÉEL
(« valide panel ronde 2 ») + re-figeage sha 6120df28… · commentaires d'en-tête
rafraîchis (qa) · vigilance borne multi_tours 31/32 commentée (eval).

## R2 — round 3 (commit 9a493b5)

| agent                | scores                                                                | blocking | major | verdict   |
| -------------------- | --------------------------------------------------------------------- | -------- | ----- | --------- |
| eval-scientist       | étiquettes 4,5 · représent. 4 · double-revue 4,5 · figeage 5 · gate 4,5 | 0      | 0     | **GREEN** |
| ml-architect         | plausib. 4,5 · cohérence 5 · ancrage 5 · symétrie 5 · exploit. 4,5    | 0        | 0     | **GREEN** |
| qa-auditor           | 5 · 5 · 5 · 5 · 5 (zéro minor)                                        | 0        | 0     | **GREEN** |
| data-quality-auditor | 5 · 5 · 5 · 5 · 5 (zéro minor)                                        | 0        | 0     | **GREEN** |
| privacy-sentinel     | — (12 preuves : reproductibilité byte-à-byte re-vérifiée, scans)      | PASS     | —     | **PASS**  |
| cost-guard           | — (mandat coût strict, zéro motif payant)                             | PASS     | —     | **PASS**  |

→ Ronde **VERTE (2/2 consécutive)** — **CHANTIER R2 CONVERGÉ** (rondes 2 & 3).
Minors résiduels : `make test` transitoirement perturbé par un reset Postgres
pendant le run concurrent des juges → REJOUÉ PROPRE par l'orchestrateur
(141 py + 218 ext verts) ; formulation cosmétique de 2 chaînes review
(optionnel, non retenu).

**Bilan R2 : construction → double-revue indépendante → arbitrage → r0 RED
(FAIL citations + provenance fabriquée par l'orchestrateur + arithmétique) →
r1 échouée (FAIL cost hors mandat, règle appliquée à la lettre) → r2 VERTE →
r3 VERTE.** Le dispositif a attrapé : 11 notes citant des formulations
utilisateur (dont 2 issues d'une correction de l'orchestrateur), une trace de
revue FABRIQUÉE par défaut de champ, recos_shown arithmétiquement impossible,
un rapport de couverture écrit à la main non gardé, des cellules opus
fragiles. Livré : golden.jsonl 181 entrées FIGÉ (sha 6120df28…), double-revue
COMPLÈTE (eval r1 + ml r2, verdicts au ledger), anti-fuite prouvée active,
limites statistiques versionnées, contrainte de gate transmise à R3 (opus en
AGRÉGÉ/relatif seulement). Dépense totale : 0,00 $.
