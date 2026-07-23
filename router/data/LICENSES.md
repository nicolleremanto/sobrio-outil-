# Registre de licences — datasets publics envisagés (§5.5 ROUTEUR_CLASSIFIEUR.md)

**Statut aujourd'hui : AUCUNE source publique n'est utilisée.** Ce registre est
rempli AVANT tout usage (règle stricte, §5.5) — les adaptateurs de
`public_datasets.py` existent pour documenter l'architecture d'activation
future, mais sont ÉTEINTS par défaut (`SOBRIO_ALLOW_DATASET_DOWNLOAD` doit
valoir `"1"`, et même alors ce module n'effectue aucun appel réseau lui-même —
voir la docstring de `public_datasets.py`).

**Méthode** : aucun appel réseau n'a été fait pour vérifier ces informations
(contrainte du chantier R4). Ce qui suit est noté « avec prudence », depuis la
connaissance générale de ces datasets — **à confirmer par une revue licence
explicite avant toute activation**, quelle que soit la formulation ci-dessous.

**Règle de décision** : licence ambiguë, restrictive, ou non vérifiée avec
certitude = **NON UTILISÉ**. Aucune exception.

---

## LMSYS-Chat-1M

- **Description** : ~1M conversations réelles collectées via des déploiements
  de chatbots (Vicuna, Chatbot Arena et autres), publié par LMSYS/UC
  Berkeley, hébergé sur HuggingFace.
- **Licence connue (à confirmer)** : distribué sous un accord d'usage
  spécifique (« LMSYS-Chat-1M Dataset License Agreement »), PAS une licence
  ouverte standard (type MIT/CC-BY) — nécessite typiquement l'acceptation de
  conditions d'usage sur la page HuggingFace avant tout téléchargement, en
  raison de la présence possible de contenu toxique/sensible et de
  préoccupations de confidentialité sur les prompts utilisateurs réels.
- **Restrictions pressenties** : usage recherche mise en avant explicitement
  dans les communications LMSYS ; statut pour usage COMMERCIAL et
  REDISTRIBUTION incertain sans lecture à jour de l'accord exact ; contient
  des textes de prompts RÉELS d'utilisateurs tiers (tension directe avec la
  règle n°1 du projet — Sobrio ne stocke ni ne traite de texte de prompt,
  même en amont d'un pipeline de conversion-signaux, sans base légale
  claire sur ces textes tiers).
- **Verdict : NON UTILISÉ.** Licence non ouverte, restrictions d'usage non
  confirmées, contenu de prompts utilisateurs tiers incompatible par
  défaut avec la posture privacy du projet. À confirmer avant toute
  activation (revue licence explicite + revue légale sur les prompts tiers).

## Chatbot Arena conversations (`lmsys/chatbot_arena_conversations`)

- **Description** : sous-ensemble de conversations d'arène (comparaisons
  A/B entre modèles avec vote humain), publié par LMSYS sur HuggingFace,
  apparenté à LMSYS-Chat-1M mais structuré autour des duels de modèles.
- **Licence connue (à confirmer)** : accord d'usage spécifique également
  (pas une licence ouverte standard confirmée) ; mêmes préoccupations de
  contenu sensible/toxique que LMSYS-Chat-1M, et probablement les mêmes
  conditions d'acceptation préalable sur HuggingFace.
- **Restrictions pressenties** : mêmes réserves que LMSYS-Chat-1M (usage
  recherche mis en avant, statut commercial/redistribution incertain,
  textes de prompts réels de tiers).
- **Verdict : NON UTILISÉ.** Mêmes motifs que LMSYS-Chat-1M. À confirmer
  avant toute activation.

## RouteLLM / données de jugement GPT-4 (`lmsys/RouteLLM`)

- **Description** : jeu de données et code associés au projet de recherche
  RouteLLM (LMSYS), qui entraîne des routeurs à partir de préférences
  Chatbot Arena et de jugements produits par un modèle « juge » (GPT-4).
  Le CODE du dépôt RouteLLM est publié sous licence Apache 2.0 (permissive)
  à notre connaissance ; les DONNÉES sous-jacentes proviennent
  vraisemblablement des mêmes conversations Chatbot Arena que ci-dessus, et
  hériteraient donc de leurs propres restrictions — pas nécessairement de
  la licence Apache 2.0 du code.
- **Restrictions pressenties** : licence du CODE probablement permissive
  (Apache 2.0), mais les DONNÉES d'entraînement (issues de Chatbot Arena)
  restent soumises à l'accord d'usage LMSYS ci-dessus ; les jugements
  produits par un modèle tiers (GPT-4, OpenAI) soulèvent en outre une
  question de CGU du fournisseur du juge (usage des sorties d'un modèle
  tiers pour entraîner un autre modèle) — non vérifiée.
