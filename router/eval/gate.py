"""Gate de promotion — décide si un rapport d'éval candidat remplace la baseline (R3).

`evaluate_gate(...)` est une fonction PURE : elle consomme des rapports JSON
déjà chargés (dicts, tels qu'écrits par `harness.py`) et ne fait AUCUNE I/O —
la lecture des fichiers est réservée à la CLI (`main()`, en bas de ce module).
Le résultat est un `GateResult` : verdict global `passed` + une raison
PASS/FAIL lisible par critère évalué. Le gate est FAIL dès qu'UN SEUL critère
échoue, et FAIL-CLOSED sur tout rapport STRUCTURELLEMENT invalide
(durcissement ronde 0 : schéma validé AVANT toute comparaison — un rapport
avec exactitude 5.0, ECE négatif, NaN ou clé manquante ne peut plus passer ni
faire crasher le gate).

ÉPINGLAGE AU SET FIGÉ (durcissement ronde 0) : le critère golden_sha ne se
contente plus de l'égalité INTERNE candidat==baseline — la CLI injecte le hash
CANONIQUE committé (`GOLDEN_SHA256`, via `loader.golden_sha256()`) et les deux
rapports doivent y correspondre. Un couple de rapports « d'accord entre eux »
sur un autre set (plus facile, fabriqué) est refusé.

SEUILS CHIFFRÉS : voir `docs/decisions/ROUTEUR_CLASSIFIEUR.md`, section
« Gate de promotion — seuils chiffrés » (rationnel du 0.10 d'ECE, des
tolérances de non-régression, de la pondération 2x et de la couverture de la
bande d'auto-bascule).

CONTRAINTE DE GATE (transmise R2 → R3, voir
`router/eval/golden/coverage_report.json` clé `limites_statistiques` et
`router/CONVERGENCE_LEDGER.md` section R2, « cellules_opus ») : certaines
cellules catégorie×opus du golden set restent minces (parfois vides par
design). En conséquence, AUCUN critère de ce gate ne porte sur une cellule
opus individuelle — les métriques sont consommées EN AGRÉGÉ ou EN RELATIF
(candidat vs baseline/previous), jamais par cellule catégorie×label. Le bloc
`categorie_x_label_informatif` produit par `harness.py` n'est JAMAIS lu ici.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path

# Budget étage 1 (docs/decisions/ROUTEUR_CLASSIFIEUR.md « Budgets §7 ») :
# p95 < 5 ms CPU. Paramètre `budget_ms` de `evaluate_gate` pour permettre à
# R6 (étage 2 embeddings, budget p95 < 30 ms) de réutiliser cette même
# fonction sans dupliquer la logique.
_DEFAULT_BUDGET_MS = 5.0
# Plafond ABSOLU de calibration — rationnel documenté dans
# ROUTEUR_CLASSIFIEUR.md (« Gate de promotion — seuils chiffrés »). Complété
# par un critère de NON-RÉGRESSION vs baseline/previous (durcissement r0 :
# un plafond absolu seul laissait un candidat MOINS calibré que la baseline
# passer le gate).
_DEFAULT_ECE_MAX = 0.10
# Tolérances de non-régression (marges d'estimation sur n=181 points) —
# documentées avec les seuils dans ROUTEUR_CLASSIFIEUR.md.
_ECE_REGRESSION_TOL = 0.01
_SOUS_DIM_REGRESSION_TOL = 0.02
_BANDE_AUTO_REGRESSION_TOL = 0.02


@dataclass(frozen=True)
class GateResult:
    """Verdict du gate de promotion : binaire + raisons lisibles, une par critère."""

    passed: bool
    reasons: list[str]


def _is_finite_number(value: object) -> bool:
    """Nombre réel FINI (bool exclu — même précaution que SafeRouter, R1)."""
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    )


def _validate_report(report: object, name: str) -> list[str]:
    """Valide la FORME d'un rapport ; liste de raisons FAIL (vide = valide).

    Durcissement ronde 0 (eval-scientist, prouvé par exécution) : sans cette
    garde, un rapport avec exactitude_ponderee=5.0, ece=-1.0, p95_ms=-5.0
    passait le gate, et une clé manquante levait un KeyError brut (contrat
    GateResult rompu). Fail-closed : toute violation = FAIL structuré.
    """
    fails: list[str] = []
    if not isinstance(report, dict):
        return [f"FAIL schéma ({name}) : rapport non-objet ({type(report).__name__})"]

    bounded = {
        "exactitude_ponderee": (0.0, 1.0),
        "ece": (0.0, 1.0),
    }
    for key, (low, high) in bounded.items():
        value = report.get(key)
        if not _is_finite_number(value) or not (low <= float(value) <= high):
            fails.append(f"FAIL schéma ({name}) : {key} absent ou hors [{low}, {high}] ({value!r})")

    p95 = report.get("p95_ms")
    if not _is_finite_number(p95) or float(p95) < 0.0:
        fails.append(f"FAIL schéma ({name}) : p95_ms absent ou négatif ({p95!r})")

    sha = report.get("golden_sha")
    if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        fails.append(f"FAIL schéma ({name}) : golden_sha absent ou non sha256-hex ({sha!r})")

    sous = report.get("sous_dimensionnement")
    taux = sous.get("taux") if isinstance(sous, dict) else None
    if not _is_finite_number(taux) or not (0.0 <= float(taux) <= 1.0):
        fails.append(
            f"FAIL schéma ({name}) : sous_dimensionnement.taux absent ou hors [0, 1] ({taux!r})"
        )

    bande = report.get("calibration_bande_auto")
    if not isinstance(bande, dict):
        fails.append(f"FAIL schéma ({name}) : calibration_bande_auto absente")
    else:
        bande_n = bande.get("n")
        ecart = bande.get("ecart")
        if not isinstance(bande_n, int) or isinstance(bande_n, bool) or bande_n < 0:
            fails.append(f"FAIL schéma ({name}) : calibration_bande_auto.n invalide ({bande_n!r})")
        if not _is_finite_number(ecart) or not (0.0 <= float(ecart) <= 1.0):
            fails.append(
                f"FAIL schéma ({name}) : calibration_bande_auto.ecart hors [0, 1] ({ecart!r})"
            )

    return fails


def evaluate_gate(
    candidate: dict,
    heuristic_baseline: dict,
    previous: dict | None = None,
    budget_ms: float = _DEFAULT_BUDGET_MS,
    ece_max: float = _DEFAULT_ECE_MAX,
    expected_golden_sha: str | None = None,
) -> GateResult:
    """Applique les critères du gate de promotion ; FAIL si UN critère échoue.

    Critères, chacun produisant une raison PASS/FAIL :
    0. SCHÉMA : les trois rapports sont structurellement valides (bornes,
       finitude, clés) — sinon FAIL immédiat sans comparaison (fail-closed) ;
    1. baseline : `exactitude_ponderee(candidate) > baseline` — STRICT ;
    2. previous (si fourni) : `exactitude_ponderee(candidate) >= previous` ;
    3. calibration ABSOLUE : `ece(candidate) <= ece_max` (0.10) ;
    4. calibration NON-RÉGRESSIVE : `ece(candidate) <= ece(baseline) + 0.01`
       et, si previous, `<= ece(previous) + 0.01` (durcissement r0 : la
       calibration ne peut plus dériver silencieusement vers la borne) ;
    5. latence : `p95_ms(candidate) <= budget_ms` (5.0 ms étage 1 ; R6 : 30.0).
       Budget ABSOLU assumé — pas de critère relatif : le contrat de latence
       est le budget, pas l'artefact précédent (décision documentée) ;
    6. sous-dimensionnement NON-RÉGRESSIF : `taux(candidate) <=
       min(baseline, previous) + 0.02` — LE coût produit ne doit pas se
       dégrader, ni vs l'heuristique ni vs l'artefact promu (r0 + r1) ;
    7. bande d'auto-bascule : `ecart(candidate) <= min(baseline, previous)
       + 0.02` —
       les décisions à confiance >= 0.75 déclenchent la bascule SANS clic
       (RFC-0003) ; l'ECE global peut masquer une sur-confiance dans cette
       bande précise (découverte r0 : l'heuristique y est à 51,5 % de
       justesse) — critère RELATIF pour ne jamais laisser un candidat
       aggraver la fiabilité de l'auto-bascule ;
    8. golden_sha : candidat == baseline, ET, si `expected_golden_sha` est
       fourni (la CLI l'injecte TOUJOURS depuis `GOLDEN_SHA256` committé),
       égalité au hash CANONIQUE du set figé.
    """
    reasons: list[str] = []

    schema_fails = _validate_report(candidate, "candidat") + _validate_report(
        heuristic_baseline, "baseline"
    )
    if previous is not None:
        schema_fails += _validate_report(previous, "previous")
    if schema_fails:
        return GateResult(passed=False, reasons=schema_fails)

    passed = True

    candidate_wa = candidate["exactitude_ponderee"]
    baseline_wa = heuristic_baseline["exactitude_ponderee"]
    if candidate_wa > baseline_wa:
        reasons.append(
            f"PASS baseline : exactitude_ponderee candidat {candidate_wa:.4f} > "
            f"heuristique {baseline_wa:.4f}"
        )
    else:
        passed = False
        reasons.append(
            f"FAIL baseline : exactitude_ponderee candidat {candidate_wa:.4f} <= "
            f"heuristique {baseline_wa:.4f} (strictement supérieur requis)"
        )

    if previous is not None:
        previous_wa = previous["exactitude_ponderee"]
        if candidate_wa >= previous_wa:
            reasons.append(
                f"PASS previous : exactitude_ponderee candidat {candidate_wa:.4f} >= "
                f"précédent {previous_wa:.4f}"
            )
        else:
            passed = False
            reasons.append(
                f"FAIL previous : exactitude_ponderee candidat {candidate_wa:.4f} < "
                f"précédent {previous_wa:.4f} (régression face à l'artefact en production)"
            )

    candidate_ece = candidate["ece"]
    if candidate_ece <= ece_max:
        reasons.append(f"PASS calibration : ece candidat {candidate_ece:.4f} <= {ece_max:.4f}")
    else:
        passed = False
        reasons.append(f"FAIL calibration : ece candidat {candidate_ece:.4f} > {ece_max:.4f}")

    baseline_ece = heuristic_baseline["ece"]
    ece_bound = baseline_ece + _ECE_REGRESSION_TOL
    if previous is not None:
        ece_bound = min(ece_bound, previous["ece"] + _ECE_REGRESSION_TOL)
    if candidate_ece <= ece_bound:
        reasons.append(
            f"PASS calibration-régression : ece candidat {candidate_ece:.4f} <= "
            f"référence + tolérance {ece_bound:.4f}"
        )
    else:
        passed = False
        reasons.append(
            f"FAIL calibration-régression : ece candidat {candidate_ece:.4f} > "
            f"référence + tolérance {ece_bound:.4f} (moins calibré que l'existant)"
        )

    candidate_p95 = candidate["p95_ms"]
    if candidate_p95 <= budget_ms:
        reasons.append(
            f"PASS latence : p95 candidat {candidate_p95:.4f} ms <= budget {budget_ms} ms"
        )
    else:
        passed = False
        reasons.append(
            f"FAIL latence : p95 candidat {candidate_p95:.4f} ms > budget {budget_ms} ms"
        )

    candidate_sous = candidate["sous_dimensionnement"]["taux"]
    baseline_sous = heuristic_baseline["sous_dimensionnement"]["taux"]
    # Référence = min(baseline, previous) — tranché r1 (ml) : une fois un
    # artefact ML promu, le candidat ne peut pas régresser vers le plancher
    # heuristique large. Même patron que l'ECE.
    sous_bound = baseline_sous + _SOUS_DIM_REGRESSION_TOL
    if previous is not None:
        sous_bound = min(
            sous_bound, previous["sous_dimensionnement"]["taux"] + _SOUS_DIM_REGRESSION_TOL
        )
    if candidate_sous <= sous_bound:
        reasons.append(
            f"PASS sous-dimensionnement : taux candidat {candidate_sous:.4f} <= "
            f"baseline + tolérance {sous_bound:.4f}"
        )
    else:
        passed = False
        reasons.append(
            f"FAIL sous-dimensionnement : taux candidat {candidate_sous:.4f} > "
            f"baseline + tolérance {sous_bound:.4f} (LE coût produit régresse)"
        )

    candidate_bande = candidate["calibration_bande_auto"]
    baseline_bande = heuristic_baseline["calibration_bande_auto"]
    if candidate_bande["n"] == 0:
        reasons.append(
            "PASS bande-auto : aucune décision candidate à confiance >= seuil "
            "d'auto-bascule (rien à dégrader)"
        )
    else:
        bande_bound = baseline_bande["ecart"] + _BANDE_AUTO_REGRESSION_TOL
        if previous is not None:
            bande_bound = min(
                bande_bound,
                previous["calibration_bande_auto"]["ecart"] + _BANDE_AUTO_REGRESSION_TOL,
            )
        if candidate_bande["ecart"] <= bande_bound:
            reasons.append(
                f"PASS bande-auto : écart candidat {candidate_bande['ecart']:.4f} <= "
                f"baseline + tolérance {bande_bound:.4f}"
            )
        else:
            passed = False
            reasons.append(
                f"FAIL bande-auto : écart candidat {candidate_bande['ecart']:.4f} > "
                f"baseline + tolérance {bande_bound:.4f} (l'auto-bascule deviendrait "
                "moins fiable — RFC-0003)"
            )

    candidate_sha = candidate["golden_sha"]
    baseline_sha = heuristic_baseline["golden_sha"]
    if candidate_sha != baseline_sha:
        passed = False
        reasons.append(
            f"FAIL golden_sha : candidat ({candidate_sha[:12]}…) != "
            f"baseline ({baseline_sha[:12]}…) — comparaison invalide, sets différents"
        )
    elif expected_golden_sha is not None and candidate_sha != expected_golden_sha:
        passed = False
        reasons.append(
            f"FAIL golden_sha : rapports d'accord entre eux ({candidate_sha[:12]}…) mais "
            f"PAS sur le set figé canonique ({expected_golden_sha[:12]}…) — évaluation "
            "sur un autre set refusée"
        )
    else:
        suffix = " (épinglé au hash canonique)" if expected_golden_sha is not None else ""
        reasons.append(f"PASS golden_sha : candidat et baseline sur le même set figé{suffix}")

    return GateResult(passed=passed, reasons=reasons)


def _load_report(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Gate de promotion — PASS/FAIL d'un rapport d'éval candidat (chantier R3)."
    )
    parser.add_argument("--candidate", required=True, type=Path, help="rapport JSON candidat")
    parser.add_argument(
        "--baseline", required=True, type=Path, help="rapport JSON de la baseline heuristique"
    )
    parser.add_argument(
        "--previous", type=Path, default=None, help="rapport JSON de l'artefact en production"
    )
    parser.add_argument(
        "--budget-ms",
        type=float,
        default=_DEFAULT_BUDGET_MS,
        help=f"budget p95 en ms (défaut {_DEFAULT_BUDGET_MS}, étage 1 ; 30.0 pour l'étage 2 R6)",
    )
    args = parser.parse_args(argv)

    # Chargement FAIL-CLOSED : un fichier introuvable/illisible produit un
    # message de diagnostic propre (pas un traceback brut) et un exit dédié.
    try:
        candidate = _load_report(args.candidate)
        baseline = _load_report(args.baseline)
        previous = _load_report(args.previous) if args.previous is not None else None
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL : rapport introuvable ou illisible — {exc}", file=sys.stderr)
        print("VERDICT : FAIL", file=sys.stderr)
        return 2

    # Épinglage au set figé CANONIQUE : la CLI injecte TOUJOURS le hash
    # committé (GOLDEN_SHA256) — voir docstring de module (durcissement r0).
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from loader import golden_sha256  # import local : module autonome

    result = evaluate_gate(
        candidate,
        baseline,
        previous,
        budget_ms=args.budget_ms,
        expected_golden_sha=golden_sha256(),
    )

    for reason in result.reasons:
        print(reason)
    print("VERDICT :", "PASS" if result.passed else "FAIL", file=sys.stderr)

    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
