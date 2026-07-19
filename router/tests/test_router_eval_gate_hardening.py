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


# ---------------------------------------------------------------------------
# Minors ronde 3 (qa) : bornes flottantes inclusives, miroir bande, -0.00.
# ---------------------------------------------------------------------------


# qa ronde 4 (mutation testing) : le premier test de bornes (r3) utilisait
# pour l'ECE 0.07 + 0.01, qui est BIT-EXACT en IEEE-754 — il n'exerçait donc
# JAMAIS la branche flottante non-exacte, et 4 des 5 sites round(., 10) du
# gate n'étaient tués par aucun test. Chaque cas ci-dessous choisit une
# référence dont l'addition flottante arrondit EN DESSOUS de la somme
# décimale exacte (vérifié par le garde-fou en tête de test) et vise UN site
# précis : retirer le round() de ce site fait échouer ce cas et lui seul.
# Ronde 5 (ml) : le cas bande (0.18 + 0.02, ex-test séparé r3) est replié ici
# pour hériter du même garde-fou anti-cas-inutile — symétrie des 5 sites.
_BANDE_REF = {"seuil": 0.75, "n": 40, "taux_justesse": 0.60, "confiance_moyenne": 0.78}


@pytest.mark.parametrize(
    ("site", "criterion", "candidate_over", "baseline_over", "previous_over"),
    [
        # ECE, branche baseline (gate.py ece_bound baseline) : 0.06+0.01 < 0.07.
        ("ece-baseline", "FAIL calibration-régression", {"ece": 0.07}, {"ece": 0.06}, None),
        # ECE, branche previous : previous 0.06 est le min liant (baseline 0.08).
        (
            "ece-previous",
            "FAIL calibration-régression",
            {"ece": 0.07},
            {"ece": 0.08},
            {"ece": 0.06},
        ),
        # Sous-dim, branche baseline : 0.12+0.02 < 0.14.
        (
            "sous-baseline",
            "FAIL sous-dimensionnement",
            {"sous_dimensionnement": {"n": 25, "taux": 0.14}},
            {"sous_dimensionnement": {"n": 22, "taux": 0.12}},
            None,
        ),
        # Sous-dim, branche previous : previous 0.15 est le min liant (baseline 0.20).
        (
            "sous-previous",
            "FAIL sous-dimensionnement",
            {"sous_dimensionnement": {"n": 31, "taux": 0.17}},
            {"sous_dimensionnement": {"n": 36, "taux": 0.20}},
            {"sous_dimensionnement": {"n": 27, "taux": 0.15}},
        ),
        # Bande auto (référence mesurée) : 0.18+0.02 < 0.20 (qa r3, replié r5).
        # Critère « FAIL bande-auto : » AVEC séparateur (r5) : le site visé est
        # le critère RELATIF — le nouveau plafond ABSOLU (« FAIL
        # bande-auto-absolu », sans arrondi par construction) échoue, lui,
        # légitimement à 0.20 > 0.10 et ne doit pas être confondu ici.
        (
            "bande",
            "FAIL bande-auto :",
            {"calibration_bande_auto": {**_BANDE_REF, "ecart": 0.20}},
            {"calibration_bande_auto": {**_BANDE_REF, "ecart": 0.18}},
            None,
        ),
    ],
)
def test_gate_each_rounding_site_inclusive_at_exact_limit(
    site, criterion, candidate_over, baseline_over, previous_over
):
    from decimal import Decimal

    # Garde-fou : le couple (référence, tolérance) du site visé DOIT être
    # flottant-non-exact vers le bas, sinon le cas ne teste rien (défaut r4).
    ref_report = previous_over if previous_over is not None else baseline_over
    if "ece" in ref_report:
        ref, tol = ref_report["ece"], 0.01
    elif "calibration_bande_auto" in ref_report:
        ref, tol = ref_report["calibration_bande_auto"]["ecart"], 0.02
    else:
        ref, tol = ref_report["sous_dimensionnement"]["taux"], 0.02
    assert ref + tol < float(Decimal(str(ref)) + Decimal(str(tol))), (
        f"cas {site} inutile : {ref} + {tol} est exact en flottant"
    )

    candidate = _report(exactitude_ponderee=0.95, **candidate_over)
    baseline = _report(**baseline_over)
    previous = _report(exactitude_ponderee=0.90, **previous_over) if previous_over else None
    result = evaluate_gate(candidate, baseline, previous)
    assert not any(r.startswith(criterion) for r in result.reasons)


