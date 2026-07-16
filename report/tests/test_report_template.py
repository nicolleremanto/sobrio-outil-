"""Tests du gabarit report.html.j2 : HTML valide et libellés exacts (règle n°4)."""

from html.parser import HTMLParser

import generate

# Libellés EXACTS des deux blocs environnementaux (règle n°4) — toute
# modification est un changement de contrat de restitution.
LIBELLE_BLOC_MESURE = "Empreinte totale mesurée (100 % de l'usage)"
LIBELLE_BLOC_EVITE = "Empreinte évitée — périmètre : chat navigateur uniquement"

# Éléments HTML « void » : jamais fermés, à ignorer dans le contrôle d'équilibre.
_VIDES = {"meta", "br", "hr", "img", "link", "input", "col", "wbr", "source", "base"}


class _VerificateurEquilibre(HTMLParser):
    """Vérifie que les balises non-void s'ouvrent et se ferment en ordre."""

    def __init__(self) -> None:
        super().__init__()
        self.pile: list[str] = []
        self.erreurs: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag not in _VIDES:
            self.pile.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in _VIDES:
            return
        if not self.pile or self.pile[-1] != tag:
            self.erreurs.append(f"balise </{tag}> inattendue (pile : {self.pile[-3:]})")
        else:
            self.pile.pop()


def _rendre(resultats_factices: dict) -> str:
    contexte = generate.build_context("demo", "2026-06", resultats_factices)
    return generate.render_html(contexte)


def test_gabarit_rend_un_html_valide(resultats_factices):
    html = _rendre(resultats_factices)
    assert html.lstrip().startswith("<!DOCTYPE html>")
    verif = _VerificateurEquilibre()
    verif.feed(html)
    verif.close()
    assert not verif.erreurs, f"HTML mal équilibré : {verif.erreurs}"
    assert not verif.pile, f"Balises jamais fermées : {verif.pile}"


def test_les_deux_libelles_exacts_sont_presents(resultats_factices):
    """Règle n°4 : les deux blocs distincts existent, avec leur libellé exact."""
    html = _rendre(resultats_factices)
    assert LIBELLE_BLOC_MESURE in html
    assert LIBELLE_BLOC_EVITE in html


def test_les_chiffres_cles_apparaissent(resultats_factices):
    html = _rendre(resultats_factices)
    # Dépense mesurée (USD) et bornes des fourchettes, au format du filtre
    # « nombre » (espace fine insécable U+202F pour les milliers).
    assert generate._filtre_nombre(1842.50, 2) in html  # dépense USD
    assert generate._filtre_nombre(2520) in html  # empreinte mesurée Wh min
    assert generate._filtre_nombre(10845) in html  # empreinte mesurée Wh max
    assert generate._filtre_nombre(1.6, 1) in html  # empreinte évitée Wh min
    assert generate._filtre_nombre(6.4, 1) in html  # empreinte évitée Wh max


def test_echec_propre_si_monthly_agg_vide(resultats_factices):
    """generate doit échouer avec un message clair si le mois est absent."""
    import pytest

    resultats_factices["monthly_total"] = []
    with pytest.raises(SystemExit, match="monthly_agg est vide"):
        generate.build_context("demo", "2026-06", resultats_factices)
