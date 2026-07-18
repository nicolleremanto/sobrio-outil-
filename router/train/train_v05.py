"""Entraînement du candidat v0.5 (ml_v05) — LightGBM déterministe, spec R5 §3-§6.

Pipeline : corpus de référence 30k (épinglé par sha256) -> split par
SIGNATURE canonique (`loader.signal_signature`, l'UNIQUE source de vérité —
aucun groupe de doublons jamais scindé, par construction) -> LightGBM
multiclass paramètres FIGÉS (§4.2, déterministe bit-exact entre runs) ->
calibration isotonique top-conf CONSERVATRICE (§6, appliquée en
`min(brut, iso(brut))`) -> artefacts `candidate/` (model.txt,
calibrator.json, metadata.json EN DERNIER).

Le train LIT UNIQUEMENT le fichier de hash committé du golden
(`GOLDEN_SHA256`, provenance metadata) — JAMAIS le set golden lui-même
(anti-fuite §3 : l'éval finale passe par `make router-eval
ROUTER=ml_v05_candidate`, le juge de paix reste le gate R3).

Validations FAIL-CLOSED (exit 2, `REFUS : …`, style `generate_corpus.py`) :
corpus introuvable/dérivé du sha de référence, hash golden absent/malformé,
split déséquilibré (garde de stratification §3.5). Aucun réseau (garde regex
R4 étendue à `router/train/`). Dépense : 0,00 $.

Module autonome (même convention que `router/eval/harness.py`) : insère
`router/eval/` dans `sys.path` pour importer `loader` (signature canonique)
et `harness` (métriques — zéro réimplémentation).
"""

from __future__ import annotations

import argparse
import gzip
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

from harness import _auto_band_calibration, compute_ece, weighted_accuracy  # noqa: E402
from loader import signal_signature  # noqa: E402

from sobrio_router.features import (  # noqa: E402
    CURRENT_MODEL_RANK,
    FEATURE_NAMES,
    FLAG_VOCAB,
    LANGS,
    signals_to_vector,
)
from sobrio_router.ml import CANDIDATE_DIR, LABEL_ORDER, interp_conf  # noqa: E402
from sobrio_router.types import ConversationSignals, PromptSignals, Signals  # noqa: E402

DEFAULT_SEED = 4242
DEFAULT_VAL_PCT = 15
# Garde de stratification §3.5 : écart max toléré entre parts de classe
# train/val (3 points ; mesuré ≈ 0,6 point sur le corpus de référence).
_STRATIFICATION_TOL = 0.03

# Chemins par défaut — constantes de module (monkeypatchables par les tests,
# lues à l'appel, jamais figées dans une signature).
DEFAULT_CORPUS_PATH = _ROUTER_DIR / "data" / "artifacts" / "corpus-v1.jsonl.gz"
REFERENCE_METADATA_PATH = _ROUTER_DIR / "data" / "reference" / "corpus-v1.metadata.json"
GOLDEN_SHA_PATH = _ROUTER_DIR / "eval" / "golden" / "GOLDEN_SHA256"

# Paramètres LightGBM ÉPINGLÉS (§4.2) — ne PAS retuner sans nouvelle ronde.
PARAMS = {
    "objective": "multiclass",
    "num_class": 3,
    "metric": "multi_logloss",
    "learning_rate": 0.08,
    "num_leaves": 31,
    "max_depth": 6,
    "min_data_in_leaf": 50,
    "feature_fraction": 0.9,
    "bagging_fraction": 0.9,
    "bagging_freq": 1,
    "lambda_l2": 1.0,
    "seed": 4242,
    "deterministic": True,
    "force_row_wise": True,
    "num_threads": 1,
    "verbose": -1,
}
NUM_BOOST_ROUND_MAX = 600
EARLY_STOPPING_ROUNDS = 50


class RefusError(RuntimeError):
    """Validation fail-closed : la CLI imprime `REFUS : …` et sort en 2."""


def _lire_golden_sha() -> str:
    """LIT le hash canonique committé (1er champ, 64 hex) — provenance metadata.

    REFUS si absent/malformé. Le train ne lit JAMAIS le set golden lui-même
    (prouvé par test : entraînement complet avec le set ABSENT du disque).
    """
    try:
        champs = GOLDEN_SHA_PATH.read_text(encoding="utf-8").split()
    except OSError as exc:
        raise RefusError(f"hash golden illisible : {GOLDEN_SHA_PATH} ({exc})") from exc
    if not champs or len(champs[0]) != 64 or any(c not in "0123456789abcdef" for c in champs[0]):
        raise RefusError(f"hash golden malformé : {GOLDEN_SHA_PATH}")
    return champs[0]


