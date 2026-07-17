# RFC-0001 — Bloc `signals` avec mémoire de conversation (contrats v1.1)

- **Auteur·e :** équipe extension (Lot A) — bootstrap V0
- **Date :** 2026-07-16
- **Statut :** brouillon

## Motif

La V0 de l'extension implémente une décision produit clé : **la recommandation ne se
fonde pas sur le seul dernier prompt**. Une mémoire locale de signaux de conversation
(nombre de messages, taille de contexte estimée, code/maths/raisonnement vus au fil des
tours, modèle courant, historique recos/dérogations — **jamais le texte**, règle n°1)
évite le routage naïf : un « démontre-le » court dans un fil mathématique ne doit pas
partir sur Haiku.

Le contrat v1.0 (`POST /v1/recommend`) ne connaît que le bloc `features` (prompt seul).
Aujourd'hui : le **mock** de l'extension consomme le bloc complet, le mode **api** mappe
vers `features` v1.0 et la mémoire n'influence pas le routeur serveur. Pour que le
routeur réel bénéficie du contexte, le contrat doit évoluer.

## Impact

- **Lot A (extension)** : déjà prête — `src/signals.ts` produit le bloc proposé ;
  `src/client.ts` supprimera le mapping de compatibilité.
- **Lot B (API)** : accepter `signals` (rétro-compatible : `features` reste accepté en
  v1.x), enrichir `Router.decide()`, ajouter `suggest_new_conversation` à la réponse.
- **Lot D (entrepôt)** : `events_reco.features_json` accueille le bloc `signals`
  (JSONB — pas de migration de schéma, contenu SANS texte inchangé).
- **Lot E (rapport)** : opportunité V1 — taux de suivi par contexte (code/maths).
- **Compatibilité** : ascendante. Une extension v0 (features) continue de fonctionner ;
  une API v1.0 reçoit des features mappées depuis les signaux.

## Contrats touchés

`contracts/openapi.yaml` uniquement :

1. `RecommendRequest` : nouveau champ optionnel `signals` :
   - `signals.prompt` : `char_len`, `token_est`, `lang`, `has_code`, **`has_math`**
     (nouveau), `keyword_flags` — liste fermée étendue à **`demonstration`** ;
   - `signals.conversation` : `msg_count`, `context_token_est`, `seen_code`,
     `seen_math`, `seen_reasoning`, `current_model` (id catalogue ou null),
     `recos_shown`, `recos_followed`, `derogations_up`.
   - Tous les champs sont des nombres, booléens ou valeurs de vocabulaires fermés —
     **aucun texte libre** (règle n°1) ; schéma strict `additionalProperties: false`.
2. `RecommendResponse` : nouveau champ `suggest_new_conversation: bool` (contexte long).
3. Nouveau endpoint léger de santé : `POST /v1/telemetry/health` avec pour seul corps
   `{signal: enum["selector_broken"]}` — alerte sans AUCUNE autre donnée quand les
   sélecteurs claude.ai cassent (détecteur boucle 5). Alternative discutable : champ
   optionnel sur reco_event — rejetée car reco_event est volontairement STRICT.
4. `ExtensionConfig` : nouveau champ `allow_auto_apply: bool` (défaut **false**) —
   permet à l'organisation d'interdire l'application automatique du modèle même si
   l'utilisateur l'a activée localement (amendement règle n°2 du 2026-07-16, voir
   `docs/decisions.md`). Tant que ce champ n'existe pas, l'opt-in est purement local.
5. `ExtensionConfig` : nouveau champ `telemetry_enabled: bool` (défaut **true**) —
   opt-out de télémétrie piloté par l'organisation. L'extension le lit déjà
   défensivement (`telemetryAllowed`) ; absent ⇒ autorisé.

## Version proposée

`contracts/CHANGELOG.md` : **v1.1** — ajout rétro-compatible (`signals`,
`suggest_new_conversation`, flag `demonstration`, endpoint `telemetry/health`).

## Alternatives

- **Ne rien changer** : la mémoire de conversation reste un avantage du mock seul ;
  le routeur serveur route naïvement les prompts courts (contredit la décision produit).
- **Envoyer le texte** : interdit (règle n°1), non négociable.
- **Faire décider l'extension localement** : contredit « toute l'intelligence est côté
  serveur » et empêche l'amélioration continue du routeur.

## Décision

_À trancher en revue d'équipe (Lots A + B). Brouillon posé par le bootstrap V0 ; le code
de l'extension référence cette RFC partout où le mapping de compatibilité v1.0 existe._
