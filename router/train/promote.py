"""Promotion / rollback de l'artefact ml_v05 — 1 commande chacun (spec R5 §11).

Invariant §5.3 : la promotion passe UNIQUEMENT par le gate R3 RÉEL, rejoué
FRAIS ici même (évals heuristique + candidat via les fonctions du harnais,
hash canonique du golden injecté — jamais optionnel). Gate FAIL => REFUS,
aucun dossier touché. Garde anti-contamination : un rapport candidat dont
`repartition_rules` contient la moindre clé autre que `ml:v05` (un repli
`fallback:heuristic` pendant l'éval) est REFUSÉ — on ne promeut pas un
artefact mesuré partiellement sur l'heuristique.

Rotation : candidate/ -> promoted/ (l'ancien promoted/ devient previous/) ;
`promoted/eval-report.json` = rapport du candidat AU MOMENT de sa promotion
(sert de `--previous` au prochain gate). Rollback : échange trois-temps
promoted/previous. Un seul niveau d'historique (assumé v0.5).

Exit codes : 0 OK · 1 gate FAIL (le code du gate) · 2 refus de garde.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

_ROUTER_DIR = Path(__file__).resolve().parents[1]
_EVAL_DIR = str(_ROUTER_DIR / "eval")
if _EVAL_DIR not in sys.path:
    sys.path.insert(0, _EVAL_DIR)

from gate import evaluate_gate  # noqa: E402
from harness import _ARTIFACTS_DIR, run  # noqa: E402
from loader import golden_sha256  # noqa: E402

from sobrio_router.ml import CANDIDATE_DIR, PROMOTED_DIR, MLRouterLoadError  # noqa: E402

PREVIOUS_DIR = PROMOTED_DIR.parent / "previous"

_ARTIFACT_FILES = ("model.txt", "calibrator.json", "metadata.json")


class RefusError(RuntimeError):
    """Garde de promotion/rollback : la CLI imprime `REFUS : …` et sort en 2."""


def _evals_fraiches() -> tuple[dict, dict]:
    """Rejoue les évals FRAÎCHES (heuristique + candidat) et écrit les rapports habituels.

    Échec de chargement du candidat => REFUS (exit 2) : rien à évaluer,
    même posture bruyante que la CLI du harnais (leçon R4).
    """
    reports: dict[str, dict] = {}
    for name in ("heuristic", "ml_v05_candidate"):
        try:
            report = run(name)
        except MLRouterLoadError as exc:
            raise RefusError(
                f"artefact {name} absent ou invalide — rien à évaluer ({exc})"
            ) from exc
        _ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = _ARTIFACTS_DIR / f"{name}-latest.json"
        out_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        reports[name] = report
    return reports["heuristic"], reports["ml_v05_candidate"]


def _verifier_integrite(directory: Path) -> dict:
    """Artefact complet + sha metadata == octets ; retourne le metadata validé."""
    for name in _ARTIFACT_FILES:
        if not (directory / name).is_file():
            raise RefusError(f"artefact incomplet : {directory / name} absent")
    try:
        metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RefusError(f"metadata.json illisible : {directory} ({exc})") from exc
    if not isinstance(metadata, dict):
        raise RefusError(f"metadata.json non-objet : {directory}")
    for filename, key in (
        ("model.txt", "sha256_model_txt"),
        ("calibrator.json", "sha256_calibrator_json"),
    ):
        attendu = metadata.get(key)
        reel = hashlib.sha256((directory / filename).read_bytes()).hexdigest()
        if reel != attendu:
            raise RefusError(
                f"intégrité : {key} attendu {str(attendu)[:12]} != octets {reel[:12]} "
                f"({directory / filename})"
            )
    return metadata


def _verifier_non_contamine(candidate_report: dict) -> None:
    """REFUSE toute clé de `repartition_rules` autre que `ml:v05` (spec §11.4)."""
    repartition = candidate_report.get("repartition_rules")
    if not isinstance(repartition, dict) or not repartition:
        raise RefusError(
            "repartition_rules absent du rapport candidat — contamination invérifiable"
        )
    etrangeres = sorted(set(repartition) - {"ml:v05"})
    if etrangeres:
        raise RefusError(
            f"éval candidate contaminée par des replis : {etrangeres} — l'artefact a replié "
            "pendant l'éval, promotion interdite"
        )


def promouvoir() -> int:
    """Gate frais puis rotation candidate -> promoted (-> previous). §5.3."""
    baseline, candidate = _evals_fraiches()

    previous_path = PROMOTED_DIR / "eval-report.json"
    previous: dict | None = None
    if previous_path.is_file():
        try:
            previous = json.loads(previous_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RefusError(f"rapport previous illisible : {previous_path} ({exc})") from exc

    result = evaluate_gate(candidate, baseline, previous, expected_golden_sha=golden_sha256())
    for reason in result.reasons:
        print(reason)
    if not result.passed:
        print("REFUS : gate FAIL — promotion interdite (§5.3)", file=sys.stderr)
        return 1

    _verifier_non_contamine(candidate)
    metadata = _verifier_integrite(CANDIDATE_DIR)

    if PROMOTED_DIR.exists():
        if PREVIOUS_DIR.exists():
            shutil.rmtree(PREVIOUS_DIR)
        PROMOTED_DIR.rename(PREVIOUS_DIR)
    shutil.copytree(CANDIDATE_DIR, PROMOTED_DIR)
    (PROMOTED_DIR / "eval-report.json").write_text(
        json.dumps(candidate, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        f"PROMU : {CANDIDATE_DIR} -> {PROMOTED_DIR} "
        f"(sha256 model.txt {str(metadata.get('sha256_model_txt'))[:12]}, "
        f"best_iteration {metadata.get('best_iteration')})"
    )
    return 0


def rollback() -> int:
    """Échange trois-temps promoted/previous — exige un previous/ COMPLET."""
    if not PREVIOUS_DIR.exists():
        raise RefusError(f"aucun artefact previous : {PREVIOUS_DIR} — rollback impossible")
    metadata = _verifier_integrite(PREVIOUS_DIR)

    if PROMOTED_DIR.exists():
        tmp_dir = PROMOTED_DIR.parent / "promoted.tmp-rollback"
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)
        PROMOTED_DIR.rename(tmp_dir)
        PREVIOUS_DIR.rename(PROMOTED_DIR)
        tmp_dir.rename(PREVIOUS_DIR)
    else:
        # Pas de promoted/ à échanger (état dégradé) : restaure simplement.
        PREVIOUS_DIR.rename(PROMOTED_DIR)
    print(
        f"ROLLBACK : {PREVIOUS_DIR} -> {PROMOTED_DIR} "
        f"(sha256 model.txt {str(metadata.get('sha256_model_txt'))[:12]})"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Promotion (défaut) ou rollback de l'artefact ml_v05 (chantier R5, §5.3)."
    )
    parser.add_argument(
        "--rollback",
        action="store_true",
        help="restaure previous/ en promoted/ (échange trois-temps, 1 niveau d'historique)",
    )
    args = parser.parse_args(argv)

    try:
        return rollback() if args.rollback else promouvoir()
    except RefusError as exc:
        print(f"REFUS : {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
