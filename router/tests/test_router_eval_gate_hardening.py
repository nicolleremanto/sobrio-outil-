"""Durcissement du gate (corrections ronde 0 — eval-scientist + ml-architect + qa).

Verrouille : validation de schéma fail-closed (rapports invalides prouvés
passants avant correction), épinglage au hash canonique du golden, calibration
NON-régressive, non-régression du sous-dimensionnement, couverture de la bande
d'auto-bascule, CLI fail-closed sur fichier manquant, et les deux branches
défensives du harnais (registre inconnu, modèle hors catalogue).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))

from gate import evaluate_gate  # noqa: E402
from harness import evaluate_router, run  # noqa: E402
from loader import golden_sha256, load_golden  # noqa: E402

from sobrio_router import Decision, Router, Signals  # noqa: E402

_SHA_A = "a" * 64


def _report(**overrides: object) -> dict:
    base: dict = {
        "exactitude_ponderee": 0.80,
        "ece": 0.05,
        "p95_ms": 2.0,
        "golden_sha": _SHA_A,
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
# Schéma fail-closed : les rapports invalides PASSAIENT avant correction.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"exactitude_ponderee": 5.0},  # > 1, mathématiquement impossible — passait
        {"exactitude_ponderee": float("nan")},
        {"ece": -1.0},  # passait
        {"p95_ms": -5.0},  # passait
        {"p95_ms": float("inf")},
        {"golden_sha": "deadbeef"},  # pas un sha256
        {"golden_sha": None},
        {"sous_dimensionnement": {}},  # taux manquant
        {"calibration_bande_auto": None},
    ],
)
def test_gate_fails_closed_on_invalid_candidate(overrides):
    candidate = _report(exactitude_ponderee=0.95)
    candidate.update(overrides)
    baseline = _report()

    result = evaluate_gate(candidate, baseline, previous=None)

    assert result.passed is False
    assert any("FAIL schéma" in r for r in result.reasons)


def test_gate_fails_closed_on_missing_key_without_exception():
    """Clé manquante : FAIL structuré (reasons remplies), pas de KeyError brut."""
    candidate = _report(exactitude_ponderee=0.95)
    del candidate["ece"]
    result = evaluate_gate(candidate, _report(), previous=None)
    assert result.passed is False
    assert any("FAIL schéma" in r and "ece" in r for r in result.reasons)


def test_gate_validates_baseline_and_previous_too():
    bad_baseline = _report()
    bad_baseline["exactitude_ponderee"] = 3.0
    result = evaluate_gate(_report(exactitude_ponderee=0.95), bad_baseline)
    assert result.passed is False
    assert any("baseline" in r and "FAIL schéma" in r for r in result.reasons)


# ---------------------------------------------------------------------------
# Épinglage au hash canonique (deux rapports « d'accord » sur un autre set).
# ---------------------------------------------------------------------------


def test_gate_rejects_reports_agreeing_on_a_foreign_set():
    fake_sha = "d" * 64
    candidate = _report(exactitude_ponderee=0.95, golden_sha=fake_sha)
    baseline = _report(golden_sha=fake_sha)

    unpinned = evaluate_gate(candidate, baseline)  # sans épinglage : accord interne suffit
    pinned = evaluate_gate(candidate, baseline, expected_golden_sha=golden_sha256())

    assert unpinned.passed is True
    assert pinned.passed is False
    assert any("canonique" in r for r in pinned.reasons)


def test_gate_cli_always_pins_to_canonical_sha(tmp_path):
    """La CLI injecte TOUJOURS le hash committé : rapports étrangers refusés."""
    import json

    fake_sha = "e" * 64
    candidate_path = tmp_path / "candidate.json"
    baseline_path = tmp_path / "baseline.json"
    candidate_path.write_text(json.dumps(_report(exactitude_ponderee=0.95, golden_sha=fake_sha)))
    baseline_path.write_text(json.dumps(_report(golden_sha=fake_sha)))

    proc = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parents[1] / "eval" / "gate.py"),
            "--candidate",
            str(candidate_path),
            "--baseline",
            str(baseline_path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 1
    assert "canonique" in proc.stdout


def test_gate_cli_missing_file_clean_fail(tmp_path):
    """Fichier introuvable : message propre + exit 2, pas de traceback brut."""
    proc = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parents[1] / "eval" / "gate.py"),
            "--candidate",
            str(tmp_path / "inexistant.json"),
            "--baseline",
            str(tmp_path / "inexistant2.json"),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 2
    assert "introuvable" in proc.stderr
    assert "Traceback" not in proc.stderr


# ---------------------------------------------------------------------------
# Calibration non-régressive + sous-dimensionnement + bande auto.
# ---------------------------------------------------------------------------


def test_gate_fails_when_ece_regresses_versus_baseline():
    """ECE 0.0999 <= 0.10 absolu MAIS pire que la baseline 0.05 : FAIL (r0, ml)."""
    candidate = _report(exactitude_ponderee=0.95, ece=0.0999)
    baseline = _report(ece=0.05)
    result = evaluate_gate(candidate, baseline)
    assert result.passed is False
    assert any(r.startswith("FAIL calibration-régression") for r in result.reasons)


def test_gate_ece_within_tolerance_of_baseline_passes():
    candidate = _report(exactitude_ponderee=0.95, ece=0.058)  # baseline 0.05 + tol 0.01
    result = evaluate_gate(candidate, _report(ece=0.05))
    assert result.passed is True


def test_gate_fails_when_sous_dimensionnement_regresses():
    """L'agrégat pondéré monte mais LE coût produit (sous-dim) régresse : FAIL."""
    candidate = _report(exactitude_ponderee=0.95, sous_dimensionnement={"n": 30, "taux": 0.20})
    baseline = _report(sous_dimensionnement={"n": 10, "taux": 0.10})
    result = evaluate_gate(candidate, baseline)
    assert result.passed is False
    assert any(r.startswith("FAIL sous-dimensionnement") for r in result.reasons)


