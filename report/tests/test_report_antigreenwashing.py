"""Test anti-écoblanchiment (règle n°3, directive UE 2024/825).

Aucun équivalent grand public ne doit apparaître dans le rapport rendu :
ni dans le gabarit, ni injecté par le code. Fourchettes min–max uniquement.
"""

import unicodedata
from pathlib import Path

import generate

# Termes interdits (comparaison insensible à la casse ET aux accents).
TERMES_INTERDITS = [
    "litre",
    "arbre",
    " km",
    "kilometre",
    "equivalent voiture",
    "equivalent co2 voiture",
    "tasse de cafe",
]


def _normaliser(texte: str) -> str:
    """Minuscules + suppression des accents, pour un filtre robuste."""
    decompose = unicodedata.normalize("NFKD", texte.lower())
    return "".join(c for c in decompose if not unicodedata.combining(c))


def test_aucun_equivalent_grand_public_dans_le_rendu(resultats_factices):
    contexte = generate.build_context("demo", "2026-06", resultats_factices)
    html = _normaliser(generate.render_html(contexte))
    for terme in TERMES_INTERDITS:
        assert terme not in html, f"Terme interdit dans le rapport rendu : {terme!r}"


def test_aucun_equivalent_grand_public_dans_le_gabarit_source():
    """Défense en profondeur : le gabarit lui-même est propre, avant rendu."""
    source = _normaliser(
        (Path(generate.TEMPLATES_DIR) / "report.html.j2").read_text(encoding="utf-8")
    )
    for terme in TERMES_INTERDITS:
        assert terme not in source, f"Terme interdit dans le gabarit : {terme!r}"


def test_les_fourchettes_restent_des_fourchettes(resultats_factices):
    """Un chiffre d'impact seul (min == max affiché comme scalaire) est interdit :
    le gabarit affiche toujours « min – max »."""
    contexte = generate.build_context("demo", "2026-06", resultats_factices)
    html = generate.render_html(contexte)
    # Les trois indicateurs d'impact de la synthèse sont bien des intervalles.
    assert html.count("–") >= 3
