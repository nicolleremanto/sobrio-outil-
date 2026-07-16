"""STUB — enregistrement de VRAIES réponses de l'API d'administration Anthropic.

État Lot 0 : ce script ne fait AUCUN appel réseau. Il vérifie seulement les
préconditions et documente la marche à suivre. La logique d'enregistrement est
volontairement laissée au Lot C.

Préconditions (règle n°5 — la clé admin est un ACTIF CRITIQUE) :
- `ANTHROPIC_ADMIN_KEY` lue depuis l'environnement UNIQUEMENT ; le script
  refuse de tourner si elle est absente ;
- la clé n'est jamais écrite : ni dans les fichiers produits, ni dans les logs,
  ni dans les messages d'erreur.

Précaution supplémentaire (règle n°1) : les emails retournés par l'API
Analytics sont ANONYMISÉS AVANT toute écriture sur disque — aucune donnée
personnelle réelle ne doit atterrir dans fixtures/.

TODO(LotC) :
1. appeler les vrais endpoints (usage_report/messages, cost_report, analytics)
   via `connector.client.AnthropicAdminClient` ;
2. paginer (has_more/next_page) et découper en fichiers `<prefixe>_pN.json` ;
3. anonymiser les emails AVANT écriture (`_anonymize_email` ci-dessous) et
   passer un détecteur d'emails sur le JSON final (échec = rien n'est écrit) ;
4. écrire les JSON dans fixtures/anthropic/ (mêmes noms que les synthétiques).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parent / "anthropic"


def _anonymize_email(email: str, index: int) -> str:
    """Remplace un email réel par un email synthétique stable dans le fichier.

    TODO(LotC) : garder un mapping cohérent au sein d'un même enregistrement
    (même personne => même alias) sans jamais écrire le mapping sur disque.
    """
    del email  # l'email réel ne doit servir à rien d'autre
    return f"user{index:02d}@exemple-client.eu"


def main() -> int:
    if not os.environ.get("ANTHROPIC_ADMIN_KEY"):
        print(
            "ERREUR : ANTHROPIC_ADMIN_KEY absente de l'environnement.\n"
            "Ce script lit la clé d'administration depuis l'environnement "
            "UNIQUEMENT (règle n°5 : jamais commitée, jamais loggée).\n"
            "Pour développer sans clé, utiliser les fixtures synthétiques "
            "existantes (mode --fixtures du connecteur).",
            file=sys.stderr,
        )
        return 2

    # TODO(LotC) : implémenter l'enregistrement réel (voir docstring du module).
    print(
        "Enregistrement non implémenté (Lot 0) : aucun appel réseau effectué.\n"
        f"Cible d'écriture prévue : {OUTPUT_DIR}\n"
        "Voir TODO(LotC) dans fixtures/record_fixtures.py.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