def _charger_corpus_epingle(corpus_path: Path) -> tuple[list[dict], str]:
    """Charge le corpus .gz et VÉRIFIE son sha256 contre la référence R4.

    Épinglage sans contournement : pour changer de corpus, on régénère la
    référence via `make router-corpus` (§4.1).
    """
    try:
        octets = corpus_path.read_bytes()
    except OSError as exc:
        raise RefusError(f"corpus introuvable ou illisible : {corpus_path} ({exc})") from exc
    sha = hashlib.sha256(octets).hexdigest()
    try:
        reference = json.loads(REFERENCE_METADATA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RefusError(f"référence corpus illisible : {REFERENCE_METADATA_PATH} ({exc})") from exc
    attendu = reference.get("sha256_gz")
    if sha != attendu:
        raise RefusError(
            f"corpus dérivé : sha256 {sha[:12]}… != référence {str(attendu)[:12]}… "
            "(régénérer via make router-corpus)"
        )
    try:
        lignes = gzip.decompress(octets).decode("utf-8").splitlines()
        rows = [json.loads(ligne) for ligne in lignes if ligne.strip()]
    except (OSError, ValueError) as exc:
        raise RefusError(f"corpus corrompu : {corpus_path} ({exc})") from exc
    return rows, sha


def split_by_signature(
    rows: list[dict], val_pct: int = DEFAULT_VAL_PCT
) -> tuple[list[dict], list[dict]]:
    """Split train/val PAR SIGNATURE canonique (§3) — déterministe, sans RNG.

    Toutes les lignes d'une même signature partagent le bucket
    (`sha256(repr(sig)) % 100`) : aucun groupe de doublons/contradictions
    n'est JAMAIS scindé, par construction. Itération dans l'ORDRE DU FICHIER
    (aucun ensemble non trié). Les groupes multi-lignes sont conservés
    entiers, TOUTES lignes comprises (la multiplicité est le poids réel du
    mode ; les contradictions-bruit restent du bruit contrôlé d'un seul côté).
    """
    train_rows: list[dict] = []
    val_rows: list[dict] = []
    for row in rows:
        sig = signal_signature(row["signals"]["prompt"], row["signals"]["conversation"])
        bucket = int(hashlib.sha256(repr(sig).encode("utf-8")).hexdigest(), 16) % 100
        (val_rows if bucket < val_pct else train_rows).append(row)
    return train_rows, val_rows


def verifier_stratification(train_rows: list[dict], val_rows: list[dict]) -> dict[str, float]:
    """Garde-fou a posteriori §3.5 : REFUS si une part de classe dévie de > 3 points.

    Retourne les écarts par label (diagnostic). Pas de stratification
    explicite : le hash est déterministe, sans état, indépendant de l'ordre.
    """
    ecarts: dict[str, float] = {}
    n_train, n_val = len(train_rows), len(val_rows)
    if n_train == 0 or n_val == 0:
        raise RefusError(f"split déséquilibré : partition vide (train {n_train} / val {n_val})")
    for label in LABEL_ORDER:
        part_train = sum(1 for r in train_rows if r["label"] == label) / n_train
        part_val = sum(1 for r in val_rows if r["label"] == label) / n_val
        ecarts[label] = abs(part_val - part_train)
    pire = max(ecarts.values())
    if pire > _STRATIFICATION_TOL:
        raise RefusError(
            f"split déséquilibré : écart de classe max {pire:.4f} > {_STRATIFICATION_TOL} "
            f"({ {k: round(v, 4) for k, v in ecarts.items()} })"
        )
    return ecarts


def _vectoriser(rows: list[dict]) -> tuple[list[list[float]], list[int]]:
    """Lignes corpus -> (X, y) via `signals_to_vector` (le MÊME encodeur qu'en prod)."""
    label_index = {label: index for index, label in enumerate(LABEL_ORDER)}
    features: list[list[float]] = []
    labels: list[int] = []
    for row in rows:
        label = row["label"]
        if label not in label_index:
            raise RefusError(f"étiquette hors catalogue visible dans le corpus : {label!r}")
        prompt = PromptSignals(**row["signals"]["prompt"])
        conversation = ConversationSignals(**row["signals"]["conversation"])
        features.append(signals_to_vector(Signals(prompt=prompt, conversation=conversation)))
        labels.append(label_index[label])
    return features, labels


def compute_class_weights(y_train: list[int]) -> dict[int, float]:
    """`balanced` calculé sur le TRAIN (§4.3) : w_k = n_train / (3 * n_train_k)."""
    n_train = len(y_train)
    counts = {k: y_train.count(k) for k in range(len(LABEL_ORDER))}
    if any(count == 0 for count in counts.values()):
        raise RefusError(f"classe absente du train : effectifs {counts}")
    return {k: n_train / (len(LABEL_ORDER) * counts[k]) for k in counts}


def fit_isotonic(conf_val: list[float], correct_val: list[bool]) -> tuple[list[float], list[float]]:
    """PAV (pool adjacent violators) sur (confiance top brute, correct) de la val (§6).

    Retourne les points de contrôle en escalier `(x[], y[])` : x strictement
    croissant, 2 points par bloc PAV (bornes min/max — les points internes
    d'un bloc sont colinéaires, inutiles à l'interpolation linéaire). Les
    égalités de x sont agrégées AVANT le PAV (moyenne pondérée) : x reste
    strictement croissant, l'interpolation est bien définie.
    """
    if len(conf_val) != len(correct_val) or len(conf_val) < 2:
        raise RefusError(f"calibration : {len(conf_val)} points de val, minimum 2")
    agreges: dict[float, list[float]] = {}
    for conf, correct in zip(conf_val, correct_val, strict=True):
        cell = agreges.setdefault(float(conf), [0.0, 0.0])
        cell[0] += 1.0 if correct else 0.0
        cell[1] += 1.0
    # blocs PAV : [somme_y, poids, x_min, x_max] — fusion tant que la moyenne
    # du bloc précédent est >= celle du dernier (monotonie non décroissante).
    blocs: list[list[float]] = []
    for x in sorted(agreges):
        somme, poids = agreges[x]
        blocs.append([somme, poids, x, x])
        while len(blocs) >= 2 and blocs[-2][0] * blocs[-1][1] >= blocs[-1][0] * blocs[-2][1]:
            s2, w2, _x2min, x2max = blocs.pop()
            s1, w1, x1min, _x1max = blocs.pop()
            blocs.append([s1 + s2, w1 + w2, x1min, x2max])
    xs: list[float] = []
    ys: list[float] = []
    for somme, poids, x_min, x_max in blocs:
        valeur = somme / poids
        xs.append(x_min)
        ys.append(valeur)
        if x_max > x_min:
            xs.append(x_max)
            ys.append(valeur)
    if len(xs) < 2:
        # Refus AU TRAIN (minor qa R5 r0) : un calibrateur à < 2 points est
        # inutilisable (interpolation impossible) — le chargeur le refusait
        # déjà, mais échouer ICI donne le diagnostic au bon moment.
        # RefusError (major eval r1) : la ValueError initiale échappait au
        # try/except de main() → traceback brut exit 1, en contradiction avec
        # le contrat CLI du module et la garde JUMELLE 30 lignes plus haut.
        raise RefusError(
            f"calibrateur isotonique dégénéré ({len(xs)} point de contrôle) — "
            "val trop petite ou confiances constantes, entraînement refusé"
        )
    return xs, ys


def _metrics_val(
    y_val: list[int], pred_idx: list[int], conf_emises: list[float], best_iteration: int
) -> dict:
    """Métriques §4.4 sur la VAL — mêmes définitions que le harnais (imports directs)."""
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
        "best_iteration": best_iteration,
    }


