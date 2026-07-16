# RFC-XXXX — <titre court>

> Gabarit de RFC. Toute modification d'un fichier de `contracts/` (openapi.yaml,
> db_schema.sql, model_catalog.yaml) exige une RFC acceptée **et** un incrément de
> version dans `contracts/CHANGELOG.md` (règle n°7).
>
> Nommage : `docs/rfc/RFC-XXXX-titre-court.md`. Statuts : brouillon → en revue →
> acceptée / refusée.

- **Auteur·e :**
- **Date :**
- **Statut :** brouillon

## Motif

Pourquoi ce changement est nécessaire. Problème constaté, contrainte nouvelle,
règle non négociable concernée le cas échéant.

## Impact

Lots touchés (A-F), migrations de données éventuelles, compatibilité ascendante,
effet sur les clients existants (extension déployée, rapports déjà générés).

## Contrats touchés

Liste précise des fichiers de `contracts/` modifiés et nature du changement
(champ ajouté/retiré, contrainte modifiée, nouveau modèle au catalogue, …).

## Version proposée

Incrément à porter dans `contracts/CHANGELOG.md` (ex. v1.0 → v1.1) et résumé de
l'entrée de changelog.

## Alternatives

Options considérées et raisons de leur rejet (y compris « ne rien faire »).

## Décision

Décision finale, date, personnes impliquées. Reporter la décision dans
`docs/decisions.md` une fois la RFC acceptée.
