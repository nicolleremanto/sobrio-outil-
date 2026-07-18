"""Gate de promotion — décide si un rapport d'éval candidat remplace la baseline (R3).

`evaluate_gate(candidate, heuristic_baseline, previous=None)` est une
fonction PURE : elle consomme des rapports JSON déjà chargés (dicts, tels
qu'écrits par `harness.py`) et ne fait AUCUNE I/O — la lecture des fichiers
est réservée à la CLI (`main()`, en bas de ce module). Le résultat est un
`GateResult` : verdict global `passed` + une raison PASS/FAIL lisible par
critère évalué. Le gate est FAIL dès qu'UN SEUL critère échoue.

CONTRAINTE DE GATE (transmise R2 → R3, voir
`router/eval/golden/coverage_report.json` clé `limites_statistiques` et
`router/CONVERGENCE_LEDGER.md` section R2, « cellules_opus ») : certaines
cellules catégorie×opus du golden set restent minces (parfois vides par
design). En conséquence, AUCUN critère de ce gate ne porte sur une cellule
opus individuelle — les métriques opus ne sont consommées qu'EN AGRÉGÉ
(`exactitude_ponderee` globale, `ece` globale) ou EN RELATIF (comparaison
candidat vs baseline/previous), jamais par cellule catégorie×label. Le bloc
`categorie_x_label_informatif` produit par `harness.py` n'est JAMAIS lu ici.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

# Budget étage 1 (docs/decisions/ROUTEUR_CLASSIFIEUR.md, §7 du ledger) :
# p95 < 5 ms CPU. Paramètre `budget_ms` de `evaluate_gate` pour permettre à
# R6 (étage 2 embeddings, budget p95 < 30 ms) de réutiliser cette même
# fonction sans dupliquer la logique.
_DEFAULT_BUDGET_MS = 5.0
_DEFAULT_ECE_MAX = 0.10


@dataclass(frozen=True)
class GateResult:
    """Verdict du gate de promotion : binaire + raisons lisibles, une par critère."""

    passed: bool
    reasons: list[str]


def evaluate_gate(
    candidate: dict,
    heuristic_baseline: dict,
    previous: dict | None = None,
    budget_ms: float = _DEFAULT_BUDGET_MS,
    ece_max: float = _DEFAULT_ECE_MAX,
) -> GateResult:
    """Applique les critères du gate de promotion ; FAIL si UN critère échoue.

    Critères, chacun produisant une raison PASS/FAIL dans l'ordre :
    1. `exactitude_ponderee(candidate) > exactitude_ponderee(heuristic_baseline)`
       — STRICT (le candidat doit battre l'heuristique, pas seulement l'égaler) ;
    2. si `previous` est fourni : `exactitude_ponderee(candidate) >=
       exactitude_ponderee(previous)` — pas de régression face à l'artefact
       déjà en production ;
    3. `ece(candidate) <= ece_max` (0.10 par défaut) — calibration acceptable ;
    4. `p95_ms(candidate) <= budget_ms` (5.0 ms par défaut, budget étage 1 ;
       R6 appellera avec `budget_ms=30.0` pour l'étage 2 embeddings) ;
    5. `golden_sha(candidate) == golden_sha(heuristic_baseline)` — comparaison
       valide seulement si les deux rapports évaluent le MÊME set figé.

    Le critère 2 est SKIPPÉ (aucune raison ajoutée, aucun impact sur le
    verdict) si `previous` est `None` — première promotion, rien à comparer.
    """
    reasons: list[str] = []
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

    candidate_sha = candidate["golden_sha"]
    baseline_sha = heuristic_baseline["golden_sha"]
    if candidate_sha == baseline_sha:
        reasons.append("PASS golden_sha : candidat et baseline évalués sur le même set figé")
    else:
        passed = False
        reasons.append(
            f"FAIL golden_sha : candidat ({candidate_sha[:12]}…) != "
            f"baseline ({baseline_sha[:12]}…) — comparaison invalide, sets différents"
        )

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

    candidate = _load_report(args.candidate)
    baseline = _load_report(args.baseline)
    previous = _load_report(args.previous) if args.previous is not None else None

    result = evaluate_gate(candidate, baseline, previous, budget_ms=args.budget_ms)

    for reason in result.reasons:
        print(reason)
    print("VERDICT :", "PASS" if result.passed else "FAIL", file=sys.stderr)

    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