- **Verdict : NON UTILISÉ.** Distinction code/données non tranchée avec
  certitude sans lecture à jour des conditions exactes ; question CGU du
  juge GPT-4 non vérifiée. À confirmer avant toute activation.

## multilingual-e5-small (`intfloat/multilingual-e5-small`)

- **Description** : encodeur de texte multilingue compact (famille E5,
  travaux Microsoft Research, publié par intfloat sur HuggingFace) ;
  produit des embeddings denses (384 dimensions) pour ~100 langues.
- **Licence connue (à confirmer)** : MIT (permissive — usage commercial,
  modification et redistribution permis avec conservation de la notice),
  d'après la fiche modèle HuggingFace telle que connue au moment de cette
  entrée — à confirmer par lecture de la fiche à jour avant activation.
- **Usage prévu** : encodeur de l'étage 2 du routeur (chantier R6) —
  embeddings calculés LOCALEMENT (aucun appel réseau à l'inférence), sous
  les mêmes invariants privacy que l'étage 1 (règle n°1 : aucun texte de
  prompt stocké ni loggé ; le poids du modèle est un artefact local).
- **Restrictions pressenties** : aucune restriction d'usage connue au-delà
  des termes MIT ; le TÉLÉCHARGEMENT initial des poids (HuggingFace) reste
  soumis aux gardes réseau du chantier (`SOBRIO_ALLOW_MODEL_DOWNLOAD` et
  revue préalable) — cette entrée consigne la licence AVANT tout usage,
  conformément à la règle mission.
- **Variante servie (export ONNX int8) — Lot 2 recadré, 2026-07-23** : la
  licence MIT ci-dessus est celle du modèle AMONT (`intfloat/…`) ; la
  variante réellement servie est un export ONNX quantifié int8 dont le dépôt
  EXPORTATEUR (possiblement communautaire, spec §4.3/§4.5) a sa provenance
  et sa licence PROPRES. **Source : À APPROUVER PAR LE FONDATEUR** — le
  PREMIER FETCH du modèle est un **geste fondateur** (décision datée
  2026-07-23) : le choix du dépôt source, la lecture de sa licence, le
  calcul et la consignation des sha256 appartiennent au fondateur, pas à un
  agent. Le manifest committé
  (`router/tools/embed_model_manifest.json`) porte des champs
  `source_repo`/`url`/`sha256` à `null` et
  `router/tools/fetch_embed_model.py` REFUSE toute exécution (« source non
  approuvée : geste fondateur requis », exit 2) tant que ce geste n'a pas eu
  lieu. Après le geste : consigner ici le dépôt exportateur réel + sa
  licence + la date de vérification (miroir du manifest), et poser le
  verdict définitif — UTILISABLE seulement si licence amont (MIT) ET licence
  de l'export toutes deux compatibles usage commercial + redistribution du
  dérivé avec attribution.
- **Verdict : NON UTILISÉ — source de l'export À APPROUVER PAR LE FONDATEUR
  (geste fondateur)**, quelle que soit la formulation ci-dessus. Aucun
  entraînement/bench/promotion tant que le verdict n'est pas UTILISABLE
  (spec §4.5).

---

## Récapitulatif

| Source | Licence (à confirmer) | Verdict |
|---|---|---|
| LMSYS-Chat-1M | Accord d'usage spécifique, pas de licence ouverte standard | **NON UTILISÉ** |
| Chatbot Arena conversations | Accord d'usage spécifique, pas de licence ouverte standard | **NON UTILISÉ** |
| RouteLLM / GPT-4 judge data | Code probablement Apache 2.0 ; données héritant des restrictions Chatbot Arena ; CGU du juge tiers non vérifiées | **NON UTILISÉ** |
| multilingual-e5-small (intfloat) | MIT amont documenté ; licence de l'export ONNX int8 servie : à vérifier au geste fondateur | **NON UTILISÉ — source de l'export À APPROUVER PAR LE FONDATEUR (geste fondateur)** |

Toute activation future exige : (1) une relecture des conditions exactes en
vigueur au moment de l'activation (les accords HuggingFace évoluent), (2) une
revue légale sur le traitement de prompts d'utilisateurs tiers au regard de la
règle n°1 (CLAUDE.md), (3) la mise à jour de ce tableau AVANT tout appel à
`public_datasets.download_*` avec le flag activé.