def run_training(
    corpus_path: Path,
    out_dir: Path,
    seed: int = DEFAULT_SEED,
    val_pct: int = DEFAULT_VAL_PCT,
) -> dict:
    """Pipeline complet §4 : validations, split, LightGBM, calibration, artefacts.

    Retourne un résumé (chemins, hash, métriques val). Lève `RefusError` sur
    toute validation fail-closed. Ordre d'écriture : model.txt ->
    calibrator.json -> metadata.json EN DERNIER (sa présence marque un
    artefact complet — le chargeur exige les trois).
    """
    # Dépendances d'ENTRAÎNEMENT (router/requirements-ml.txt), importées ici
    # PARESSEUSEMENT : le module reste importable sans elles (les fonctions
    # pures — split, PAV, gardes — se testent sans lightgbm).
    import lightgbm as lgb
    import numpy

    golden_sha = _lire_golden_sha()
    rows, corpus_sha = _charger_corpus_epingle(corpus_path)

    train_rows, val_rows = split_by_signature(rows, val_pct)
    verifier_stratification(train_rows, val_rows)

    x_train, y_train = _vectoriser(train_rows)
    x_val, y_val = _vectoriser(val_rows)
    class_weights = compute_class_weights(y_train)
    poids_train = [class_weights[y] for y in y_train]
    # Val d'early stopping PONDÉRÉE avec les MÊMES poids de classe (§4.2) :
    # critère de sélection aligné sur le coût asymétrique du gate.
    poids_val = [class_weights[y] for y in y_val]

    params = dict(PARAMS)
    params["seed"] = seed
    # numpy : uniquement pour matérialiser les matrices attendues par
    # lgb.Dataset (dtype float64 explicite — déterminisme §5.6).
    x_train_mat = numpy.asarray(x_train, dtype=numpy.float64)
    x_val_mat = numpy.asarray(x_val, dtype=numpy.float64)
    train_set = lgb.Dataset(
        x_train_mat, label=y_train, weight=poids_train, feature_name=list(FEATURE_NAMES)
    )
    val_set = train_set.create_valid(x_val_mat, label=y_val, weight=poids_val)
    booster = lgb.train(
        params,
        train_set,
        num_boost_round=NUM_BOOST_ROUND_MAX,
        valid_sets=[val_set],
        valid_names=["val"],
        callbacks=[
            lgb.early_stopping(stopping_rounds=EARLY_STOPPING_ROUNDS, verbose=False),
            lgb.log_evaluation(period=0),
        ],
    )
    best_iteration = int(booster.best_iteration or NUM_BOOST_ROUND_MAX)

    # Calibration isotonique CONSERVATRICE (§6) : ajustée sur la val, émise
    # en min(brut, iso(brut)) — jamais de confiance au-dessus de la brute.
    probas_val = booster.predict(x_val_mat, num_iteration=best_iteration, num_threads=1)
    pred_idx = [int(p.argmax()) for p in probas_val]
    conf_brutes = [float(p[i]) for p, i in zip(probas_val, pred_idx, strict=True)]
    corrects = [p == y for p, y in zip(pred_idx, y_val, strict=True)]
    calib_x, calib_y = fit_isotonic(conf_brutes, corrects)
    conf_emises = [
        min(1.0, max(0.0, min(raw, interp_conf(raw, calib_x, calib_y)))) for raw in conf_brutes
    ]

    val_metrics = _metrics_val(y_val, pred_idx, conf_emises, best_iteration)

    out_dir.mkdir(parents=True, exist_ok=True)
    model_path = out_dir / "model.txt"
    calibrator_path = out_dir / "calibrator.json"
    metadata_path = out_dir / "metadata.json"

    booster.save_model(str(model_path), num_iteration=best_iteration)
    sha_model = hashlib.sha256(model_path.read_bytes()).hexdigest()

    calibrator = {
        "method": "isotonic_top_conservative",
        "fit_on": "val",
        "n_fit": len(conf_brutes),
        "x": calib_x,
        "y": calib_y,
    }
    calibrator_path.write_text(json.dumps(calibrator, indent=2) + "\n", encoding="utf-8")
    sha_calibrator = hashlib.sha256(calibrator_path.read_bytes()).hexdigest()

    def _dist(rows_part: list[dict]) -> dict[str, int]:
        return {label: sum(1 for r in rows_part if r["label"] == label) for label in LABEL_ORDER}

    metadata = {
        "schema_version": "1",
        "artifact": "ml_v05",
        "date_train": datetime.now(tz=UTC).isoformat(),
        "seed": seed,
        "corpus_path_basename": corpus_path.name,
        "corpus_sha256_gz": corpus_sha,
        "corpus_n": len(rows),
        "golden_sha": golden_sha,
        "versions": {
            "python": platform.python_version(),
            "lightgbm": lgb.__version__,
            "numpy": numpy.__version__,
        },
        "label_mapping": {label: index for index, label in enumerate(LABEL_ORDER)},
        "feature_spec": {
            "names": list(FEATURE_NAMES),
            "langs": list(LANGS),
            "flag_vocab": list(FLAG_VOCAB),
            # clé JSON : None (fil vierge) est sérialisé "null" (vocabulaire
            # système — une clé JSON ne peut pas être nulle).
            "current_model_rank": {
                ("null" if model is None else model): rank
                for model, rank in CURRENT_MODEL_RANK.items()
            },
            "version": "1",
        },
        "split": {
            "method": "signature_sha256_mod100",
            "val_pct": val_pct,
            "n_train": len(train_rows),
            "n_val": len(val_rows),
            "dist_train": _dist(train_rows),
            "dist_val": _dist(val_rows),
        },
        "class_weights": {LABEL_ORDER[k]: round(w, 6) for k, w in class_weights.items()},
        "params": params,
        "num_boost_round_max": NUM_BOOST_ROUND_MAX,
        "early_stopping_rounds": EARLY_STOPPING_ROUNDS,
        "best_iteration": best_iteration,
        "calibration": {"method": "isotonic_top_conservative", "n_points": len(calib_x)},
        "val_metrics": val_metrics,
        "sha256_model_txt": sha_model,
        "sha256_calibrator_json": sha_calibrator,
    }
    metadata_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    return {
        "out_dir": out_dir,
        "model_path": model_path,
        "sha256_model_txt": sha_model,
        "sha256_calibrator_json": sha_calibrator,
        "best_iteration": best_iteration,
        "n_train": len(train_rows),
        "n_val": len(val_rows),
        "class_weights": metadata["class_weights"],
        "calibration_n_points": len(calib_x),
        "val_metrics": val_metrics,
    }


