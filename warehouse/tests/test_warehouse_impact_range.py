"""Tests STRUCTURELS de la règle n°3 : tout chiffre d'impact est un Range min-max.

Ces tests verrouillent le contrat du module d'impact : quiconque tente de
faire retourner un scalaire à ``estimate()`` (ou de rendre ``Range``
convertible en nombre) casse cette suite.
"""

from __future__ import annotations

import typing

import pytest

from sobrio_impact import Range, catalog_version, estimate


def test_estimate_retourne_un_range_jamais_un_scalaire():
    result = estimate("claude-haiku-4-5", 1000)
    assert isinstance(result, Range)
    assert not isinstance(result, (int, float))


def test_annotation_de_retour_de_estimate_est_range():
    # Inspection statique : l'annotation de retour DOIT être Range.
    hints = typing.get_type_hints(estimate)
    assert hints["return"] is Range


def test_range_refuse_min_superieur_a_max():
    with pytest.raises(ValueError):
        Range(min=2, max=1, scope="inference", source="test")


def test_range_exige_un_perimetre_et_une_source():
    with pytest.raises(ValueError):
        Range(min=1, max=2, scope="", source="test")
    with pytest.raises(ValueError):
        Range(min=1, max=2, scope="inference", source="")


def test_range_non_convertible_en_nombre():
    # Un Range n'est PAS un nombre : pas de __float__ ni __int__.
    assert not hasattr(Range, "__float__")
    assert not hasattr(Range, "__int__")
    result = estimate("claude-sonnet-5", 500)
    with pytest.raises(TypeError):
        float(result)
    with pytest.raises(TypeError):
        int(result)


def test_estimate_valeurs_du_catalogue():
    # 1000 tokens de sortie = 1 ktok : les bornes du catalogue s'appliquent telles quelles.
    result = estimate("claude-haiku-4-5", 1000)
    assert result.min == pytest.approx(0.3)
    assert result.max == pytest.approx(1.4)
    assert result.scope == "inference"
    assert result.source  # source obligatoire


def test_estimate_modele_inconnu_leve_keyerror():
    with pytest.raises(KeyError):
        estimate("modele-inconnu", 100)


def test_catalog_version_correspond_au_contrat():
    assert catalog_version() == "2026-07.2"
