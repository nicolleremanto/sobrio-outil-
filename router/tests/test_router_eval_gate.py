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
    assert len(result.reasons) == 5  # baseline + previous + ece + latence + golden_sha
    assert all(reason.startswith("PASS") for reason in result.reasons)


def test_gate_passes_without_previous_four_criteria_only():
    candidate = _report(exactitude_ponderee=0.85)
    baseline = _report(exactitude_ponderee=0.80)

    result = evaluate_gate(candidate, baseline, previous=None)

    assert result.passed is True
    assert len(result.reasons) == 4  # pas de critère "previous"
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
    assert any(r.startswith("FAIL calibration") for r in result.reasons)
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
