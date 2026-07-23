"""Tests du pipeline d'entraînement (`router/train/train_v05.py`, chantier R5 §3-§6).

Couvre : split par signature SANS fuite (recalcul indépendant), déterminisme
du split, garde de stratification (REFUS exit 2), preuve que le train ne lit
JAMAIS le set golden (exécution avec le fichier ABSENT), épinglage du corpus
(octet muté -> REFUS ; chemin inexistant -> REFUS « introuvable » sans
traceback), zéro texte dans les artefacts (jurisprudence R4) et metadata
complet §8.1.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import subprocess
import sys
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
    # Garde clone-frais (major dq r3) : sans corpus, main() refuse « corpus
    # introuvable » AVANT la garde de stratification — l'assertion serait fausse.
    if not train_v05.DEFAULT_CORPUS_PATH.is_file():
        pytest.skip("corpus de référence absent — régénérer via make router-corpus")

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
    # Garde clone-frais (major dq r3) : run_training lit le corpus de référence.
    if not train_v05.DEFAULT_CORPUS_PATH.is_file():
        pytest.skip("corpus de référence absent — régénérer via make router-corpus")
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
    # Le chemin main() traverse l'import paresseux de run_training (major dq
    # r3) : sans lightgbm, le refus observé serait celui des dépendances, pas
    # celui du hash golden — skip pour rester un témoin honnête de SA garde.
    pytest.importorskip("lightgbm")
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
    # Même import paresseux traversé par main() (major dq r3) : sans lightgbm,
    # le REFUS observé ne serait pas celui de l'épinglage sha256 — skip.
    pytest.importorskip("lightgbm")
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


def test_corpus_introuvable_refuse(tmp_path: Path, capsys: pytest.CaptureFixture):
    """Minor qa r4 : chemin --corpus INEXISTANT -> REFUS exit 2 « introuvable »,
    ZÉRO traceback — le try/except OSError de `_charger_corpus_epingle`
    convertit le FileNotFoundError en RefusError structurée (un mutant qui
    retire cette conversion laisserait fuir un traceback non structuré)."""
    # Même import paresseux traversé par main() (patron test_corpus_epingle) :
    # sans lightgbm, le REFUS observé serait celui des dépendances — skip.
    pytest.importorskip("lightgbm")
    inexistant = tmp_path / "corpus-inexistant.jsonl.gz"
    code = train_v05.main(["--corpus", str(inexistant), "--out-dir", str(tmp_path / "out")])
    assert code == 2
    err = capsys.readouterr().err
    assert "REFUS" in err and "introuvable" in err
    assert "Traceback" not in err
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("valeur", ["0", "100"])
def test_val_pct_hors_bornes_refuse(valeur: str, capsys: pytest.CaptureFixture):
    """Minor qa r3 : la garde CLI DÉDIÉE --val-pct hors [1, 99] refuse exit 2
    avec SON message (« [1, 99] ») — distinct du refus « partition vide » de
    verifier_stratification (un mutant qui supprime la garde est ainsi tué).
    La garde précède toute dépendance et toute lecture : aucun corpus ni
    lightgbm requis (clone frais compris)."""
    assert train_v05.main(["--val-pct", valeur]) == 2
    err = capsys.readouterr().err
    assert "REFUS" in err and "[1, 99]" in err


_REPO_ROOT = Path(__file__).resolve().parents[2]

# Patron _SCRIPT_HEURISTIC_SANS_LIGHTGBM (test_router_eval_gate_hardening) :
# meta-path finder qui BLOQUE lightgbm dans un interpréteur frais.
_SCRIPT_TRAIN_SANS_LIGHTGBM = """
import sys


class _BloqueurLightgbm:
    def find_spec(self, name, path=None, target=None):
        if name == "lightgbm" or name.startswith("lightgbm."):
            raise ImportError("lightgbm bloque (simulation absence)")
        return None


sys.meta_path.insert(0, _BloqueurLightgbm())
sys.path.insert(0, "router/train")
import train_v05