def test_gate_auto_band_mirror_direction_both_measured():
    """Trou de couverture qa r3 : previous PIRE que baseline, les deux bandes
    MESURÉES → la baseline (plus stricte) reste la référence liante."""
    band = {"seuil": 0.75, "n": 40, "taux_justesse": 0.60, "confiance_moyenne": 0.78}
    candidate = _report(exactitude_ponderee=0.95, calibration_bande_auto={**band, "ecart": 0.15})
    baseline = _report(calibration_bande_auto={**band, "ecart": 0.10})  # borne liante : 0.12
    previous = _report(exactitude_ponderee=0.90, calibration_bande_auto={**band, "ecart": 0.30})
    result = evaluate_gate(candidate, baseline, previous)
    assert result.passed is False
    assert any(r.startswith("FAIL bande-auto") for r in result.reasons)


def test_per_confidence_block_normalizes_negative_zero_label():
    """qa r3 : une confiance qui arrondit à -0.0 produisait une clé « -0.00 »
    distincte de « 0.00 » (défensif : SafeRouter clampe déjà [0, 1] en amont)."""
    from harness import _calibration_by_confidence

    block = _calibration_by_confidence([-0.001, 0.001], [True, False])
    assert set(block) == {"0.00"}
    assert block["0.00"]["n"] == 2


# ---------------------------------------------------------------------------
# R5 — registre ml du harnais (échec BRUYANT sans artefact) + bloc
# `repartition_rules` (informatif, ignoré par le gate, spec R5 §9).
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]

_SCRIPT_ML_SANS_ARTEFACT = """
import sys
from pathlib import Path

sys.path.insert(0, "router/eval")
import harness

harness._ARTIFACTS_DIR = Path(sys.argv[2])  # jamais d'écriture dans le dépôt
harness._REGISTRY["ml_v05_candidate"] = lambda: harness.SafeRouter(
    harness.MLRouter(Path(sys.argv[1]))
)
raise SystemExit(harness.main(["--router", "ml_v05_candidate"]))
"""

_SCRIPT_HEURISTIC_SANS_LIGHTGBM = """
import sys
from pathlib import Path


class _BloqueurLightgbm:
    def find_spec(self, name, path=None, target=None):
        if name == "lightgbm" or name.startswith("lightgbm."):
            raise ImportError("lightgbm bloque (simulation absence)")
        return None


sys.meta_path.insert(0, _BloqueurLightgbm())
sys.path.insert(0, "router/eval")
import harness

harness._ARTIFACTS_DIR = Path(sys.argv[1])  # jamais d'écriture dans le dépôt
raise SystemExit(harness.main(["--router", "heuristic"]))
"""


def test_registre_ml_sans_artefact_refus_propre(tmp_path: Path):
    """CLI `--router ml_v05_candidate` sans artefact : exit 2, REFUS, zéro traceback."""
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            _SCRIPT_ML_SANS_ARTEFACT,
            str(tmp_path / "artefact-inexistant"),
            str(tmp_path / "eval-out"),
        ],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
        timeout=120,
    )
    assert proc.returncode == 2, proc.stderr
    assert "REFUS" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_registre_heuristic_fonctionne_sans_lightgbm_ni_artefact(tmp_path: Path):
    """`--router heuristic` reste fonctionnel SANS lightgbm et SANS artefact ml."""
    proc = subprocess.run(
        [sys.executable, "-c", _SCRIPT_HEURISTIC_SANS_LIGHTGBM, str(tmp_path / "eval-out")],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "eval-out" / "heuristic-latest.json").is_file()


