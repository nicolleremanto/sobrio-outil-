"""Point d'entrée de la recalibration mensuelle v1, volontairement fail-closed.

Flux prévu, lorsque la télémétrie v1 réelle sera disponible :

1. extraire les exemples admissibles depuis ``events_reco`` ;
2. constituer un jeu tenu à l'écart pour les choix de méthode ;
3. entraîner un candidat avec ``train_v05`` ;
4. soumettre le candidat au gate ;
5. promouvoir avec ``promote`` uniquement après verdict positif.

Intégrité de l'évaluation : le golden figé reste un instrument d'évaluation
et de promotion. Il ne sert JAMAIS à recalibrer, choisir une méthode de
calibration ou une architecture. Ces choix utilisent exclusivement le jeu
tenu à l'écart ou des données fraîches, conformément à la section
« Intégrité de l'évaluation » de ``docs/decisions/ROUTEUR_CLASSIFIEUR.md``.

Ce module ne contient et n'appelle aucune extraction, aucun entraînement,
aucun gate et aucune promotion. Tant que les données réelles n'existent pas,
son unique comportement est le refus opérateur explicite ci-dessous.
"""

from __future__ import annotations

import sys

REFUS_MESSAGE = (
    "REFUS : recalibration impossible — télémétrie v1 requise (aucune donnée réelle disponible)"
)


def main() -> int:
    """Refuse la recalibration avant disponibilité de la télémétrie v1."""
    print(REFUS_MESSAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
