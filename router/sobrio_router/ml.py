"""MLRouter — étage 1 v0.5 : LightGBM + calibration conservatrice (spec R5 §7).

TOUJOURS derrière `SafeRouter` en production (invariant §5.2) : les échecs de
chargement arrivent À LA CONSTRUCTION (`MLRouterLoadError`), exactement là où
`api/app/router_bridge.py` les guette (`try/except` -> `SafeRouter(primary=None)`).
`decide()` PEUT lever (proba invalide) : c'est VOULU — SafeRouter attrape.

Import de lightgbm PARESSEUX, à l'intérieur de `__init__` — JAMAIS au niveau
module : `sobrio_router` (y compris `from sobrio_router.ml import MLRouter`)
s'importe SANS lightgbm installé ; seule la CONSTRUCTION échoue alors (repli
bridge). Aucun import numpy direct (predict accepte une liste de listes).

Messages d'erreur = chemins/hash/nombres UNIQUEMENT, jamais de contenu
(invariant §5.1 — un artefact ou un message ne transporte aucun texte).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from bisect import bisect_right
from pathlib import Path

from .features import FEATURE_NAMES, expected_feature_spec, signals_to_vector
from .interface import Router
from .types import Decision, Signals

# index 0/1/2 = ordre de coût croissant, ALIGNÉ sur _MODEL_RANK du harnais
# (router/eval/harness.py). Le chargeur REFUSE tout artefact dont le
# label_mapping diffère (garde de dérive, §2).
LABEL_ORDER: tuple[str, ...] = ("claude-haiku-4-5", "claude-sonnet-5", "claude-opus-4-8")

# Valeur par défaut valide en installation éditable (venv racine).
PROMOTED_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "models" / "promoted"
CANDIDATE_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "models" / "candidate"

_PROMOTED_DIR_ENV = "SOBRIO_PROMOTED_DIR"
_N_FEATURES = len(FEATURE_NAMES)  # 22
_ARTIFACT_FILES = ("model.txt", "calibrator.json", "metadata.json")


class MLRouterLoadError(RuntimeError):
    """Échec de chargement d'un artefact ml_v05 (manquant, corrompu, dérivé)."""


def _validate_calibrator(calibrator: object, path: Path) -> tuple[list[float], list[float]]:
    """Valide le format §6 de calibrator.json ; retourne (x, y) prêts à interpoler."""
    if not isinstance(calibrator, dict):
        raise MLRouterLoadError(f"calibrator.json non-objet : {path}")
    xs = calibrator.get("x")
    ys = calibrator.get("y")
    if not isinstance(xs, list) or not isinstance(ys, list):
        raise MLRouterLoadError(f"calibrator.json : x/y absents ou non-listes : {path}")
    if len(xs) != len(ys) or len(xs) < 2:
        raise MLRouterLoadError(
            f"calibrator.json : longueurs x/y invalides ({len(xs)}/{len(ys)}) : {path}"
        )
    for value in (*xs, *ys):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            raise MLRouterLoadError(f"calibrator.json : valeur non finie : {path}")
    if any(b < a for a, b in zip(xs, xs[1:], strict=False)):
        raise MLRouterLoadError(f"calibrator.json : x non croissant : {path}")
    if any(not (0.0 <= float(v) <= 1.0) for v in ys):
        raise MLRouterLoadError(f"calibrator.json : y hors [0, 1] : {path}")
    return [float(v) for v in xs], [float(v) for v in ys]


def interp_conf(raw: float, xs: list[float], ys: list[float]) -> float:
    """Interpolation linéaire pure python sur les points de contrôle (§6).

    Même sémantique que `np.interp` (égalité vérifiée par l'architecte,
    diff 0.0) ; hors bornes : clamp aux valeurs extrêmes. Partagée avec
    `router/train/train_v05.py` (mêmes confiances émises train/serveur,
    zéro réimplémentation).
    """
    if raw <= xs[0]:
        return ys[0]
    if raw >= xs[-1]:
        return ys[-1]
    i = bisect_right(xs, raw)
    x0, x1 = xs[i - 1], xs[i]
    y0, y1 = ys[i - 1], ys[i]
    if x1 == x0:
        return y1
    return y0 + (y1 - y0) * (raw - x0) / (x1 - x0)


