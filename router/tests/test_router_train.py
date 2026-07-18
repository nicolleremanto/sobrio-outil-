"""Tests du pipeline d'entraînement (`router/train/train_v05.py`, chantier R5 §3-§6).

Couvre : split par signature SANS fuite (recalcul indépendant), déterminisme
du split, garde de stratification (REFUS exit 2), preuve que le train ne lit
JAMAIS le set golden (exécution avec le fichier ABSENT), épinglage du corpus
(octet muté -> REFUS), zéro texte dans les artefacts (jurisprudence R4) et
metadata complet §8.1.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
from pathlib import Path

import pytest
import train_v05
from loader import signal_signature

from sobrio_router.features import FEATURE_NAMES
from sobrio_router.ml import LABEL_ORDER

_CORPUS_SHA_REFERENCE = "be96b691bbb29838668d7506e32d6d7e766e77f6b7a6be1defe17eaea38969ba"
_GOLDEN_DIR = Path(__file__).resolve().parents[1] / "eval" / "golden"

# Jurisprudence R4 (zéro texte) : chaîne système courte, jamais une phrase.
_CHAINE_SYSTEME_RE = re.compile(r"^[A-Za-z0-9_.:+\-/=% ]{1,120}$")


def _charger_corpus() -> list[dict]:
    payload = gzip.decompress(train_v05.DEFAULT_CORPUS_PATH.read_bytes()).decode("utf-8")
    return [json.loads(ligne) for ligne in payload.splitlines() if ligne.strip()]


@pytest.fixture(scope="module")
def corpus_rows() -> list[dict]:
    if not train_v05.DEFAULT_CORPUS_PATH.is_file():
        pytest.skip("corpus de référence absent — régénérer via make router-corpus")
    return _charger_corpus()


def test_split_aucune_fuite(corpus_rows: list[dict]):
    """Aucune signature des deux côtés (recalcul INDÉPENDANT sur la partition produite)."""
    train_rows, val_rows = train_v05.split_by_signature(corpus_rows)
    assert len(train_rows) + len(val_rows) == len(corpus_rows)

    def _sigs(rows: list[dict]) -> set[tuple]:
        return {
            signal_signature(r["signals"]["prompt"], r["signals"]["conversation"]) for r in rows
        }

    sigs_train, sigs_val = _sigs(train_rows), _sigs(val_rows)
    assert not (sigs_train & sigs_val), "fuite : signature présente des deux côtés"
    # Groupes multi-lignes ENTIERS : toutes les lignes du corpus portant une
    # signature donnée sont du même côté (conséquence directe, revérifiée).
    cote: dict[tuple, str] = {}
    for nom, rows in (("train", train_rows), ("val", val_rows)):
        for r in rows:
            sig = signal_signature(r["signals"]["prompt"], r["signals"]["conversation"])
            assert cote.setdefault(sig, nom) == nom, "groupe multi-lignes scindé"


def test_split_deterministe(corpus_rows: list[dict]):
    """Deux appels -> partitions strictement identiques (aucune RNG, aucun état)."""
    a_train, a_val = train_v05.split_by_signature(corpus_rows)
    b_train, b_val = train_v05.split_by_signature(corpus_rows)
    assert a_train == b_train
    assert a_val == b_val


def test_garde_stratification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
):
    """Split artificiellement déséquilibré (> 3 points) -> REFUS exit 2 (CLI)."""
    pytest.importorskip("lightgbm")

    def _split_desequilibre(rows: list[dict], val_pct: int = 15):
        # Toutes les lignes opus en val : la part de classe dévie largement.
        val = [r for r in rows if r["label"] == "claude-opus-4-8"]
        train = [r for r in rows if r["label"] != "claude-opus-4-8"]
        return train, val

    monkeypatch.setattr(train_v05, "split_by_signature", _split_desequilibre)
    code = train_v05.main(["--out-dir", str(tmp_path / "jamais-ecrit")])
    assert code == 2
    err = capsys.readouterr().err
    assert "REFUS" in err and "déséquilibré" in err
    # Unitaire : la garde elle-même lève bien au-delà de 3 points.
    rows = [{"label": label} for label in LABEL_ORDER] * 10
    with pytest.raises(train_v05.RefusError, match="déséquilibré"):
        train_v05.verifier_stratification(rows, [{"label": "claude-opus-4-8"}] * 10)


def test_train_ne_lit_jamais_golden(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Sandbox où le set golden est ABSENT (seul le fichier de hash présent) :
    l'entraînement ABOUTIT — le train ne lit que la provenance, jamais le set."""
    pytest.importorskip("lightgbm")
    sandbox = tmp_path / "golden-sandbox"
    sandbox.mkdir()
    (sandbox / "GOLDEN_SHA256").write_bytes((_GOLDEN_DIR / "GOLDEN_SHA256").read_bytes())
    # AUCUN autre fichier dans la sandbox : le set lui-même n'existe pas ici.
    monkeypatch.setattr(train_v05, "GOLDEN_SHA_PATH", sandbox / "GOLDEN_SHA256")
    resume = train_v05.run_training(train_v05.DEFAULT_CORPUS_PATH, tmp_path / "out")
    assert (tmp_path / "out" / "metadata.json").is_file()
    assert resume["best_iteration"] >= 1

    # Garde statique : la source du train ne référence jamais le fichier du
    # set (le GATE, lui, continue de l'épingler via loader — inchangé).
    source = Path(train_v05.__file__).read_text(encoding="utf-8")
    nom_fichier_set = "golden" + ".jsonl"  # concaténé pour ne pas s'auto-matcher
    assert nom_fichier_set not in source
    gate_source = (Path(train_v05.__file__).parents[1] / "eval" / "gate.py").read_text(
        encoding="utf-8"
    )
    assert "golden_sha256" in gate_source


