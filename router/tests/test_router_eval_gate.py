"""Tests du gate de promotion (`router/eval/gate.py`, chantier R3).

Rapports synthétiques (dicts minimaux, pas de fichiers) : un cas PASS complet
et un cas FAIL par critère isolé — chaque scénario ne fait échouer QU'UN
critère à la fois, pour vérifier que `evaluate_gate` diagnostique la bonne
cause. Voir la note d'import en tête de `test_router_eval_harness.py` : même
mécanisme de `sys.path` pour importer `router/eval/gate.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))

from gate import GateResult, evaluate_gate  # noqa: E402

_SHA_A = "a" * 64
_SHA_B = "b" * 64


def _report(**overrides: object) -> dict:
    """Rapport minimal PASS par défaut (surchargeable champ par champ)."""
    base: dict = {
        "exactitude_ponderee": 0.80,
        "ece": 0.05,
        "p95_ms": 2.0,
        "golden_sha": _SHA_A,
        # Champs exigés par le durcissement ronde 0 (schéma + nouveaux critères).
        "sous_dimensionnement": {"n": 10, "taux": 0.10},
        "calibration_bande_auto": {
            "seuil": 0.75,
            "n": 40,
            "taux_justesse": 0.80,
            "confiance_moyenne": 0.78,
            "ecart": 0.02,
        },
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Cas PASS complet.
# ---------------------------------------------------------------------------


def test_gate_passes_when_all_criteria_met():
    candidate = _report(exactitude_ponderee=0.85)
    baseline = _report(exactitude_ponderee=0.80)
    previous = _report(exactitude_ponderee=0.82)

    result = evaluate_gate(candidate, baseline, previous)

    assert isinstance(result, GateResult)
    assert result.passed is True
    # baseline + previous + calibration + calibration-régression + latence
    # + sous-dimensionnement + bande-auto + bande-auto-absolu (R5) + golden_sha
    assert len(result.reasons) == 9
    assert all(reason.startswith("PASS") for reason in result.reasons)


def test_gate_passes_without_previous_four_criteria_only():
    candidate = _report(exactitude_ponderee=0.85)
    baseline = _report(exactitude_ponderee=0.80)

    result = evaluate_gate(candidate, baseline, previous=None)

    assert result.passed is True
    assert len(result.reasons) == 8  # pas de critère "previous"
    assert all(reason.startswith("PASS") for reason in result.reasons)


# ---------------------------------------------------------------------------
# Un FAIL par critère, isolé.
# ---------------------------------------------------------------------------


def test_gate_fails_when_baseline_not_beaten():
    candidate = _report(exactitude_ponderee=0.80)  # égal, pas STRICTEMENT supérieur
    baseline = _report(exactitude_ponderee=0.80)

    result = evaluate_gate(candidate, baseline, previous=None)

    assert result.passed is False
    assert any(r.startswith("FAIL baseline") for r in result.reasons)


def test_gate_fails_when_baseline_worse_than_candidate_but_below_strict():
    """Cas limite explicite : candidat en-dessous de la baseline (pas juste égal)."""
    candidate = _report(exactitude_ponderee=0.70)
    baseline = _report(exactitude_ponderee=0.80)

    result = evaluate_gate(candidate, baseline, previous=None)

    assert result.passed is False
    assert any(r.startswith("FAIL baseline") for r in result.reasons)


def test_gate_fails_when_previous_regressed():
    candidate = _report(exactitude_ponderee=0.85)
    baseline = _report(exactitude_ponderee=0.80)  # battue : ce critère PASS
    previous = _report(exactitude_ponderee=0.90)  # candidat régresse face à previous

    result = evaluate_gate(candidate, baseline, previous)

    assert result.passed is False
    assert any(r.startswith("PASS baseline") for r in result.reasons)
    assert any(r.startswith("FAIL previous") for r in result.reasons)


def test_gate_fails_when_ece_too_high():
    candidate = _report(exactitude_ponderee=0.85, ece=0.15)
    baseline = _report(exactitude_ponderee=0.80)

    result = evaluate_gate(candidate, baseline, previous=None)

    assert result.passed is False
    assert any(r.startswith("FAIL calibration :") for r in result.reasons)
    # Les autres critères restent PASS (échec isolé sur l'ECE).
    assert any(r.startswith("PASS baseline") for r in result.reasons)
    assert any(r.startswith("PASS latence") for r in result.reasons)
    assert any(r.startswith("PASS golden_sha") for r in result.reasons)


def test_gate_fails_when_latency_p95_exceeds_budget():
    candidate = _report(exactitude_ponderee=0.85, p95_ms=7.3)
    baseline = _report(exactitude_ponderee=0.80)

    result = evaluate_gate(candidate, baseline, previous=None)

    assert result.passed is False
    assert any(r.startswith("FAIL latence") for r in result.reasons)


def test_gate_fails_when_golden_sha_differs():
    candidate = _report(exactitude_ponderee=0.85, golden_sha=_SHA_B)
    baseline = _report(exactitude_ponderee=0.80, golden_sha=_SHA_A)

    result = evaluate_gate(candidate, baseline, previous=None)

    assert result.passed is False
    assert any(r.startswith("FAIL golden_sha") for r in result.reasons)


def test_gate_custom_budget_ms_used_for_latency_criterion():
    """`budget_ms` paramétrable (étage 2 R6, ex. 30 ms) — un p95 de 20 ms passe alors."""
    candidate = _report(exactitude_ponderee=0.85, p95_ms=20.0)
    baseline = _report(exactitude_ponderee=0.80)

    result_default_budget = evaluate_gate(candidate, baseline, previous=None)
    result_stage2_budget = evaluate_gate(candidate, baseline, previous=None, budget_ms=30.0)

    assert result_default_budget.passed is False
    assert result_stage2_budget.passed is True


def test_gate_never_reads_per_cell_opus_metrics():
    """Un rapport SANS `categorie_x_label_informatif` doit quand même s'évaluer (aucune lecture)."""
    candidate = _report(exactitude_ponderee=0.85)
    baseline = _report(exactitude_ponderee=0.80)
    assert "categorie_x_label_informatif" not in candidate
    assert "categorie_x_label_informatif" not in baseline

    result = evaluate_gate(candidate, baseline, previous=None)

    assert result.passed is True