def test_gate_fails_when_auto_band_reliability_regresses():
    """La bande >= 0.75 déclenche la bascule SANS clic : son écart ne doit pas croître."""
    candidate = _report(
        exactitude_ponderee=0.95,
        calibration_bande_auto={
            "seuil": 0.75,
            "n": 40,
            "taux_justesse": 0.55,
            "confiance_moyenne": 0.78,
            "ecart": 0.23,
        },
    )
    baseline = _report()  # ecart baseline 0.02
    result = evaluate_gate(candidate, baseline)
    assert result.passed is False
    assert any(r.startswith("FAIL bande-auto") for r in result.reasons)


def test_gate_empty_auto_band_passes_trivially():
    candidate = _report(
        exactitude_ponderee=0.95,
        calibration_bande_auto={
            "seuil": 0.75,
            "n": 0,
            "taux_justesse": None,
            "confiance_moyenne": None,
            "ecart": 0.0,
        },
    )
    result = evaluate_gate(candidate, _report())
    assert result.passed is True
    assert any("rien à dégrader" in r for r in result.reasons)


# ---------------------------------------------------------------------------
# Branches défensives du harnais (minors qa ronde 0).
# ---------------------------------------------------------------------------


def test_harness_run_unknown_router_raises():
    with pytest.raises(ValueError, match="routeur inconnu"):
        run("routeur-bogus")


class _RogueRouter(Router):
    def decide(self, signals: Signals) -> Decision:
        return Decision(model="gpt-4-leaked", confidence=0.9, rule="rogue")


def test_harness_rejects_out_of_catalog_predictions():
    entries = load_golden()[:5]
    with pytest.raises(ValueError, match="hors catalogue"):
        evaluate_router(_RogueRouter(), entries)


# ---------------------------------------------------------------------------
# Le rapport réel porte les nouveaux champs (schéma du gate satisfait).
# ---------------------------------------------------------------------------