def test_golden_sha_malforme_refuse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys):
    """Fichier de hash absent ou malformé (1er champ != 64 hex) -> REFUS exit 2."""
    mauvais = tmp_path / "GOLDEN_SHA256"
    mauvais.write_text("pasunhash\n", encoding="utf-8")
    monkeypatch.setattr(train_v05, "GOLDEN_SHA_PATH", mauvais)
    assert train_v05.main(["--out-dir", str(tmp_path / "out")]) == 2
    assert "REFUS" in capsys.readouterr().err
    monkeypatch.setattr(train_v05, "GOLDEN_SHA_PATH", tmp_path / "inexistant")
    assert train_v05.main(["--out-dir", str(tmp_path / "out")]) == 2
    assert "REFUS" in capsys.readouterr().err


def test_corpus_epingle(tmp_path: Path, capsys: pytest.CaptureFixture):
    """Corpus muté d'UN octet -> sha != référence -> REFUS exit 2 (aucun contournement)."""
    if not train_v05.DEFAULT_CORPUS_PATH.is_file():
        pytest.skip("corpus de référence absent — régénérer via make router-corpus")
    octets = bytearray(train_v05.DEFAULT_CORPUS_PATH.read_bytes())
    octets[len(octets) // 2] ^= 0x01
    mute = tmp_path / "corpus-mute.jsonl.gz"
    mute.write_bytes(bytes(octets))
    code = train_v05.main(["--corpus", str(mute), "--out-dir", str(tmp_path / "out")])
    assert code == 2
    err = capsys.readouterr().err
    assert "REFUS" in err and "sha256" in err
    assert not (tmp_path / "out").exists()


def _chaines(node: object):
    """Walk récursif : TOUTES les chaînes (clés ET valeurs) d'un JSON."""
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for key, value in node.items():
            yield from _chaines(key)
            yield from _chaines(value)
    elif isinstance(node, list):
        for value in node:
            yield from _chaines(value)


def test_zero_texte_artefacts(artefact_v05: Path):
    """Invariant §5.1 sur les ARTEFACTS : aucune chaîne qui ressemble à une phrase."""
    lgb = pytest.importorskip("lightgbm")
    for name in ("metadata.json", "calibrator.json"):
        document = json.loads((artefact_v05 / name).read_text(encoding="utf-8"))
        for chaine in _chaines(document):
            assert _CHAINE_SYSTEME_RE.match(chaine), f"{name} : chaîne suspecte {chaine!r}"
            assert chaine.count(" ") <= 6, f"{name} : trop d'espaces (prose ?) {chaine!r}"
    booster = lgb.Booster(model_file=str(artefact_v05 / "model.txt"))
    assert set(booster.feature_name()) <= set(FEATURE_NAMES)


def test_metadata_complet(artefact_v05: Path):
    """Toutes les clés §8.1, valeurs épinglées (corpus, golden, mapping, versions)."""
    lightgbm = pytest.importorskip("lightgbm")
    numpy = pytest.importorskip("numpy")
    metadata = json.loads((artefact_v05 / "metadata.json").read_text(encoding="utf-8"))
    cles_obligatoires = {
        "schema_version",
        "artifact",
        "date_train",
        "seed",
        "corpus_path_basename",
        "corpus_sha256_gz",
        "corpus_n",
        "golden_sha",
        "versions",
        "label_mapping",
        "feature_spec",
        "split",
        "class_weights",
        "params",
        "num_boost_round_max",
        "early_stopping_rounds",
        "best_iteration",
        "calibration",
        "val_metrics",
        "sha256_model_txt",
        "sha256_calibrator_json",
    }
    assert cles_obligatoires <= set(metadata)
    assert metadata["schema_version"] == "1"
    assert metadata["artifact"] == "ml_v05"
    assert metadata["seed"] == 4242
    assert metadata["corpus_sha256_gz"] == _CORPUS_SHA_REFERENCE
    assert metadata["golden_sha"] == (_GOLDEN_DIR / "GOLDEN_SHA256").read_text().split()[0]
    assert metadata["label_mapping"] == {label: i for i, label in enumerate(LABEL_ORDER)}
    assert metadata["feature_spec"]["names"] == list(FEATURE_NAMES)
    assert metadata["versions"]["lightgbm"] == lightgbm.__version__
    assert metadata["versions"]["numpy"] == numpy.__version__
    assert metadata["split"]["method"] == "signature_sha256_mod100"
    assert metadata["split"]["n_train"] + metadata["split"]["n_val"] == metadata["corpus_n"]
    assert metadata["calibration"]["method"] == "isotonic_top_conservative"
    assert 1 <= metadata["best_iteration"] <= metadata["num_boost_round_max"]
    # Intégrité consignée == octets réels.
    for filename, key in (
        ("model.txt", "sha256_model_txt"),
        ("calibrator.json", "sha256_calibrator_json"),
    ):
        assert hashlib.sha256((artefact_v05 / filename).read_bytes()).hexdigest() == metadata[key]


def test_fit_isotonic_refuses_degenerate_calibrator():
    """Minor qa R5 r0 : un calibrateur à < 2 points est refusé AU TRAIN
    (diagnostic au bon moment), plus seulement au chargement."""
    import pytest as _pytest

    with _pytest.raises(ValueError, match="dégénéré"):
        train_v05.fit_isotonic([0.8, 0.8, 0.8], [True, True, False])
