"""Tests de `MLRouter` (`sobrio_router/ml.py`, chantier R5 §7) sur artefact RÉEL.

La fixture session `artefact_v05` (conftest.py) entraîne UNE fois via les
fonctions réelles de `train_v05` sur le corpus de référence. Couvre : contrat
de sortie, budgets MESURÉS (p95 < 5 ms, artefact < 20 Mo), déterminisme
bit-exact de l'entraînement, propriété conservatrice de la calibration (§6)
et chargement fail-closed (chaque corruption -> `MLRouterLoadError`, jamais
une autre exception).
"""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from pathlib import Path

import pytest
from conftest_helpers import make_signals

from sobrio_router import VISIBLE_MODELS
from sobrio_router.ml import MLRouter, MLRouterLoadError

pytest.importorskip("lightgbm")


def _signals_varies(n: int = 50):
    """`n` jeux de signaux variés (longueurs, langues, flags, conversation)."""
    langs = ("fr", "en", "other")
    flags_options = ((), ("code",), ("resume",), ("contrat", "analyse"), ("traduction",))
    models = (None, "claude-haiku-4-5", "claude-sonnet-5", "claude-opus-4-8", "claude-fable-5")
    return [
        make_signals(
            char_len=20 + 90 * i,
            token_est=5 + 40 * i,
            lang=langs[i % 3],
            has_code=i % 4 == 0,
            has_math=i % 5 == 0,
            keyword_flags=flags_options[i % 5],
            msg_count=(i * 3) % 40,
            context_token_est=(i * 217) % 9000,
            seen_code=i % 3 == 0,
            seen_math=i % 7 == 0,
            seen_reasoning=i % 6 == 0,
            current_model=models[i % 5],
            recos_shown=i % 8,
            recos_followed=i % 5,
            derogations_up=i % 4,
        )
        for i in range(n)
    ]


def test_decide_contrat(artefact_v05: Path):
    """Sur 50 Signals variés : modèle VISIBLE, confiance [0, 1], rule constant."""
    router = MLRouter(artefact_v05)
    for signals in _signals_varies(50):
        decision = router.decide(signals)
        assert decision.model in VISIBLE_MODELS
        assert 0.0 <= decision.confidence <= 1.0
        assert decision.rule == "ml:v05"


def test_latence_p95_unitaire(artefact_v05: Path):
    """Budget §7 MESURÉ : p95 de 200 `decide()` unitaires < 5 ms."""
    router = MLRouter(artefact_v05)
    signals = _signals_varies(50)
    latences = []
    for i in range(200):
        start = time.perf_counter()
        router.decide(signals[i % len(signals)])
        latences.append((time.perf_counter() - start) * 1000)
    latences.sort()
    p95 = latences[int(len(latences) * 0.95)]
    assert p95 < 5.0, f"p95 {p95:.4f} ms >= budget 5 ms"


def test_taille_artefact(artefact_v05: Path):
    """Budget §7 : somme des octets du dossier artefact < 20 Mo."""
    total = sum(p.stat().st_size for p in artefact_v05.iterdir() if p.is_file())
    assert total < 20 * 1024 * 1024, f"artefact {total} octets >= 20 Mo"


def test_determinisme_train(tmp_path: Path):
    """DEUX entraînements complets même seed -> model.txt et calibrator.json IDENTIQUES."""
    import train_v05

    out_a = tmp_path / "run-a"
    out_b = tmp_path / "run-b"
    train_v05.run_training(train_v05.DEFAULT_CORPUS_PATH, out_a)
    train_v05.run_training(train_v05.DEFAULT_CORPUS_PATH, out_b)
    sha_a = hashlib.sha256((out_a / "model.txt").read_bytes()).hexdigest()
    sha_b = hashlib.sha256((out_b / "model.txt").read_bytes()).hexdigest()
    assert sha_a == sha_b
    assert (out_a / "calibrator.json").read_bytes() == (out_b / "calibrator.json").read_bytes()