def test_real_heuristic_report_satisfies_gate_schema():
    import json

    report_path = (
        Path(__file__).resolve().parents[1] / "artifacts" / "eval" / "heuristic-latest.json"
    )
    report = json.loads(report_path.read_text())
    # Auto-comparaison : baseline == candidat ⇒ FAIL sur le critère STRICT,
    # mais AUCUN "FAIL schéma" (le rapport réel est structurellement valide).
    result = evaluate_gate(report, report, expected_golden_sha=golden_sha256())
    assert not any("FAIL schéma" in r for r in result.reasons)
    assert any(r.startswith("FAIL baseline") for r in result.reasons)
    # La bande d'auto-bascule est mesurée sur le rapport réel.
    assert report["calibration_bande_auto"]["n"] > 0


# ---------------------------------------------------------------------------
# Références vs previous (minors ml ronde 1 — tranché : min(baseline, previous)).
# ---------------------------------------------------------------------------


def test_gate_sous_dim_guards_versus_previous_too():
    """Un candidat qui bat l'heuristique mais régresse LE coût produit vs
    l'artefact promu doit échouer (asymétrie de référence corrigée, r1 ml)."""
    candidate = _report(exactitude_ponderee=0.95, sous_dimensionnement={"n": 27, "taux": 0.15})
    baseline = _report(sous_dimensionnement={"n": 36, "taux": 0.20})  # borne large : 0.22
    previous = _report(sous_dimensionnement={"n": 18, "taux": 0.10})  # borne stricte : 0.12
    result = evaluate_gate(candidate, baseline, previous)
    assert result.passed is False
    assert any(r.startswith("FAIL sous-dimensionnement") for r in result.reasons)


def test_gate_auto_band_guards_versus_previous_too():
    """Même patron pour la fiabilité de l'auto-bascule : le plancher heuristique
    large (0.1235) ne redevient jamais la référence après une promotion."""
    band = {"seuil": 0.75, "confiance_moyenne": 0.78, "n": 40, "taux_justesse": 0.70}
    candidate = _report(exactitude_ponderee=0.95, calibration_bande_auto={**band, "ecart": 0.10})
    baseline = _report(calibration_bande_auto={**band, "ecart": 0.12})  # borne large : 0.14
    previous = _report(calibration_bande_auto={**band, "ecart": 0.02})  # borne stricte : 0.04
    result = evaluate_gate(candidate, baseline, previous)
    assert result.passed is False
    assert any(r.startswith("FAIL bande-auto") for r in result.reasons)


# ---------------------------------------------------------------------------
# Diagnostic par valeur de confiance (minor ml r1 — informatif, jamais lu par le gate).
# ---------------------------------------------------------------------------


def test_harness_reports_per_confidence_calibration_informative():
    from sobrio_router import HeuristicRouter, SafeRouter

    entries = load_golden()
    report = evaluate_router(SafeRouter(HeuristicRouter()), entries)
    block = report["calibration_par_confiance_informatif"]
    assert sum(cell["n"] for cell in block.values()) == len(entries)
    for cell in block.values():
        assert 0.0 <= cell["taux_justesse"] <= 1.0
        assert cell["ecart"] >= 0.0
    # La tranche découverte en r0 est visible individuellement (règle à 0.75).
    assert "0.75" in block


# ---------------------------------------------------------------------------
# Bornes des références min(baseline, previous) — défauts/trous prouvés ronde 2.
# ---------------------------------------------------------------------------


def test_gate_previous_empty_band_never_serves_as_reference():
    """MAJOR ronde 2 (eval + ml) : l'écart 0.0 CONVENTIONNEL d'une bande vide
    chez previous servait de référence via min() et rejetait un candidat MIEUX
    calibré que la baseline. Une bande n=0 ne borne plus jamais le min."""
    band = {"seuil": 0.75, "confiance_moyenne": 0.78}
    candidate = _report(
        exactitude_ponderee=0.95,
        calibration_bande_auto={**band, "n": 40, "taux_justesse": 0.73, "ecart": 0.05},
    )
    baseline = _report(
        calibration_bande_auto={**band, "n": 66, "taux_justesse": 0.65, "ecart": 0.1235}
    )
    previous = _report(
        exactitude_ponderee=0.90,
        calibration_bande_auto={
            **band,
            "n": 0,
            "taux_justesse": None,
            "confiance_moyenne": None,
            "ecart": 0.0,
        },
    )
    result = evaluate_gate(candidate, baseline, previous)
    assert result.passed is True
    assert any(r.startswith("PASS bande-auto") for r in result.reasons)


