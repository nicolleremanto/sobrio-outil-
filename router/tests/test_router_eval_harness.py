"""Tests du harnais d'évaluation (`router/eval/harness.py`, chantier R3).

Couvre : rapport bien formé sur le golden RÉEL via `HeuristicRouter`
(toutes les clés, exactitude connue, latence sous budget, matrice 3x3
cohérente, déterminisme hors latence/date), puis les deux fonctions
mathématiques isolées (`weighted_accuracy`, `compute_ece`) sur des cas
synthétiques calculés à la main.

`router/eval/` n'est pas un paquet installé (modules autonomes, invocables en
script direct, cf. `router/eval/harness.py` : `python router/eval/harness.py
--router heuristic`) : ce fichier ajoute son chemin à `sys.path` avant
d'importer `harness`/`loader`, même esprit que `conftest_helpers.py` (import
explicite plutôt qu'un vrai `conftest.py` — voir sa propre docstring).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))

from harness import (  # noqa: E402
    _CATALOG_ORDER,
    compute_ece,
    evaluate_router,
    run,
    weighted_accuracy,
)
from loader import load_golden  # noqa: E402

# Clés EXACTES attendues du rapport complet (métriques + métadonnées).
_EXPECTED_KEYS = {
    "n",
    "exactitude_globale",
    "exactitude_par_categorie",
    "sous_dimensionnement",
    "sur_dimensionnement",
    "exactitude_ponderee",
    "ece",
    "p50_ms",
    "p95_ms",
    "calibration_bande_auto",
    "calibration_par_confiance_informatif",
    "matrice_confusion",
    "categorie_x_label_informatif",
    "repartition_rules",  # R5 : comptes par Decision.rule (informatif)
    "router_name",
    "golden_sha",
    "date",
    "git_sha",
}

# Clés dont la valeur varie légitimement d'un run à l'autre (chrono, horloge).
_NON_DETERMINISTIC_KEYS = {"p50_ms", "p95_ms", "date"}

# Accord heuristique connu du golden set (coverage_stats.json : 0.6685) — le
# harnais doit le retrouver puisque `heuristic` = `SafeRouter(HeuristicRouter())`
# et que la fonction primaire ne peut ici jamais tomber en repli (elle est pure).
_KNOWN_HEURISTIC_AGREEMENT = 0.6685
_TOLERANCE = 0.02


def test_report_has_all_expected_keys():
    report = run("heuristic")
    assert set(report.keys()) == _EXPECTED_KEYS


def test_report_n_matches_golden_size():
    report = run("heuristic")
    assert report["n"] == len(load_golden()) == 181


def test_report_metadata_well_formed():
    report = run("heuristic")
    assert report["router_name"] == "heuristic"
    assert isinstance(report["golden_sha"], str) and len(report["golden_sha"]) == 64
    assert "T" in report["date"]  # ISO 8601


def test_accuracy_matches_known_heuristic_agreement():
    report = run("heuristic")
    assert abs(report["exactitude_globale"] - _KNOWN_HEURISTIC_AGREEMENT) <= _TOLERANCE


def test_accuracy_per_category_covers_all_eight_categories():
    report = run("heuristic")
    assert set(report["exactitude_par_categorie"]) == {
        "code",
        "extraction",
        "juridique_contrat",
        "maths_raisonnement",
        "multi_tours",
        "redaction_simple",
        "resume",
        "traduction",
    }
    for accuracy in report["exactitude_par_categorie"].values():
        assert 0.0 <= accuracy <= 1.0


def test_latency_p95_under_stage1_budget():
    report = run("heuristic")
    # Budget étage 1 (docs/decisions/ROUTEUR_CLASSIFIEUR.md) : p95 < 5 ms CPU.
    assert report["p95_ms"] < 5.0
    assert report["p50_ms"] <= report["p95_ms"]


def test_confusion_matrix_is_3x3_and_sums_to_n():
    report = run("heuristic")
    matrice = report["matrice_confusion"]
    assert matrice["labels"] == list(_CATALOG_ORDER)
    matrix = matrice["matrix"]
    assert len(matrix) == 3
    assert all(len(row) == 3 for row in matrix)
    assert sum(sum(row) for row in matrix) == report["n"]


def test_determinism_across_two_runs_excluding_latency_and_date():
    report_a = run("heuristic")
    report_b = run("heuristic")
    keys_to_compare = _EXPECTED_KEYS - _NON_DETERMINISTIC_KEYS
    for key in keys_to_compare:
        assert report_a[key] == report_b[key], f"non déterministe sur la clé {key!r}"


def test_evaluate_router_matches_run_for_heuristic():
    """`evaluate_router` (sans métadonnées) et `run` (avec) doivent s'accorder sur les métriques."""
    from sobrio_router import HeuristicRouter, SafeRouter

    entries = load_golden()
    direct = evaluate_router(SafeRouter(HeuristicRouter()), entries)
    via_run = run("heuristic")
    for key in direct:
        if key not in _NON_DETERMINISTIC_KEYS:
            assert direct[key] == via_run[key]


