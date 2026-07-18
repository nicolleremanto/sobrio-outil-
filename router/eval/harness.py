"""Harnais d'évaluation — mesure N'IMPORTE QUEL `Router` sur le golden set figé.

Écrit un rapport JSON VERSIONNÉ (`router/artifacts/eval/<router_name>-latest.json`)
consommé ensuite par `gate.py` (gate de promotion, même chantier R3). Le
golden set est le juge de paix (chantier R2, `router/eval/golden/`) : ce
module ne fait que LIRE `golden.jsonl` via `loader.py` (qui réutilise
`sobrio_router.types`, zéro réimplémentation du schéma).

RAPPEL — LIMITES STATISTIQUES (contrainte transmise R2 → R3, voir
`router/eval/golden/coverage_report.json` clé `limites_statistiques` et
`router/CONVERGENCE_LEDGER.md` section R2) : certaines cellules
catégorie×opus du golden restent minces (n effectif ≈ nombre de gabarits, pas
de lignes ; certaines cellules sont même VIDES par design — sobriété). Le
bloc `categorie_x_label_informatif` de ce rapport existe à titre INFORMATIF
UNIQUEMENT (relecture humaine, diagnostic) : le GATE DE PROMOTION (`gate.py`)
NE DOIT JAMAIS consommer une métrique opus par cellule — uniquement les
agrégats globaux (`exactitude_ponderee`, `ece`, `p95_ms`, `exactitude_globale`)
ou des comparaisons relatives candidat/baseline/previous.

Module autonome, stdlib SEULE (aucune dépendance) : voir la note d'import en
tête de `loader.py`.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from loader import GoldenEntry, golden_sha256, load_golden

from sobrio_router import VISIBLE_MODELS, HeuristicRouter, Router, SafeRouter

# Rang de coût, du moins cher au plus cher — SOUS-dimensionner = prédire un
# rang INFÉRIEUR à celui de l'étiquette (modèle moins cher que nécessaire :
# LE coût produit, cf. consigne du chantier) ; SUR-dimensionner = prédire un
# rang SUPÉRIEUR (plus cher que nécessaire, gaspillage).
_MODEL_RANK: dict[str, int] = {
    "claude-haiku-4-5": 0,
    "claude-sonnet-5": 1,
    "claude-opus-4-8": 2,
}
# Garde de cohérence : cette table de rang DOIT couvrir exactement les ids
# visibles du catalogue (source de vérité `sobrio_router.VISIBLE_MODELS`,
# elle-même recoupée avec `contracts/model_catalog.yaml` par
# `test_router_corrections_r0.py`).
if set(_MODEL_RANK) != VISIBLE_MODELS:  # pas un assert : doit tenir même sous python -O
    raise RuntimeError("désynchronisation _MODEL_RANK / VISIBLE_MODELS")

# Ordre catalogue stable pour la matrice de confusion (du moins au plus cher).
_CATALOG_ORDER: tuple[str, ...] = tuple(sorted(_MODEL_RANK, key=lambda m: _MODEL_RANK[m]))

# Seuil d'auto-bascule de l'extension (RFC-0003, auto_confidence_threshold
# par défaut) : les décisions à confiance >= ce seuil déclenchent la bascule
# SANS clic. La métrique `calibration_bande_auto` mesure la fiabilité RÉELLE
# de ces décisions-là — l'ECE global (bins égaux) peut la masquer.
# Chiffres précis (r0/r1) : la RÈGLE reasoning long (conf 0.75) est à 51,5 %
# de justesse ; la BANDE >= 0.75 entière est à 65,15 % (écart 0.1235).
_AUTO_THRESHOLD = 0.75

_ARTIFACTS_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "eval"

# Registre des routeurs évaluables par la CLI — extensible (R5 ajoutera
# "ml_v05" ici, probablement lui aussi enveloppé dans un SafeRouter par
# cohérence avec l'invariant §5.2 de production).
_REGISTRY: dict[str, Callable[[], Router]] = {
    "heuristic": lambda: SafeRouter(HeuristicRouter()),
}


def weighted_accuracy(nb_sous: int, nb_sur: int, n: int) -> float:
    """Exactitude pondérée : les erreurs de SOUS-dimensionnement comptent DOUBLE.

    Formule : ``1 - (2*nb_sous + 1*nb_sur) / (2*n)``.

    Motif : le sous-dimensionnement (prédire un modèle MOINS cher que
    l'étiquette — ex. haiku recommandé alors que sonnet était requis) est LE
    coût produit du routeur (tâche mal servie, qualité en dessous du besoin) ;
    le sur-dimensionnement (modèle plus cher que nécessaire) reste une
    erreur, mais un gaspillage économique/environnemental, pas un défaut de
    qualité pour l'utilisateur — d'où le facteur 2 côté sous-dimensionnement.

    Bornée [0, 1] par construction (``nb_sous + nb_sur <= n`` puisque les
    prédictions correctes ne comptent dans aucun des deux compteurs), le
    clamp explicite ci-dessous est une garde défensive supplémentaire.
    """
    if n == 0:
        return 1.0  # convention : rapport vide = aucune erreur à pénaliser
    value = 1.0 - (2 * nb_sous + nb_sur) / (2 * n)
    return max(0.0, min(1.0, value))


def compute_ece(confidences: list[float], corrects: list[bool], n_bins: int = 10) -> float:
    """Expected Calibration Error, `n_bins` bins ÉGAUX sur la confiance [0, 1].

    ``ECE = somme_b (n_b / n) * |acc_b - conf_moyenne_b|`` où ``acc_b`` est le
    taux de bonnes prédictions du bin b (`correct` = prédiction == étiquette)
    et ``conf_moyenne_b`` la confiance moyenne des décisions tombées dans ce
    bin — pondération par effectif (bins déséquilibrés n'ont pas tous le même
    poids). La borne haute 1.0 tombe dans le DERNIER bin (comme un
    histogramme à bornes [k/n_bins, (k+1)/n_bins), sauf le dernier fermé des
    deux côtés). Un bin vide ne contribue rien (poids nul, pas de division).

    LIMITE (v0, documentée ronde 0) : l'heuristique n'émet que 6 valeurs de
    confiance discrètes dans [0.55, 0.80] — seuls ~4 bins sont peuplés, la
    résolution 10 bins est majoritairement inutilisée et l'ECE global peut
    masquer un défaut localisé (d'où la métrique complémentaire
    `calibration_bande_auto`). À réexaminer en R5 quand le classifieur
    produira une distribution de confiance continue.
    """
    n = len(confidences)
    if n == 0:
        return 0.0
    bins: list[list[int]] = [[] for _ in range(n_bins)]
    for i, confidence in enumerate(confidences):
        idx = min(int(confidence * n_bins), n_bins - 1)
        bins[idx].append(i)
    ece = 0.0
    for indices in bins:
        if not indices:
            continue
        bin_n = len(indices)
        acc = sum(1 for i in indices if corrects[i]) / bin_n
        avg_confidence = sum(confidences[i] for i in indices) / bin_n
        ece += (bin_n / n) * abs(acc - avg_confidence)
    return ece


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Percentile par rang le plus proche, pas d'interpolation (même méthode que `bench.py`)."""
    n = len(sorted_values)
    if n == 0:
        return 0.0
    index = min(int(n * pct), n - 1)
    return sorted_values[index]


def _accuracy_by_group(groups: list[str], corrects: list[bool]) -> dict[str, float]:
    """Exactitude par valeur distincte de `groups` (ex. par catégorie)."""
    totals: dict[str, int] = {}
    hits: dict[str, int] = {}
    for group, correct in zip(groups, corrects, strict=True):
        totals[group] = totals.get(group, 0) + 1
        hits[group] = hits.get(group, 0) + int(correct)
    return {group: round(hits[group] / totals[group], 4) for group in sorted(totals)}


def _confusion_matrix(labels: list[str], predictions: list[str]) -> dict:
    """Matrice 3x3 (étiquettes x prédictions), ids catalogue, ordre `_CATALOG_ORDER`."""
    size = len(_CATALOG_ORDER)
    matrix = [[0] * size for _ in range(size)]
    index = {model: i for i, model in enumerate(_CATALOG_ORDER)}
    for label, prediction in zip(labels, predictions, strict=True):
        matrix[index[label]][index[prediction]] += 1
    return {"labels": list(_CATALOG_ORDER), "matrix": matrix}


def _category_by_label_informatif(
    categories: list[str], labels: list[str], corrects: list[bool]
) -> dict[str, dict[str, dict[str, float]]]:
    """Cellule catégorie×label (n + exactitude locale) — INFORMATIF SEULEMENT.

    Voir la note en tête de module : le gate de promotion ne lit JAMAIS ce
    bloc, certaines cellules opus étant trop minces pour un seuil individuel
    fiable (limites_statistiques, chantier R2).
    """
    counts: dict[str, dict[str, list[int]]] = {}
    for category, label, correct in zip(categories, labels, corrects, strict=True):
        cell = counts.setdefault(category, {}).setdefault(label, [0, 0])
        cell[0] += 1
        cell[1] += int(correct)
    return {
        category: {
            label: {"n": n_cell, "exactitude": round(hits / n_cell, 4)}
            for label, (n_cell, hits) in sorted(by_label.items())
        }
        for category, by_label in sorted(counts.items())
    }


def _auto_band_calibration(confidences: list[float], corrects: list[bool]) -> dict:
    """Fiabilité des décisions à confiance >= seuil d'auto-bascule (RFC-0003).

    `ecart` = |taux_justesse - confiance_moyenne| des décisions de la bande :
    c'est la sur/sous-confiance EFFECTIVE là où le produit agit sans clic.
    Le gate exige la NON-RÉGRESSION de cet écart (critère bande-auto).
    Bande vide (aucune décision >= seuil) : n=0, ecart=0.0 (rien à dégrader).
    """
    indices = [i for i, c in enumerate(confidences) if c >= _AUTO_THRESHOLD]
    if not indices:
        return {
            "seuil": _AUTO_THRESHOLD,
            "n": 0,
            "taux_justesse": None,
            "confiance_moyenne": None,
            "ecart": 0.0,
        }
    n = len(indices)
    taux = sum(1 for i in indices if corrects[i]) / n
    conf = sum(confidences[i] for i in indices) / n
    return {
        "seuil": _AUTO_THRESHOLD,
        "n": n,
        "taux_justesse": round(taux, 4),
        "confiance_moyenne": round(conf, 4),
        "ecart": round(abs(taux - conf), 4),
    }


def _calibration_by_confidence(confidences: list[float], corrects: list[bool]) -> dict:
    """Diagnostic PAR valeur de confiance distincte — INFORMATIF SEULEMENT (r1, ml).

    Permet à la recalibration R5 de viser la tranche précise (ex. 0.75) plutôt
    que l'agrégat de bande, qui peut moyenner une tranche mal calibrée avec une
    tranche saine. Le gate ne lit PAS ce bloc (agrégats/relatif seulement).
    """
    groups: dict[float, list[int]] = {}
    for i, confidence in enumerate(confidences):
        groups.setdefault(round(confidence, 4), []).append(i)
    return {
        f"{conf:.2f}": {
            "n": len(indices),
            "taux_justesse": round(sum(1 for i in indices if corrects[i]) / len(indices), 4),
            "ecart": round(abs(sum(1 for i in indices if corrects[i]) / len(indices) - conf), 4),
        }
        for conf, indices in sorted(groups.items())
    }


def evaluate_router(router: Router, entries: list[GoldenEntry]) -> dict:
    """Évalue `router` sur `entries` : chronomètre chaque `decide()`, calcule les métriques.

    Fonction pure vis-à-vis du disque (aucune écriture) — les métadonnées
    (nom du routeur, hash golden, date, sha git) sont ajoutées par `run()`.
    """
    predictions: list[str] = []
    confidences: list[float] = []
    latencies_ms: list[float] = []
    for entry in entries:
        start = time.perf_counter()
        decision = router.decide(entry.signals)
        latencies_ms.append((time.perf_counter() - start) * 1000)
        predictions.append(decision.model)
        confidences.append(decision.confidence)

    n = len(entries)
    labels = [e.label for e in entries]
    categories = [e.category for e in entries]

    for model in (*labels, *predictions):
        if model not in _MODEL_RANK:
            raise ValueError(
                f"modèle hors catalogue visible rencontré dans l'éval : {model!r} — "
                "le routeur évalué doit garantir une sortie dans VISIBLE_MODELS "
                "(l'envelopper dans SafeRouter, invariant §5.2)"
            )

    corrects = [p == label for p, label in zip(predictions, labels, strict=True)]
    exactitude_globale = sum(corrects) / n if n else 0.0

    rank_pairs = [
        (_MODEL_RANK[p], _MODEL_RANK[label]) for p, label in zip(predictions, labels, strict=True)
    ]
    nb_sous = sum(1 for pred_rank, label_rank in rank_pairs if pred_rank < label_rank)
    nb_sur = sum(1 for pred_rank, label_rank in rank_pairs if pred_rank > label_rank)

    sorted_latencies = sorted(latencies_ms)

    return {
        "n": n,
        "exactitude_globale": round(exactitude_globale, 4),
        "exactitude_par_categorie": _accuracy_by_group(categories, corrects),
        "sous_dimensionnement": {"n": nb_sous, "taux": round(nb_sous / n, 4) if n else 0.0},
        "sur_dimensionnement": {"n": nb_sur, "taux": round(nb_sur / n, 4) if n else 0.0},
        "exactitude_ponderee": round(weighted_accuracy(nb_sous, nb_sur, n), 4),
        "ece": round(compute_ece(confidences, corrects), 4),
        "p50_ms": round(_percentile(sorted_latencies, 0.50), 4),
        "p95_ms": round(_percentile(sorted_latencies, 0.95), 4),
        "calibration_bande_auto": _auto_band_calibration(confidences, corrects),
        "calibration_par_confiance_informatif": _calibration_by_confidence(confidences, corrects),
        "matrice_confusion": _confusion_matrix(labels, predictions),
        "categorie_x_label_informatif": _category_by_label_informatif(categories, labels, corrects),
    }


def _git_sha() -> str:
    """Sha court du commit de GÉNÉRATION du rapport (HEAD au moment du run).

    NB : un rapport committé référence donc le commit PARENT de son propre
    commit d'artefact (impossible d'embarquer le sha de son futur commit) —
    sémantique documentée, revue r1. "unknown" hors dépôt git.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).resolve().parent,
            check=True,
            timeout=5,
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


def run(router_name: str) -> dict:
    """Construit le routeur `router_name` depuis le registre, l'évalue, ajoute les métadonnées."""
    if router_name not in _REGISTRY:
        raise ValueError(
            f"routeur inconnu : {router_name!r} — registre disponible : {sorted(_REGISTRY)}"
        )
    router = _REGISTRY[router_name]()
    entries = load_golden()
    report = evaluate_router(router, entries)
    report["router_name"] = router_name
    report["golden_sha"] = golden_sha256()
    report["date"] = datetime.now(tz=UTC).isoformat()
    report["git_sha"] = _git_sha()
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Évalue un routeur sur le golden set figé (chantier R3)."
    )
    parser.add_argument(
        "--router",
        default="heuristic",
        choices=sorted(_REGISTRY),
        help="routeur du registre à évaluer (défaut : heuristic)",
    )
    args = parser.parse_args(argv)

    report = run(args.router)

    _ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _ARTIFACTS_DIR / f"{args.router}-latest.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nrapport écrit : {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
