"""Promotion / rollback de la TÊTE de l'étage 2 — R6 Lot 5, spec §9.3 (patron promote.py).

Invariant : la promotion passe UNIQUEMENT par le gate R3 RÉEL rejoué FRAIS
(`harness_embed` prior + head_candidate, hash canonique du manifest
embed_golden injecté — jamais optionnel), `--budget-ms 30` (§9.2), PLUS les
gardes propres à l'étage 2 :

- anti-contamination : `repartition_rules` du candidat STRICTEMENT ⊆
  `{"embed:v0"}`, sinon REFUS (§9.3.3) ;
- **preuve de latence RÉELLE (D8, §9.3.4)** : le gate sur fixtures ne
  prouvant que la tête (`latence_perimetre: "head_only"`), la promotion
  EXIGE `router/artifacts/bench/embed-latest.json` frais — `p95_ms <= 30.0`
  (inclusif), `rss_peak_mb < 1024` ET `encoder_sha256` == sha int8 du
  manifest courant. Absent/périmé/dépassé => REFUS exit 2. AVANT LE GESTE
  FONDATEUR (recadrage ledger 2026-07-23) : le sha int8 du manifest est
  null, donc AUCUNE preuve bench n'est possible — `promote_embed` REFUSE
  proprement TOUTE promotion effective (exit 2, message « geste
  fondateur ») ; c'est le comportement VOULU : `heads/promoted/` reste VIDE
  en production à la clôture R6 (D4), la promotion de la tête v0 synthétique
  est un acte de STAGING/démo explicite (opérateur local, environnement
  jetable) — jamais un défaut.

Rotation : candidate/ -> promoted/ (l'ancien promoted/ devient previous/) ;
`promoted/eval-report.json` = rapport du candidat AU MOMENT de sa promotion
(sert de `--previous` au prochain gate). Rollback : échange trois-temps
promoted/previous, un niveau d'historique (parité R5).

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

import harness_embed  # noqa: E402 — accès par attribut : chemins monkeypatchables
from embed_fixtures import embed_golden_sha256  # noqa: E402
from gate import _is_finite_number, evaluate_gate  # noqa: E402

from sobrio_router.embed import (  # noqa: E402
    CANDIDATE_HEAD_DIR,
    PREVIOUS_HEAD_DIR,
    PROMOTED_HEAD_DIR,
    EmbedLoadError,
)

CANDIDATE_DIR = CANDIDATE_HEAD_DIR
PROMOTED_DIR = PROMOTED_HEAD_DIR
PREVIOUS_DIR = PREVIOUS_HEAD_DIR

# Preuve bench (D8) et manifest encodeur — chemins module-level
# (monkeypatchables), lus À L'APPEL.
BENCH_REPORT_PATH = _ROUTER_DIR / "artifacts" / "bench" / "embed-latest.json"
MANIFEST_PATH = _ROUTER_DIR / "tools" / "embed_model_manifest.json"

# Budgets §7 (bornes INCLUSIVES pour la latence, convention R5).
BUDGET_MS = 30.0
RSS_MAX_MB = 1024.0

_ARTIFACT_FILES = ("head.json", "calibrator.json", "metadata.json")
_REGLE_ATTENDUE = "embed:v0"


class RefusError(RuntimeError):
    """Garde de promotion/rollback : la CLI imprime `REFUS : …` et sort en 2."""


def _sha_canonique_embed() -> str:
    """Pin du manifest embed_golden, re-typé refus de garde si illisible."""
    try:
        return embed_golden_sha256()
    except ValueError as exc:
        raise RefusError(str(exc)) from exc


def _evals_fraiches() -> tuple[dict, dict]:
    """Rejoue les évals FRAÎCHES (prior + candidat) et écrit les rapports habituels.

    Échec de chargement du candidat => REFUS (exit 2) : rien à évaluer,
    même posture bruyante que la CLI du harnais (leçon R4 — jamais d'éval
    « prouvée à vide »).
    """
    reports: dict[str, dict] = {}
    for name in ("prior", "head_candidate"):
        try:
            report = harness_embed.run(name)
        except EmbedLoadError as exc:
            raise RefusError(f"tête {name} absente ou invalide — rien à évaluer ({exc})") from exc
        harness_embed._ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = harness_embed._ARTIFACTS_DIR / f"embed-{name}-latest.json"
        out_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        reports[name] = report
    return reports["prior"], reports["head_candidate"]


def _verifier_non_contamine(candidate_report: dict) -> None:
    """REFUSE toute clé de `repartition_rules` autre que `embed:v0` (§9.3.3)."""
    repartition = candidate_report.get("repartition_rules")
    if not isinstance(repartition, dict) or not repartition:
        raise RefusError(
            "repartition_rules absent du rapport candidat — contamination invérifiable"
        )
    etrangeres = sorted(set(repartition) - {_REGLE_ATTENDUE})
    if etrangeres:
        raise RefusError(
            f"éval candidate contaminée par des règles étrangères : {etrangeres} — "
            "la tête n'a pas émis seule pendant l'éval, promotion interdite"
        )


def _sha_encodeur_manifest() -> str:
    """Sha256 int8 NORMATIF du manifest — null => geste fondateur non advenu, REFUS.

    C'est la garde qui rend toute promotion effective IMPOSSIBLE avant le
    geste fondateur (D8 + recadrage ledger 2026-07-23) : sans sha d'encodeur
    consigné, aucune preuve bench ne peut être rattachée à un encodeur réel.
    """
    try:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RefusError(f"manifest encodeur illisible : {MANIFEST_PATH} ({exc})") from exc
    sha: object = None
    if isinstance(manifest, dict):
        variante = manifest.get("variants", {})
        if isinstance(variante, dict):
            int8 = variante.get("int8", {})
            if isinstance(int8, dict):
                fichiers = int8.get("files", {})
                if isinstance(fichiers, dict):
                    modele = fichiers.get("model.onnx", {})
                    if isinstance(modele, dict):
                        sha = modele.get("sha256")
    if (
        not isinstance(sha, str)
        or len(sha) != 64
        or any(c not in "0123456789abcdef" for c in sha)
    ):
        raise RefusError(
            "preuve bench impossible : sha256 de l'encodeur int8 non consigné dans le "
            f"manifest ({MANIFEST_PATH}) — geste fondateur §8 non advenu, promotion "
            "effective refusée (D8) ; heads/promoted/ reste vide en production (D4)"
        )
    return sha


def _verifier_preuve_bench() -> None:
    """Garde D8 (§9.3.4) : bench RÉEL frais, budgets tenus, encodeur du manifest."""
    sha_attendu = _sha_encodeur_manifest()
    if not BENCH_REPORT_PATH.is_file():
        raise RefusError(
            f"preuve bench absente : {BENCH_REPORT_PATH} — exécuter make router-embed-bench "
            "(le gate sur fixtures ne prouve que la tête, §9.1)"
        )
    try:
        rapport = json.loads(BENCH_REPORT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RefusError(f"preuve bench illisible : {BENCH_REPORT_PATH} ({exc})") from exc
    if not isinstance(rapport, dict):
        raise RefusError(f"preuve bench non-objet : {BENCH_REPORT_PATH}")
    p95 = rapport.get("p95_ms")
    if not _is_finite_number(p95) or float(p95) > BUDGET_MS:
        raise RefusError(
            f"preuve bench : p95_ms {p95!r} absent ou > budget {BUDGET_MS} ms "
            f"({BENCH_REPORT_PATH})"
        )
    rss = rapport.get("rss_peak_mb")
    if not _is_finite_number(rss) or float(rss) >= RSS_MAX_MB:
        raise RefusError(
            f"preuve bench : rss_peak_mb {rss!r} absent ou >= plafond {RSS_MAX_MB} Mo "
            f"({BENCH_REPORT_PATH})"
        )
    sha_bench = rapport.get("encoder_sha256")
    if sha_bench != sha_attendu:
        raise RefusError(
            f"preuve bench périmée : encoder_sha256 {str(sha_bench)[:12]} != manifest "
            f"{sha_attendu[:12]} — re-bencher l'encodeur courant ({BENCH_REPORT_PATH})"
        )


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
        ("head.json", "sha256_head_json"),
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


def promouvoir() -> int:
    """Gate frais (+ gardes D8) puis rotation candidate -> promoted (-> previous)."""
    baseline, candidate = _evals_fraiches()

    previous_path = PROMOTED_DIR / "eval-report.json"
    previous: dict | None = None
    if previous_path.is_file():
        try:
            previous = json.loads(previous_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RefusError(f"rapport previous illisible : {previous_path} ({exc})") from exc

    result = evaluate_gate(
        candidate,
        baseline,
        previous,
        budget_ms=BUDGET_MS,
        expected_golden_sha=_sha_canonique_embed(),
    )
    for reason in result.reasons:
        print(reason)
    if not result.passed:
        print("REFUS : gate FAIL — promotion interdite (§9.3)", file=sys.stderr)
        return 1

    _verifier_non_contamine(candidate)
    _verifier_preuve_bench()
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
        f"(sha256 head.json {str(metadata.get('sha256_head_json'))[:12]}, "
        f"artefact {metadata.get('artefact')})"
    )
    return 0


def rollback() -> int:
    """Échange trois-temps promoted/previous — exige un previous/ COMPLET."""
    if not PREVIOUS_DIR.exists():
        raise RefusError(f"aucune tête previous : {PREVIOUS_DIR} — rollback impossible")
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
        f"(sha256 head.json {str(metadata.get('sha256_head_json'))[:12]})"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Promotion (défaut) ou rollback de la tête de l'étage 2 (chantier R6, §9.3)."
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