raise SystemExit(train_v05.main(["--out-dir", sys.argv[1]]))
"""


def test_cli_sans_lightgbm_refus_propre(tmp_path: Path):
    """Minors dq+qa r3 : CLI train SANS lightgbm -> exit 2, « REFUS :
    dépendances d'entraînement absentes … requirements-ml », ZÉRO traceback
    (l'import paresseux de run_training est converti en RefusError — même
    patron que MLRouter). Le refus précède toute lecture et toute écriture."""
    proc = subprocess.run(
        [sys.executable, "-c", _SCRIPT_TRAIN_SANS_LIGHTGBM, str(tmp_path / "jamais-ecrit")],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
        timeout=120,
    )
    assert proc.returncode == 2, proc.stderr
    assert "REFUS" in proc.stderr and "requirements-ml" in proc.stderr
    assert "Traceback" not in proc.stderr
    assert not (tmp_path / "jamais-ecrit").exists()


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
    """Minor qa R5 r0 + major eval r1 : un calibrateur à < 2 points est refusé
    AU TRAIN via RefusError (la ValueError initiale échappait au try/except de
    main() → traceback brut, contrat CLI violé — corrigé)."""
    import pytest as _pytest

    with _pytest.raises(train_v05.RefusError, match="dégénéré"):
        train_v05.fit_isotonic([0.8, 0.8, 0.8], [True, True, False])


def test_main_converts_degenerate_calibrator_to_clean_refusal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
    corpus_rows: list[dict],
):
    """Le chemin main() traverse la VRAIE garde dégénérée (minor ml r3 : elle
    était monkeypatchée — plus maintenant). Corpus RÉDUIT à 60 lignes de train
    (< 2 x min_data_in_leaf=50 : aucun split possible, modèle constant), donc
    confiances val CONSTANTES -> un seul point de contrôle isotonique -> le
    VRAI `fit_isotonic` lève RefusError, que main() convertit en « REFUS »
    propre exit 2. Seule l'INFRASTRUCTURE (corpus réduit, référence sha) est
    monkeypatchée — la garde, elle, est réelle."""
    pytest.importorskip("lightgbm")

    # Sélection DÉTERMINISTE 20 train + 4 val PAR label via les buckets réels
    # de `split_by_signature` : parts de classe 1/3 des deux côtés (écart 0,
    # garde de stratification muette), chaque classe présente au train.
    voulu_train, voulu_val = 20, 4
    choisis: list[dict] = []
    for label in LABEL_ORDER:
        pris_train = pris_val = 0
        for row in corpus_rows:
            if row["label"] != label:
                continue
            sig = signal_signature(row["signals"]["prompt"], row["signals"]["conversation"])
            bucket = int(hashlib.sha256(repr(sig).encode("utf-8")).hexdigest(), 16) % 100
            if bucket < train_v05.DEFAULT_VAL_PCT:
                if pris_val < voulu_val:
                    choisis.append(row)
                    pris_val += 1
            elif pris_train < voulu_train:
                choisis.append(row)
                pris_train += 1
            if pris_train == voulu_train and pris_val == voulu_val:
                break
        assert pris_train == voulu_train and pris_val == voulu_val

    payload = "\n".join(json.dumps(r, ensure_ascii=False) for r in choisis) + "\n"
    corpus_reduit = tmp_path / "corpus-reduit.jsonl.gz"
    corpus_reduit.write_bytes(gzip.compress(payload.encode("utf-8")))
    reference = tmp_path / "reference.metadata.json"
    reference.write_text(
        json.dumps({"sha256_gz": hashlib.sha256(corpus_reduit.read_bytes()).hexdigest()}),
        encoding="utf-8",
    )
    monkeypatch.setattr(train_v05, "REFERENCE_METADATA_PATH", reference)

    code = train_v05.main(
        ["--corpus", str(corpus_reduit), "--out-dir", str(tmp_path / "jamais-ecrit")]
    )
    assert code == 2
    err = capsys.readouterr().err
    assert "REFUS" in err and "dégénéré" in err
    # Le refus précède toute écriture : aucun artefact partiel.
    assert not (tmp_path / "jamais-ecrit").exists()