def test_confiance_conservatrice(artefact_v05: Path):
    """Propriété §6 : confiance émise <= proba top BRUTE (comparaison au booster direct)."""
    import lightgbm as lgb

    from sobrio_router.features import signals_to_vector

    router = MLRouter(artefact_v05)
    booster = lgb.Booster(model_file=str(artefact_v05 / "model.txt"))
    for signals in _signals_varies(50):
        decision = router.decide(signals)
        proba = booster.predict([signals_to_vector(signals)], num_threads=1)[0]
        raw = float(proba.max())
        assert decision.confidence <= raw + 1e-12, (decision.confidence, raw)


def _corrompre_calibrator(directory: Path, mutation: dict) -> None:
    """Mute calibrator.json ET met à jour son sha dans metadata (pour atteindre
    la VALIDATION du calibrateur, pas la garde d'intégrité en amont)."""
    calibrator_path = directory / "calibrator.json"
    calibrator = json.loads(calibrator_path.read_text(encoding="utf-8"))
    calibrator.update(mutation)
    calibrator_path.write_text(json.dumps(calibrator), encoding="utf-8")
    metadata_path = directory / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["sha256_calibrator_json"] = hashlib.sha256(calibrator_path.read_bytes()).hexdigest()
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")


def _muter_metadata(directory: Path, cle: str, valeur: object) -> None:
    metadata_path = directory / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata[cle] = valeur
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")


def _tronquer_model_txt(directory: Path) -> None:
    """Tronque model.txt SANS toucher au sha consigné : la garde d'INTÉGRITÉ
    (sha metadata != octets) refuse AVANT tout passage au parseur C++ de
    LightGBM — c'est précisément son rôle : nourrir le Booster d'octets
    corrompus peut ABORT le processus entier (constaté sur ce poste), il ne
    doit jamais voir un fichier dont le hash ne correspond pas."""
    model_path = directory / "model.txt"
    model_path.write_bytes(model_path.read_bytes()[:1024])


def _malformer_calibrator(directory: Path) -> None:
    """calibrator.json non-JSON, sha réparé : atteint l'échec de PARSE du calibrateur."""
    (directory / "calibrator.json").write_text("{pas du json", encoding="utf-8")
    _muter_metadata(
        directory,
        "sha256_calibrator_json",
        hashlib.sha256((directory / "calibrator.json").read_bytes()).hexdigest(),
    )


_CORRUPTIONS = {
    "dossier_absent": lambda d: shutil.rmtree(d),
    "model_txt_tronque": _tronquer_model_txt,
    "calibrator_x_decroissant": lambda d: _corrompre_calibrator(
        d, {"x": [0.9, 0.5, 0.1], "y": [0.1, 0.5, 0.9]}
    ),
    "calibrator_y_hors_bornes": lambda d: _corrompre_calibrator(
        d, {"x": [0.1, 0.5, 0.9], "y": [0.1, 0.5, 1.9]}
    ),
    "calibrator_longueurs_inegales": lambda d: _corrompre_calibrator(
        d, {"x": [0.1, 0.5, 0.9], "y": [0.1, 0.5]}
    ),
    "calibrator_malforme": _malformer_calibrator,
    "feature_spec_deviant": lambda d: _muter_metadata(
        d, "feature_spec", {"names": ["char_len", "intrus"], "version": "1"}
    ),
    "label_mapping_deviant": lambda d: _muter_metadata(
        d, "label_mapping", {"claude-haiku-4-5": 2, "claude-sonnet-5": 1, "claude-opus-4-8": 0}
    ),
    "sha_metadata_deviant": lambda d: _muter_metadata(d, "sha256_model_txt", "0" * 64),
}


@pytest.mark.parametrize("cas", sorted(_CORRUPTIONS), ids=str)
def test_chargement_fail_closed(artefact_v05: Path, tmp_path: Path, cas: str):
    """Chaque corruption -> `MLRouterLoadError` à la CONSTRUCTION, jamais autre chose."""
    directory = tmp_path / cas
    shutil.copytree(artefact_v05, directory)
    _CORRUPTIONS[cas](directory)
    with pytest.raises(MLRouterLoadError):
        MLRouter(directory)
