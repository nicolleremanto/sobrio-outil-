# Runbook du routeur Sobrio

Ce document est la référence opérateur des deux étages du routeur. Toutes les
commandes ci-dessous sont des cibles du `Makefile` racine et se lancent depuis
la racine du monorepo.

## Étage 1 — déploiement et rollback

1. `make router-train` entraîne le candidat v0.5 depuis le corpus de référence
   et écrit l'artefact dans `router/artifacts/models/candidate/`.
2. `make router-gate` régénère les évaluations de l'heuristique et du candidat,
   puis exécute le gate. Le rapport du modèle promu est injecté comme référence
   précédente lorsqu'il existe. Cette commande ne promeut rien.
3. `make router-promote` rejoue lui-même des évaluations et le gate frais,
   vérifie l'absence de repli heuristique pendant l'évaluation ainsi que
   l'intégrité de l'artefact, puis copie le candidat vers `promoted/`. L'ancien
   `promoted/` devient `previous/`.
4. Après une promotion, appeler
   `api.app.router_bridge.reinitialiser_routeurs()` depuis le geste interne de
   déploiement. Les requêtes en cours terminent avec leur instance ; les
   résolutions suivantes rechargent les artefacts.

En cas de régression, `make router-rollback` échange `promoted/` et `previous/`
après contrôle d'intégrité. Appeler ensuite la même fonction de
réinitialisation du bridge. Un seul niveau d'historique est conservé.

## Étage 2 — déploiement et rollback

L'étage 2 est désactivé par défaut et son artefact synthétique ne doit pas être
promu en production.

- `make router-embed-model` autorise explicitement, pour cette cible seulement,
  la récupération de la variante int8 décrite par le manifest. Avant le geste
  fondateur, la commande refuse avec le code 2.
- `make router-embed-train` entraîne la tête v0 synthétique et écrit le
  candidat dans `router/artifacts/embed/heads/candidate/`. Ce candidat sert
  uniquement à la mécanique de staging.
- `make router-embed-eval` évalue la tête `prior` par défaut sur les fixtures
  figées et écrit son rapport sous `router/artifacts/eval/`.
- `make router-embed-gate` régénère les évaluations `prior` et
  `head_candidate`, puis applique le gate avec le budget étage 2 de 30 ms et
  la référence précédente lorsqu'elle existe. Cette commande ne promeut rien.
- `make router-embed-bench` mesure le pipeline complet et écrit
  `router/artifacts/bench/embed-latest.json`. Avant le geste fondateur, la commande refuse avec le code 2. La preuve doit porter le sha256
  de l'encodeur courant, avec un p95 inférieur ou égal à 30 ms et un pic RSS
  strictement inférieur à 1 024 Mo.
- `make router-embed-promote` rejoue le gate frais, contrôle la contamination,
  la preuve de bench et l'intégrité, puis fait la rotation
  `candidate/` → `promoted/` → `previous/`. Avant le geste fondateur, cette
  cible refuse avec le code 2.
- `make router-embed-rollback` échange les têtes `promoted/` et `previous/`
  après contrôle d'intégrité.

Après toute promotion ou tout rollback de l'étage 2, appeler
`api.app.router_bridge.reinitialiser_routeurs()` comme pour l'étage 1.

## Geste fondateur de l'encodeur int8

Le premier export ONNX int8 est une décision humaine et atomique :

1. Approuver le dépôt source de l'export et vérifier sa licence, sa provenance
   et les octets attendus.
2. Renseigner la variante `int8` de
   `router/tools/embed_model_manifest.json` : `source_repo`, licence, date de
   vérification et, pour `model.onnx` et `tokenizer.json`, `url`, `sha256` et
   `size_bytes`.
3. Reporter les deux sha256 dans les littéraux `_ENCODER_SHA256` et
   `_TOKENIZER_SHA256` de `router/sobrio_router/embed.py`.
4. Mettre à jour le pin littéral intégral
   `test_embed_spec_pin_litteral_integral` dans
   `router/tests/test_router_embed.py`. Le test croisé
   `test_croise_litteraux_embed_spec_egaux_au_manifest_int8` échoue si le
   manifest et les littéraux ne sont pas renseignés ensemble.
5. `make router-embed-model` récupère et vérifie la variante int8 approuvée.
6. Réaliser le spike `max_tokens` sur des charges représentatives, sans
   persistance de texte. Comparer au minimum 256, 192 et 128 tokens. Si la
   valeur change, mettre à jour le spec, son pin intégral et sa version dans
   le même mouvement.