# ---------------------------------------------------------------------------
# weighted_accuracy — cas synthétiques calculés à la main.
# ---------------------------------------------------------------------------


def test_weighted_accuracy_two_sous_one_sur_sur_dix():
    # 1 - (2*2 + 1*1) / (2*10) = 1 - 5/20 = 0.75
    assert weighted_accuracy(nb_sous=2, nb_sur=1, n=10) == 0.75


def test_weighted_accuracy_perfect_no_errors():
    assert weighted_accuracy(nb_sous=0, nb_sur=0, n=50) == 1.0


def test_weighted_accuracy_all_sous_dimensionnement():
    # 1 - (2*10 + 0) / (2*10) = 1 - 1 = 0.0 (pire cas, borne basse atteinte)
    assert weighted_accuracy(nb_sous=10, nb_sur=0, n=10) == 0.0


def test_weighted_accuracy_all_sur_dimensionnement():
    # 1 - (0 + 1*10) / (2*10) = 1 - 0.5 = 0.5 (sur-dimensionnement pèse moitié moins)
    assert weighted_accuracy(nb_sous=0, nb_sur=10, n=10) == 0.5


def test_weighted_accuracy_empty_report_is_one_by_convention():
    assert weighted_accuracy(nb_sous=0, nb_sur=0, n=0) == 1.0


def test_weighted_accuracy_bounded_in_unit_interval():
    for nb_sous in range(0, 6):
        for nb_sur in range(0, 6 - nb_sous):
            value = weighted_accuracy(nb_sous, nb_sur, 5)
            assert 0.0 <= value <= 1.0


# ---------------------------------------------------------------------------
# compute_ece — cas synthétique calculé à la main.
# ---------------------------------------------------------------------------


def test_compute_ece_two_bins_hand_calculated():
    """4 décisions, 2 bins non vides (0.3 et 0.9), 2 par bin.

    Bin [0.3, 0.4) : 2 décisions, 0/2 correctes -> acc=0.0, conf_moy=0.3, écart=0.3.
    Bin [0.9, 1.0] : 2 décisions, 2/2 correctes -> acc=1.0, conf_moy=0.9, écart=0.1.
    ECE = (2/4)*0.3 + (2/4)*0.1 = 0.15 + 0.05 = 0.2.
    """
    confidences = [0.9, 0.9, 0.3, 0.3]
    corrects = [True, True, False, False]
    assert math.isclose(compute_ece(confidences, corrects), 0.2, abs_tol=1e-9)


def test_compute_ece_perfectly_calibrated_bin_is_zero():
    # Une seule décision, confiance == exactitude locale (1/1 correcte, conf 1.0).
    assert compute_ece([1.0], [True]) == 0.0


def test_compute_ece_empty_is_zero():
    assert compute_ece([], []) == 0.0


def test_compute_ece_bounded_in_unit_interval():
    confidences = [0.05, 0.15, 0.55, 0.95, 0.42]
    corrects = [True, False, True, False, True]
    assert 0.0 <= compute_ece(confidences, corrects) <= 1.0