def main(argv: list[str] | None = None) -> int:
    """CLI — sortie : nombres/chemins/hash uniquement ; refus propres exit 2."""
    parser = argparse.ArgumentParser(
        description="Entraîne le candidat ml_v05 depuis le corpus de référence (chantier R5)."
    )
    parser.add_argument(
        "--corpus",
        type=Path,
        default=None,
        help="corpus .jsonl.gz épinglé (défaut : router/data/artifacts/corpus-v1.jsonl.gz)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="répertoire candidat (défaut : router/artifacts/models/candidate)",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="graine LightGBM")
    parser.add_argument(
        "--val-pct", type=int, default=DEFAULT_VAL_PCT, help="pourcent de buckets en val (0-99)"
    )
    args = parser.parse_args(argv)

    if not (0 < args.val_pct < 100):
        print(f"REFUS : --val-pct doit être dans [1, 99] (reçu {args.val_pct})", file=sys.stderr)
        return 2

    corpus_path = args.corpus if args.corpus is not None else DEFAULT_CORPUS_PATH
    out_dir = args.out_dir if args.out_dir is not None else CANDIDATE_DIR

    try:
        resume = run_training(corpus_path, out_dir, seed=args.seed, val_pct=args.val_pct)
    except RefusError as exc:
        print(f"REFUS : {exc}", file=sys.stderr)
        return 2

    vm = resume["val_metrics"]
    print(f"split : {resume['n_train']} train / {resume['n_val']} val")
    print(f"class_weights : {resume['class_weights']}")
    print(f"best_iteration : {resume['best_iteration']}")
    print(f"calibration : {resume['calibration_n_points']} points de contrôle")
    print(
        f"val : exactitude_ponderee {vm['exactitude_ponderee']:.4f} · "
        f"sous {vm['sous_dimensionnement']['taux']:.4f} · ece {vm['ece']:.4f} · "
        f"bande ecart {vm['calibration_bande_auto']['ecart']:.4f} "
        f"(n={vm['calibration_bande_auto']['n']})"
    )
    taille = sum((out_dir / n).stat().st_size for n in ("model.txt", "calibrator.json"))
    taille += (out_dir / "metadata.json").stat().st_size
    print(f"artefact : {out_dir} ({taille} octets)")
    print(f"sha256 model.txt : {resume['sha256_model_txt']}")
    print(f"sha256 calibrator.json : {resume['sha256_calibrator_json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