7. `make router-embed-bench` produit la preuve réelle : p95 ≤ 30 ms, borne
   inclusive, et RSS < 1 024 Mo, borne stricte.
8. Consigner le verdict définitif de licence dans
   `router/data/LICENSES.md` avant tout usage au-delà du fetch de vérification.
9. Activer ensuite le canary organisation par organisation. Les trois verrous
   doivent être explicites : environnement serveur `SOBRIO_EMBED_STAGE2=1`,
   politique `router_version="embed_v0"` et `send_prompt_text=true`. Surveiller
   avant d'élargir ; un verrou absent maintient l'étage 1.

## Recalibration mensuelle v1

Le flux cible est : extraction de la télémétrie réelle `events_reco` →
constitution d'un jeu tenu à l'écart → entraînement par `train_v05` → gate →
promotion par `promote`.

Le golden figé ne sert jamais à la recalibration ni au choix d'une méthode ou
d'une architecture. Il reste réservé à l'évaluation et au gate de promotion.

`make router-recalibrate` documente ce point d'entrée mais refuse aujourd'hui
avec le code 2, car aucune télémétrie v1 réelle admissible n'est disponible. Il
n'extrait, n'entraîne, n'évalue et ne promeut rien.

## Monitoring et seuils

Les rapports du harnais font foi pour :

- l'exactitude pondérée
  `1 − (2 × sous-dimensionnements + sur-dimensionnements) / (2 × n)` ;
- l'ECE global ;
- la calibration de la bande d'auto-bascule, définie par une confiance
  supérieure ou égale à 0,75 ;
- le taux global de sous-dimensionnement et la latence p95.

Le gate est fail-closed dès qu'un critère échoue :

- exactitude pondérée strictement supérieure à l'heuristique et supérieure ou
  égale au modèle précédent ;
- ECE ≤ 0,10 et non-régression face à chaque référence mesurée, avec une
  tolérance de 0,01 ;
- sous-dimensionnement non régressif face à la meilleure référence, avec une
  tolérance de 0,02 ;
- écart de calibration dans la bande auto ≤ 0,10 et non régressif face aux
  références à bande non vide, avec une tolérance de 0,02 ;
- p95 ≤ 5 ms pour l'étage 1 et p95 ≤ 30 ms pour l'étage 2, bornes inclusives ;
- hash du golden égal au hash canonique.

Vigilance spécifique : mesurer le sous-dimensionnement **dans** la bande auto,
pas seulement le taux global. La valeur actuelle est 0,8 %. Toute hausse va
dans la direction dangereuse, car elle touche les décisions appliquées sans
clic : déclencher une alerte et suspendre l'élargissement du canary.

## Incidents connus

### Caches bytecode

Un fichier `.pyc` fondé sur le mtime et la taille peut rester considéré comme
valide après une mutation de source dans la même seconde et à taille
identique. Toute mutation de preuve doit donc être réalisée sur une copie
temporaire. Au moindre doute, purger les répertoires `__pycache__` concernés
avant de rejouer la preuve.

Le conteneur API a déjà écrit des `.pyc` dans l'arbre monté. Le compose pose
désormais `PYTHONDONTWRITEBYTECODE=1` pour empêcher cette écriture.

### Postgres

Un flake de connexion Postgres peut être transitoire. Recycler le conteneur
Postgres, attendre son état sain, puis rejouer le test concerné. Ne modifier
ni les seuils ni le code applicatif pour masquer ce flake.

### Artefact promu mais routeur inchangé

Le bridge mémorise les routeurs. Après une promotion ou un rollback, appeler
`api.app.router_bridge.reinitialiser_routeurs()` depuis le geste interne de
déploiement. Sans cette purge, le processus peut continuer à servir l'instance
construite avant la rotation des artefacts.

## Caps de dépense

Tout appel payant est en dry-run par défaut. Un chemin réel exige
simultanément `SOBRIO_ALLOW_PAID_CALLS=1` et un
`SOBRIO_MAX_SPEND_USD` fini, strictement positif ; sa valeur par défaut est
20 USD. Un flag absent, différent de `1`, un cap invalide ou un dépassement
doit refuser avant tout appel. La CI ne pose jamais l'autorisation et ne
dépense jamais.
