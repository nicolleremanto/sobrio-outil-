# ops/ — exploitation et sécurité (Lot F)

Squelette d'exploitation de Sobrio. `docker-compose.prod.yml` est un **gabarit
commenté**, non utilisable en l'état : les choix d'hébergeur, de reverse proxy et
de sauvegarde restent à faire (marqueurs `TODO(LotF)`).

## Notes de sécurité

### Clé d'administration Anthropic = actif critique (règle n°5)

- Anthropic n'offre pas de permission fine : cette clé lit **tout** le compte
  (Usage & Cost, Analytics, organisation). Elle doit être traitée comme un
  secret de plus haut niveau.
- Lue depuis l'environnement uniquement (`ANTHROPIC_ADMIN_KEY`). Jamais commitée,
  jamais loggée, jamais dans une image Docker, jamais dans le bundle de l'extension.
- **Rotation** : procédure à documenter et tester — génération d'une nouvelle clé
  dans la console Anthropic, mise à jour du secret côté hébergeur, révocation de
  l'ancienne, vérification d'un `sync` complet. TODO(LotF) : cadence (90 jours
  proposés) et responsable.
- Le connecteur est **en lecture seule** : aucune écriture, aucune action
  d'administration ne doit jamais être ajoutée sans RFC.

### Aucun contenu de prompt, nulle part (règle n°1)

- Ni en base, ni dans les logs applicatifs, ni dans les traces du reverse proxy
  (ne pas logger les corps de requêtes), ni dans les événements d'erreur.
- **Scrubbing Sentry à configurer — TODO(LotF)** : avant toute activation de
  Sentry, configurer le filtrage (`before_send`) pour supprimer corps de
  requêtes, champs `prompt_text` et en-têtes d'autorisation. Sans scrubbing
  vérifié par un test, pas de Sentry.

### Sauvegardes Postgres

- TODO(LotF) : `pg_dump` planifié (quotidien proposé) + rétention, ou snapshots
  de volume selon l'hébergeur ; chiffrement des sauvegardes ; **test de
  restauration** régulier documenté.
- L'entrepôt ne contient que des métadonnées (tokens, coûts, pseudonymes salés) —
  jamais de contenu de prompt. Cela reste une base à protéger (données de
  facturation d'entreprise).

### Kill-switch de l'extension

- L'extension interroge `GET /v1/extension/config` : le champ `enabled: false`
  désactive la recommandation à distance pour toute l'organisation, sans
  redéploiement. C'est le mécanisme d'urgence si un comportement inattendu est
  observé sur claude.ai (changement de DOM, incident).
- TODO(LotF) : procédure d'activation du kill-switch (qui, comment, délai de
  propagation lié au cache de configuration de l'extension).

### Aucune promesse de temps réel (règle n°6)

- Les données d'usage/coût Anthropic se rafraîchissent en ~4-24 h et se
  réconcilient jusqu'à J+30. Aucun tableau de bord ni engagement contractuel ne
  doit laisser croire à du temps réel. Le rapport mensuel est produit à J+10 du
  mois suivant.

### Exposition réseau

- Seul le reverse proxy TLS publie des ports (80/443). API et Postgres restent
  sur le réseau interne. Pas de ports de debug en production.
- TODO(LotF) : limitation de débit sur `/v1/*`, en-têtes de sécurité, HSTS.