def test_gate_all_references_empty_band_passes_with_explicit_reason():
    empty = {"seuil": 0.75, "n": 0, "taux_justesse": None, "confiance_moyenne": None, "ecart": 0.0}
    full = {"seuil": 0.75, "n": 40, "taux_justesse": 0.7, "confiance_moyenne": 0.78, "ecart": 0.08}
    candidate = _report(exactitude_ponderee=0.95, calibration_bande_auto=full)
    baseline = _report(calibration_bande_auto=dict(empty))
    previous = _report(exactitude_ponderee=0.90, calibration_bande_auto=dict(empty))
    result = evaluate_gate(candidate, baseline, previous)
    assert result.passed is True
    assert any("aucune référence à bande mesurée" in r for r in result.reasons)


def test_gate_previous_worse_than_baseline_keeps_baseline_binding():
    """Direction miroir du min() (trou de couverture r2) : previous PIRE que la
    baseline → la baseline reste la référence liante, dans les deux sens."""
    candidate_sous = {"n": 27, "taux": 0.15}
    baseline = _report(sous_dimensionnement={"n": 18, "taux": 0.10})  # borne liante : 0.12
    previous = _report(
        exactitude_ponderee=0.70, sous_dimensionnement={"n": 45, "taux": 0.25}
    )  # borne large : 0.27

    failing = evaluate_gate(
        _report(exactitude_ponderee=0.95, sous_dimensionnement=candidate_sous),
        baseline,
        previous,
    )
    assert failing.passed is False
    assert any(r.startswith("FAIL sous-dimensionnement") for r in failing.reasons)

    passing = evaluate_gate(
        _report(exactitude_ponderee=0.95, sous_dimensionnement={"n": 20, "taux": 0.11}),
        baseline,
        previous,
    )
    assert not any(r.startswith("FAIL sous-dimensionnement") for r in passing.reasons)


def test_gate_bound_is_inclusive_at_exact_limit():
    """candidat == borne exacte → PASS (<= inclusif), pas un FAIL d'arrondi."""
    candidate = _report(exactitude_ponderee=0.95, sous_dimensionnement={"n": 22, "taux": 0.12})
    baseline = _report(sous_dimensionnement={"n": 18, "taux": 0.10})  # borne : 0.10 + 0.02
    result = evaluate_gate(candidate, baseline)
    assert not any(r.startswith("FAIL sous-dimensionnement") for r in result.reasons)


# ---------------------------------------------------------------------------
# Collision de cellules du bloc par-confiance — major ronde 2 (ml + qa).
# ---------------------------------------------------------------------------


def test_per_confidence_block_never_loses_cells_on_collision():
    """Grouper à round(,4) puis clef .2f écrasait silencieusement les cellules
    en collision (0.7501/0.7523/0.7549 → une seule cellule n=1). Le groupement
    se fait désormais à la granularité de la clé : n cumulés, sum(n) == total,
    écart mesuré contre la confiance MOYENNE réelle de la cellule."""
    from harness import _calibration_by_confidence

    block = _calibration_by_confidence([0.7501, 0.7523, 0.7549, 0.10], [True, False, True, True])
    assert sum(cell["n"] for cell in block.values()) == 4
    assert block["0.75"]["n"] == 3
    assert block["0.75"]["taux_justesse"] == round(2 / 3, 4)
    assert block["0.75"]["confiance_moyenne"] == round((0.7501 + 0.7523 + 0.7549) / 3, 4)
    assert block["0.10"] == {"n": 1, "taux_justesse": 1.0, "confiance_moyenne": 0.1, "ecart": 0.9}
