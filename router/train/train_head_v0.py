"""Entraînement de la tête v0 sur embeddings SYNTHÉTIQUES — R6 Lot 5, spec §8 (D4).

Pipeline : `canonical_train_set()` (embeddings seedés, JAMAIS de texte,
JAMAIS le set d'éval — garde d'étanchéité : REFUS si `EVAL_SEED ==
TRAIN_SEED`) -> split interne train/val 85/15 STRATIFIÉ par label (la val
sert la calibration) -> régression logistique multinomiale (softmax),
descente de gradient FULL-BATCH numpy, seedée (`DEFAULT_SEED=4242`, parité
corpus R4), L2 faible, itérations FIXES — DÉTERMINISTE à l'octet entre runs
(patron train R5, test de double-run bit-identique) -> calibration
isotonique CONSERVATRICE `min(brut, iso(brut))` sur la val (RÉUTILISE
`fit_isotonic` de train_v05 — zéro réimplémentation) -> val_metrics dérivées
d'une `EmbedHead` construite EN MÉMOIRE via `predict` ligne à ligne (la
SEULE porte de sortie d'une confiance de tête, §5.2bis — zéro miroir de la
chaîne, correction ronde 1 : ML-R6r0-m1 = ES-R6r0-m1 = DQ-R6-m2) ->
artefacts `heads/candidate/` (head.json -> calibrator.json -> metadata.json
EN DERNIER, sha256 consignés, schéma §6.3 exigé par `EmbedHead.load`).

STATUT v0 CONSIGNÉ DANS L'ARTEFACT (D4) : cette tête prouve la MÉCANIQUE
(train -> calibration -> gate -> promotion -> service) sur fixtures
synthétiques — elle n'est PAS représentative, la tête réelle attend la
télémétrie v1 (`head_reelle_attend_telemetrie_v1: true`, champ `statut`).
`heads/promoted/` reste VIDE en production à la clôture R6.

Le plafond D3 (`confidence_cap` 0.74) est ÉCRIT ici dans metadata.json — sa
SEULE source (§6.3) : le code de service n'en porte aucun littéral, le
retirer en v1 = nouvel artefact, pas un patch.

Validations FAIL-CLOSED (exit 2, `REFUS : …`, patron train_v05/DQ-R3) :
numpy absent (« installer router/requirements-embed.txt »), étanchéité des
seeds, split déséquilibré, poids non finis, calibrateur dégénéré. Aucun
réseau, aucun texte. Dépense : 0,00 $.

Module autonome (convention train_v05) : insère `router/eval/` dans
`sys.path` pour `embed_fixtures` (fixtures canoniques) et `harness`
(métriques + `_git_sha` — zéro réimplémentation).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path

_ROUTER_DIR = Path(__file__).resolve().parents[1]
_EVAL_DIR = str(_ROUTER_DIR / "eval")
if _EVAL_DIR not in sys.path:
    sys.path.insert(0, _EVAL_DIR)

from embed_fixtures import (  # noqa: E402
    DEFAULT_SIGMA,
    EVAL_SEED,
    TRAIN_SEED,
    EmbedFixture,
    canonical_train_set,
)
from harness import _auto_band_calibration, _git_sha, compute_ece, weighted_accuracy  # noqa: E402
from train_v05 import RefusError, fit_isotonic  # noqa: E402

from sobrio_router.embed import CANDIDATE_HEAD_DIR, EmbedHead, expected_embed_spec  # noqa: E402
from sobrio_router.ml import LABEL_ORDER  # noqa: E402

DEFAULT_SEED = 4242
# Plafond D3 écrit dans metadata.json (`confidence_cap`) — SEULE source du
# plafond, consommée fail-closed par `EmbedHead.load` (§5.2bis/§6.3).
CONFIDENCE_CAP_V0 = 0.74
# Statut D4 consigné mot pour mot dans l'artefact (metadata honnête —
# constante EXACTE, pinnée par les tests du lot).
STATUT_V0 = "tête v0 fixtures synthétiques — non représentative, attend télémétrie v1"
# Hyperparamètres FIGÉS (§8) — ne pas retuner sans nouvelle ronde. Calés au
# Lot 5 avec DEFAULT_SIGMA (voir embed_fixtures) pour que la chaîne SERVIE
# (min(brut, iso) puis plafond 0.74) passe le gate INCHANGÉ (§9.2) :
# ECE servi ~0,07 <= 0.10 avec marge, exactitude ~0,68 dans le garde-fou
# anti-dégénérescence [0.55, 0.999] (§10.8).
_VAL_PCT = 0.15
_LEARNING_RATE = 3.0
_N_ITERATIONS = 1200
_L2 = 5e-5
# Garde de stratification (miroir §3.5 R5) : écart max entre parts de classe
# train/val — le split stratifié exact la satisfait par construction, la
# garde reste (fail-closed si le split est cassé par une évolution).
_STRATIFICATION_TOL = 0.03


def _split_stratifie(
    rows: list[EmbedFixture], rng: object
) -> tuple[list[EmbedFixture], list[EmbedFixture]]:
    """Split train/val 85/15 STRATIFIÉ par label — permutation seedée par label.

    `rng` est un `numpy.random.Generator` déjà seedé (flux UNIQUE du train :
    split d'abord, initialisation des poids ensuite — ordre fixe,
    déterminisme bit-exact). Itération par `LABEL_ORDER` (jamais un ensemble
    non trié).
    """
    indices_val: set[int] = set()
    par_label: dict[str, list[int]] = {label: [] for label in LABEL_ORDER}
    for i, row in enumerate(rows):
        par_label[row.label].append(i)
    for label in LABEL_ORDER:
        indices = par_label[label]
        if not indices:
            raise RefusError(f"classe absente du train : {label}")
        permutation = rng.permutation(len(indices))  # type: ignore[attr-defined]
        n_val = round(len(indices) * _VAL_PCT)
        indices_val.update(indices[j] for j in permutation[:n_val])
    train_rows = [row for i, row in enumerate(rows) if i not in indices_val]
    val_rows = [row for i, row in enumerate(rows) if i in indices_val]
    if not train_rows or not val_rows:
        raise RefusError(
            f"split déséquilibré : partition vide (train {len(train_rows)} / val {len(val_rows)})"
        )
    return train_rows, val_rows


def _verifier_stratification(train_rows: list[EmbedFixture], val_rows: list[EmbedFixture]) -> None:
    """Garde-fou a posteriori (patron §3.5 R5) : REFUS si une part de classe dévie."""
    ecarts: dict[str, float] = {}
    for label in LABEL_ORDER:
        part_train = sum(1 for r in train_rows if r.label == label) / len(train_rows)
        part_val = sum(1 for r in val_rows if r.label == label) / len(val_rows)
        ecarts[label] = abs(part_val - part_train)
    pire = max(ecarts.values())
    if pire > _STRATIFICATION_TOL:
        raise RefusError(
            f"split déséquilibré : écart de classe max {pire:.4f} > {_STRATIFICATION_TOL} "
            f"({ {k: round(v, 4) for k, v in ecarts.items()} })"
        )


def _metrics_val(y_val: list[int], pred_idx: list[int], conf_emises: list[float]) -> dict:
    """Métriques sur la VAL — mêmes définitions que le harnais (imports directs)."""
    n = len(y_val)
    corrects = [p == y for p, y in zip(pred_idx, y_val, strict=True)]
    nb_sous = sum(1 for p, y in zip(pred_idx, y_val, strict=True) if p < y)
    nb_sur = sum(1 for p, y in zip(pred_idx, y_val, strict=True) if p > y)
    return {
        "n": n,
        "exactitude_globale": round(sum(corrects) / n, 4) if n else 0.0,
        "exactitude_ponderee": round(weighted_accuracy(nb_sous, nb_sur, n), 4),
        "sous_dimensionnement": {"n": nb_sous, "taux": round(nb_sous / n, 4) if n else 0.0},
        "sur_dimensionnement": {"n": nb_sur, "taux": round(nb_sur / n, 4) if n else 0.0},
        "ece": round(compute_ece(conf_emises, corrects), 4),
        "calibration_bande_auto": _auto_band_calibration(conf_emises, corrects),
    }


def run_training(out_dir: Path, seed: int = DEFAULT_SEED) -> dict:
    """Pipeline complet §8 : fixtures, split, softmax full-batch, calibration, artefacts.

    Retourne un résumé (chemins, hash, métriques val). Lève `RefusError` sur
    toute validation fail-closed. Ordre d'écriture : head.json ->
    calibrator.json -> metadata.json EN DERNIER (sa présence marque un
    artefact complet — `EmbedHead.load` exige les trois).
    """
    # Dépendance d'ENTRAÎNEMENT (router/requirements-embed.txt), importée
    # PARESSEUSEMENT : le module reste importable sans elle, le contrat CLI
    # fail-closed tient aussi (exit 2, « REFUS », zéro traceback — leçon
    # DQ-R3, patron des skips lightgbm).
    try:
        import numpy
    except ImportError as exc:
        raise RefusError(
            f"dépendances embed absentes ({exc.__class__.__name__}) — "
            "installer router/requirements-embed.txt"
        ) from exc

    # Étanchéité train/éval (§8) : le train ne DOIT jamais voir le set
    # d'éval — les seeds canoniques sont distincts par construction (§7.1),
    # cette garde refuse toute dérive future.
    if TRAIN_SEED == EVAL_SEED:
        raise RefusError(f"étanchéité train/éval rompue : train_seed == eval_seed ({TRAIN_SEED})")

    rows = canonical_train_set()
    rng = numpy.random.default_rng(seed)
    train_rows, val_rows = _split_stratifie(rows, rng)
    _verifier_stratification(train_rows, val_rows)

    label_index = {label: index for index, label in enumerate(LABEL_ORDER)}
    x_train = numpy.asarray([r.embedding for r in train_rows], dtype=numpy.float64)
    y_train = numpy.asarray([label_index[r.label] for r in train_rows])
    x_val = numpy.asarray([r.embedding for r in val_rows], dtype=numpy.float64)
    y_val = [label_index[r.label] for r in val_rows]

    # Régression logistique multinomiale, full-batch, itérations fixes (§8).
    y_onehot = numpy.eye(len(LABEL_ORDER))[y_train]
    poids = rng.normal(0.0, 0.01, (len(LABEL_ORDER), x_train.shape[1]))
    biais = numpy.zeros(len(LABEL_ORDER))
    n = len(x_train)
    for _ in range(_N_ITERATIONS):
        logits = x_train @ poids.T + biais
        logits -= logits.max(axis=1, keepdims=True)
        exp = numpy.exp(logits)
        probas = exp / exp.sum(axis=1, keepdims=True)
        gradient = (probas - y_onehot) / n
        poids -= _LEARNING_RATE * (gradient.T @ x_train + _L2 * poids)
        biais -= _LEARNING_RATE * gradient.sum(axis=0)
    if not (bool(numpy.isfinite(poids).all()) and bool(numpy.isfinite(biais).all())):
        raise RefusError("entraînement dégénéré : poids non finis — hyperparamètres à revoir")

    def _predire(x_mat: object) -> tuple[list[int], list[float]]:
        logits = x_mat @ poids.T + biais  # type: ignore[operator]
        logits -= logits.max(axis=1, keepdims=True)
        exp = numpy.exp(logits)
        probas = exp / exp.sum(axis=1, keepdims=True)
        return (
            [int(i) for i in probas.argmax(axis=1)],
            [float(c) for c in probas.max(axis=1)],
        )

    # Calibration isotonique CONSERVATRICE sur la val (§8) — brique R5
    # réutilisée (`fit_isotonic`, ajustée sur les confiances BRUTES du train
    # numpy : les octets de calibrator.json restent bit-identiques).
    pred_val, conf_brutes = _predire(x_val)
    corrects_val = [p == y for p, y in zip(pred_val, y_val, strict=True)]
    calib_x, calib_y = fit_isotonic(conf_brutes, corrects_val)

    # val_metrics = confiances telles qu'elles seront SERVIES : la tête
    # candidate est construite EN MÉMOIRE et évaluée via `EmbedHead.predict`
    # ligne à ligne — la SEULE porte de sortie d'une confiance de tête
    # (§5.2bis) ; AUCUN miroir de la chaîne dans ce module (correction
    # ronde 1 : ML-R6r0-m1 = ES-R6r0-m1 = DQ-R6-m2). Indicatif seulement —
    # l'éval qui fait foi est `harness_embed` sur le set canonique (règle
    # héritée minor dq R5-r0).
    tete = EmbedHead(
        [[float(v) for v in ligne] for ligne in poids],
        [float(v) for v in biais],
        calib_x,
        calib_y,
        CONFIDENCE_CAP_V0,
    )
    pred_servies: list[int] = []
    conf_emises: list[float] = []
    for row in val_rows:
        label, conf = tete.predict(list(row.embedding))
        pred_servies.append(label_index[label])
        conf_emises.append(conf)
    val_metrics = _metrics_val(y_val, pred_servies, conf_emises)

    out_dir.mkdir(parents=True, exist_ok=True)
    head_path = out_dir / "head.json"
    calibrator_path = out_dir / "calibrator.json"
    metadata_path = out_dir / "metadata.json"

    head = {
        "w": [[float(v) for v in ligne] for ligne in poids],
        "b": [float(v) for v in biais],
    }
    head_path.write_text(json.dumps(head) + "\n", encoding="utf-8")
    sha_head = hashlib.sha256(head_path.read_bytes()).hexdigest()

    calibrator = {
        "method": "isotonic_top_conservative",
        "fit_on": "val",
        "n_fit": len(conf_brutes),
        "x": calib_x,
        "y": calib_y,
    }
    calibrator_path.write_text(json.dumps(calibrator, indent=2) + "\n", encoding="utf-8")
    sha_calibrator = hashlib.sha256(calibrator_path.read_bytes()).hexdigest()

    def _dist(rows_part: list[EmbedFixture]) -> dict[str, int]:
        return {label: sum(1 for r in rows_part if r.label == label) for label in LABEL_ORDER}

    metadata = {
        "artefact": "embed_head_v0",
        # Statut D4 consigné DANS l'artefact — honnêteté d'évaluation R5.
        "statut": STATUT_V0,
        "date_train": datetime.now(tz=UTC).isoformat(),
        "seed": seed,
        "git_sha": _git_sha(),
        "train_source": "synthetic_embed_fixtures",
        "train_seed": TRAIN_SEED,
        "eval_seed": EVAL_SEED,
        "n_train": len(train_rows),
        "n_val": len(val_rows),
        "dist_train": _dist(train_rows),
        "dist_val": _dist(val_rows),
        "fixtures": {"sigma": DEFAULT_SIGMA, "n_total": len(rows)},
        "hyperparametres": {
            "learning_rate": _LEARNING_RATE,
            "n_iterations": _N_ITERATIONS,
            "l2": _L2,
            "val_pct": _VAL_PCT,
        },
        "versions": {"python": platform.python_version(), "numpy": numpy.__version__},
        "label_mapping": {label: index for index, label in enumerate(LABEL_ORDER)},
        # Constructeur UNIQUE (§6.1) : le MÊME dict que la garde de dérive de
        # `EmbedHead.load` — identique par construction.
        "embed_spec": expected_embed_spec(),
        "calibration": {"method": "isotonic_top_conservative", "n_points": len(calib_x)},
        "confidence_cap": CONFIDENCE_CAP_V0,
        "val_metrics": val_metrics,
        "sha256_head_json": sha_head,
        "sha256_calibrator_json": sha_calibrator,
        "head_reelle_attend_telemetrie_v1": True,
    }
    metadata_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    return {
        "out_dir": out_dir,
        "n_train": len(train_rows),
        "n_val": len(val_rows),
        "calibration_n_points": len(calib_x),
        "val_metrics": val_metrics,
        "sha256_head_json": sha_head,
        "sha256_calibrator_json": sha_calibrator,
    }


def main(argv: list[str] | None = None) -> int:
    """CLI — sortie : nombres/chemins/hash uniquement ; refus propres exit 2."""
    parser = argparse.ArgumentParser(
        description=(
            "Entraîne la tête v0 de l'étage 2 sur embeddings synthétiques (chantier R6, D4)."
        )
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="répertoire candidat (défaut : router/artifacts/embed/heads/candidate)",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="graine numpy")
    args = parser.parse_args(argv)

    out_dir = args.out_dir if args.out_dir is not None else CANDIDATE_HEAD_DIR

    try:
        resume = run_training(out_dir, seed=args.seed)
    except RefusError as exc:
        print(f"REFUS : {exc}", file=sys.stderr)
        return 2

    vm = resume["val_metrics"]
    print(f"split : {resume['n_train']} train / {resume['n_val']} val")
    print(f"calibration : {resume['calibration_n_points']} points de contrôle")
    print(
        f"val (indicatif — l'éval qui fait foi est harness_embed) : "
        f"exactitude_ponderee {vm['exactitude_ponderee']:.4f} · "
        f"sous {vm['sous_dimensionnement']['taux']:.4f} · ece {vm['ece']:.4f} · "
        f"bande n={vm['calibration_bande_auto']['n']}"
    )
    taille = sum(
        (out_dir / nom).stat().st_size for nom in ("head.json", "calibrator.json", "metadata.json")
    )
    print(f"artefact : {out_dir} ({taille} octets)")
    print(f"sha256 head.json : {resume['sha256_head_json']}")
    print(f"sha256 calibrator.json : {resume['sha256_calibrator_json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