def test_repartition_rules_present_comptes_exacts():
    """Bloc informatif au rapport : comptes PAR règle == décisions réellement émises."""
    from sobrio_router import HeuristicRouter, SafeRouter

    entries = load_golden()[:25]
    report = evaluate_router(SafeRouter(HeuristicRouter()), entries)
    attendu: dict[str, int] = {}
    reference = HeuristicRouter()
    for entry in entries:
        rule = reference.decide(entry.signals).rule
        attendu[rule] = attendu.get(rule, 0) + 1
    assert report["repartition_rules"] == dict(sorted(attendu.items()))
    assert sum(report["repartition_rules"].values()) == len(entries)


def test_repartition_rules_retro_compatible_et_ignore_du_gate():
    """`_validate_report` accepte un rapport SANS le bloc ; le gate ne le lit pas."""
    from gate import _validate_report

    sans_bloc = _report()
    assert "repartition_rules" not in sans_bloc
    assert _validate_report(sans_bloc, "candidat") == []
    # Un bloc contaminé n'influence PAS le verdict du gate (c'est promote.py
    # qui le lit — garde anti-contamination, testée dans test_router_promote).
    candidate = _report(exactitude_ponderee=0.95, repartition_rules={"fallback:heuristic": 181})
    result = evaluate_gate(candidate, _report())
    assert result.passed is True


# ---------------------------------------------------------------------------
# Bornes CLI du gate (minor eval R5 r0) : paramètres opérateur fail-closed.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("--bande-ecart-max", "1.0"),  # neutraliserait le critère 7-bis
        ("--bande-ecart-max", "0"),
        ("--bande-ecart-max", "nan"),
        ("--budget-ms", "inf"),
        ("--budget-ms", "-1"),
    ],
)
def test_gate_cli_rejects_out_of_range_operator_params(tmp_path, flag, value):
    import json

    candidate_path = tmp_path / "candidate.json"
    baseline_path = tmp_path / "baseline.json"
    candidate_path.write_text(json.dumps(_report(exactitude_ponderee=0.95)))
    baseline_path.write_text(json.dumps(_report()))
    proc = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve().parents[1] / "eval" / "gate.py"),
            "--candidate",
            str(candidate_path),
            "--baseline",
            str(baseline_path),
            flag,
            value,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc.returncode == 2
    # Ligne de verdict assertée pour LES DEUX branches de refus (minor qa r3 :
    # la branche budget l'était déjà via le test ci-dessous — alignée ici).
    assert "VERDICT : FAIL" in proc.stderr and "Traceback" not in proc.stderr


def test_gate_cli_rejects_huge_budget_and_accepts_valid_bounds(tmp_path):
    """Minors r1 : --budget-ms plafonné à 1000 (1e9 neutralisait le critère de
    latence) ; chemin d'ACCEPTATION des bornes valides couvert (30 ms / 0.10)."""
    import json

    candidate_path = tmp_path / "candidate.json"
    baseline_path = tmp_path / "baseline.json"
    candidate_path.write_text(
        json.dumps(_report(exactitude_ponderee=0.95, golden_sha=golden_sha256()))
    )
    baseline_path.write_text(json.dumps(_report(golden_sha=golden_sha256())))
    gate_py = str(Path(__file__).resolve().parents[1] / "eval" / "gate.py")
    base_cmd = [
        sys.executable,
        gate_py,
        "--candidate",
        str(candidate_path),
        "--baseline",
        str(baseline_path),
    ]

    huge = subprocess.run(
        base_cmd + ["--budget-ms", "1e9"], capture_output=True, text=True, timeout=30
    )
    assert huge.returncode == 2
    assert "VERDICT : FAIL" in huge.stderr and "Traceback" not in huge.stderr

    valid = subprocess.run(
        base_cmd + ["--budget-ms", "30", "--bande-ecart-max", "0.10"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert valid.returncode == 0
    assert "VERDICT : PASS" in valid.stderr  # le verdict sort sur stderr (contrat CLI)

    # Borne haute INCLUSIVE (minor qa r3) : --budget-ms 1000 exact est dans
    # ]0, 1000] — accepté, aucun refus (le p95 du rapport, 2.0 ms, passe).
    at_bound = subprocess.run(
        base_cmd + ["--budget-ms", "1000"], capture_output=True, text=True, timeout=30
    )
    assert at_bound.returncode == 0
    assert "VERDICT : PASS" in at_bound.stderr