# ---------------------------------------------------------------------------
# R5 — plafond ABSOLU d'écart de bande (critère 7-bis) + registre ml +
# bloc `repartition_rules` (spec R5 §9-§10).
# ---------------------------------------------------------------------------


def _bande(n: int, ecart: float) -> dict:
    return {
        "seuil": 0.75,
        "n": n,
        "taux_justesse": 0.80 if n else None,
        "confiance_moyenne": 0.80 if n else None,
        "ecart": ecart,
    }


def test_bande_plafond_absolu_fail_malgre_references_laxistes():
    """Écart 0.12 <= références relatives laxistes MAIS > plafond absolu 0.10 : FAIL."""
    candidate = _report(exactitude_ponderee=0.85, calibration_bande_auto=_bande(40, 0.12))
    baseline = _report(calibration_bande_auto=_bande(66, 0.1235))  # bande héritée R3
    result = evaluate_gate(candidate, baseline)
    assert result.passed is False
    assert any(r.startswith("PASS bande-auto :") for r in result.reasons)  # relatif OK
    assert any(r.startswith("FAIL bande-auto-absolu") for r in result.reasons)


def test_bande_plafond_absolu_pass_candidat_ancre():
    """Écart 0.0093 (candidat ancré) : PASS absolu ET relatif."""
    candidate = _report(exactitude_ponderee=0.85, calibration_bande_auto=_bande(123, 0.0093))
    result = evaluate_gate(candidate, _report())
    assert result.passed is True
    assert any(r.startswith("PASS bande-auto-absolu") for r in result.reasons)


def test_bande_plafond_absolu_ferme_le_trou_references_vides():
    """Baseline ET previous à bande VIDE + écart candidat 0.5 : FAIL absolu (le trou R3)."""
    candidate = _report(exactitude_ponderee=0.85, calibration_bande_auto=_bande(40, 0.5))
    baseline = _report(calibration_bande_auto=_bande(0, 0.0))
    previous = _report(calibration_bande_auto=_bande(0, 0.0))
    result = evaluate_gate(candidate, baseline, previous)
    assert result.passed is False
    # Le critère relatif, lui, n'a rien contre quoi régresser (trou fermé par l'absolu).
    assert any("rien contre quoi régresser" in r for r in result.reasons)
    assert any(r.startswith("FAIL bande-auto-absolu") for r in result.reasons)


def test_bande_plafond_absolu_limite_exacte_inclusive():
    """Écart 0.10 EXACT : PASS (borne <= inclusive, comparaison directe sans arrondi)."""
    candidate = _report(exactitude_ponderee=0.85, calibration_bande_auto=_bande(40, 0.10))
    baseline = _report(calibration_bande_auto=_bande(66, 0.1235))
    result = evaluate_gate(candidate, baseline)
    assert result.passed is True
    assert any(r.startswith("PASS bande-auto-absolu") for r in result.reasons)


def test_bande_plafond_absolu_candidate_vide_pass_les_deux_criteres():
    """Bande candidate VIDE : PASS des deux critères (l'absolu n'est pas évalué, n=0)."""
    candidate = _report(exactitude_ponderee=0.85, calibration_bande_auto=_bande(0, 0.0))
    result = evaluate_gate(candidate, _report())
    assert result.passed is True
    assert not any("bande-auto-absolu" in r for r in result.reasons)
    assert any("rien à dégrader" in r for r in result.reasons)


def test_bande_plafond_absolu_cli_parametrable():
    """`--bande-ecart-max` / paramètre `bande_ecart_max` (réutilisable R6)."""
    candidate = _report(exactitude_ponderee=0.85, calibration_bande_auto=_bande(40, 0.12))
    baseline = _report(calibration_bande_auto=_bande(66, 0.1235))
    assert evaluate_gate(candidate, baseline).passed is False
    assert evaluate_gate(candidate, baseline, bande_ecart_max=0.15).passed is True