class MLRouter(Router):
    """Routeur LightGBM v0.5 : featurise, prédit, calibre — `rule="ml:v05"` constant.

    `rule` constant (pas de rule par motif) : un GBDT n'a pas de motif
    nommable honnête ; l'explicabilité fine (importances, contributions) est
    un chantier rapport/R7, pas un champ de contrat. `ml:` préfixe l'étage,
    `v05` la génération ; v1 émettra `ml:v1-<org>`. En repli, SafeRouter
    substitue `fallback:heuristic` comme aujourd'hui.
    """

    def __init__(self, artifact_dir: Path | str | None = None) -> None:
        # Lecture À LA CONSTRUCTION : un déploiement peut changer l'artefact
        # puis purger le cache du bridge sans réimporter ce module.
        if artifact_dir is None:
            surcharge = os.environ.get(_PROMOTED_DIR_ENV)
            if surcharge is not None and not surcharge.strip():
                # Une surcharge vide équivaut à une absence.
                surcharge = None
            directory = Path(surcharge) if surcharge is not None else PROMOTED_DIR
        else:
            directory = Path(artifact_dir)
        # Import PARESSEUX (§7.1) — lightgbm absent => MLRouterLoadError,
        # jamais un ImportError nu (le bridge et les tests s'y fient).
        try:
            import lightgbm as lgb
        except ImportError as exc:
            raise MLRouterLoadError(f"lightgbm indisponible : {exc.__class__.__name__}") from exc

        for name in _ARTIFACT_FILES:
            if not (directory / name).is_file():
                raise MLRouterLoadError(f"artefact incomplet : {directory / name} absent")

        model_path = directory / "model.txt"
        calibrator_path = directory / "calibrator.json"
        metadata_path = directory / "metadata.json"

        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MLRouterLoadError(
                f"metadata.json illisible : {metadata_path} ({exc.__class__.__name__})"
            ) from exc
        if not isinstance(metadata, dict):
            raise MLRouterLoadError(f"metadata.json non-objet : {metadata_path}")

        # Intégrité AVANT chargement : sha des octets == sha consignés.
        for filename, key in (
            ("model.txt", "sha256_model_txt"),
            ("calibrator.json", "sha256_calibrator_json"),
        ):
            expected = metadata.get(key)
            actual = hashlib.sha256((directory / filename).read_bytes()).hexdigest()
            if actual != expected:
                raise MLRouterLoadError(
                    f"integrite : {key} attendu {str(expected)[:12]} != octets {actual[:12]} "
                    f"({directory / filename})"
                )

        # Gardes de dérive artefact/code (§2 + §7.1).
        expected_mapping = {label: index for index, label in enumerate(LABEL_ORDER)}
        if metadata.get("label_mapping") != expected_mapping:
            raise MLRouterLoadError(f"label_mapping deviant : {metadata_path}")
        # Garde de dérive ÉTENDUE à l'INTÉGRALITÉ du feature_spec (minor ml
        # r3) : names + langs + flag_vocab + current_model_rank + version,
        # comparés au spec COURANT de features.py — même patron fail-closed
        # que label_mapping. Sans elle, un changement des VALEURS de rang de
        # CURRENT_MODEL_RANK entre l'entraînement d'un artefact et son
        # service chargerait l'ancien artefact avec une sémantique de feature
        # décalée. Le spec attendu vient du constructeur UNIQUE
        # `expected_feature_spec()` (minors ml+dq r4), le MÊME que celui
        # écrit par le train (§8.1) — identique par construction ; l'égalité
        # de dict refuse TOUT écart (clé absente, valeur modifiée, clé en
        # trop, non-dict).
        if metadata.get("feature_spec") != expected_feature_spec():
            raise MLRouterLoadError(f"feature_spec deviant : {metadata_path}")

        try:
            booster = lgb.Booster(model_file=str(model_path))
        except Exception as exc:  # lgb.basic.LightGBMError, OSError…
            raise MLRouterLoadError(
                f"model.txt invalide : {model_path} ({exc.__class__.__name__})"
            ) from exc
        if booster.num_feature() != _N_FEATURES:
            raise MLRouterLoadError(
                f"nombre de features {booster.num_feature()} != {_N_FEATURES} : {model_path}"
            )
        if booster.feature_name() != list(FEATURE_NAMES):
            raise MLRouterLoadError(f"feature_name() deviant : {model_path}")

        try:
            calibrator = json.loads(calibrator_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MLRouterLoadError(
                f"calibrator.json illisible : {calibrator_path} ({exc.__class__.__name__})"
            ) from exc
        self._calib_x, self._calib_y = _validate_calibrator(calibrator, calibrator_path)

        self._booster = booster

    def _interp(self, raw: float) -> float:
        """Confiance isotonique du point `raw` (délègue à `interp_conf`, §6)."""
        return interp_conf(raw, self._calib_x, self._calib_y)

    def decide(self, signals: Signals) -> Decision:
        vec = signals_to_vector(signals)  # features.py, pur stdlib
        proba = self._booster.predict([vec], num_threads=1)[0]  # shape (3,)
        if len(proba) != len(LABEL_ORDER) or any(not math.isfinite(float(p)) for p in proba):
            # SafeRouter attrape et replie (§5.2) — lever ici est VOULU.
            raise ValueError(f"proba invalide : {len(proba)} valeurs")
        idx = int(proba.argmax())
        raw = float(proba[idx])
        # Calibration CONSERVATRICE §6 : min(brut, iso(brut)) — la confiance
        # émise ne peut JAMAIS dépasser la brute (jamais créer d'auto-bascule
        # RFC-0003, seulement en retirer). Clamp [0, 1] défensif.
        conf = min(1.0, max(0.0, min(raw, self._interp(raw))))
        return Decision(model=LABEL_ORDER[idx], confidence=conf, rule="ml:v05")
