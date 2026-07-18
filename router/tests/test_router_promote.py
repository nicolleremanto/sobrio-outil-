"""Tests de promotion/rollback (`router/train/promote.py`, chantier R5 §11).

Sandbox tmp complète : chemins d'artefacts monkeypatchés + évals fraîches
substituées par des rapports canoniques (le gate RÉEL `evaluate_gate` est,
lui, toujours exécuté — c'est le juge, §5.3). Couvre : gate FAIL => rien
touché, rotation candidate->promoted->previous, garde anti-contamination
(`fallback:heuristic` dans `repartition_rules`), rollback et son refus sans
`previous/`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import promote
import pytest
from loader import golden_sha256

_SHA_CANONIQUE = golden_sha256()


def _rapport(**overrides: object) -> dict:
    """Rapport d'éval canonique PASS (schéma du gate satisfait, sha canonique)."""
    base: dict = {
        "exactitude_ponderee": 0.90,
        "ece": 0.04,
        "p95_ms": 0.05,
        "golden_sha": _SHA_CANONIQUE,
        "sous_dimensionnement": {"n": 6, "taux": 0.03},
        "calibration_bande_auto": {
            "seuil": 0.75,
            "n": 120,
            "taux_justesse": 0.92,
            "confiance_moyenne": 0.93,
            "ecart": 0.01,
        },
        "repartition_rules": {"ml:v05": 181},
    }
    base.update(overrides)
    return base


def _baseline() -> dict:
    return _rapport(
        exactitude_ponderee=0.73,
        ece=0.09,
        sous_dimensionnement={"n": 37, "taux": 0.20},
        calibration_bande_auto={
            "seuil": 0.75,
            "n": 66,
            "taux_justesse": 0.65,
            "confiance_moyenne": 0.78,
            "ecart": 0.12,
        },
        repartition_rules={"heuristic:short_simple": 181},
    )


def _artefact_bidon(directory: Path, contenu: bytes = b"modele factice v1") -> None:
    """Artefact minimal COHÉRENT (3 fichiers, sha metadata == octets)."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "model.txt").write_bytes(contenu)
    (directory / "calibrator.json").write_text(
        '{"method": "isotonic_top_conservative", "x": [0.1, 0.9], "y": [0.1, 0.9]}',
        encoding="utf-8",
    )
    metadata = {
        "sha256_model_txt": hashlib.sha256((directory / "model.txt").read_bytes()).hexdigest(),
        "sha256_calibrator_json": hashlib.sha256(
            (directory / "calibrator.json").read_bytes()
        ).hexdigest(),
        "best_iteration": 130,
    }
    (directory / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Chemins promote.* redirigés vers tmp + évals fraîches substituées."""
    dirs = {
        "candidate": tmp_path / "candidate",
        "promoted": tmp_path / "promoted",
        "previous": tmp_path / "previous",
    }
    monkeypatch.setattr(promote, "CANDIDATE_DIR", dirs["candidate"])
    monkeypatch.setattr(promote, "PROMOTED_DIR", dirs["promoted"])
    monkeypatch.setattr(promote, "PREVIOUS_DIR", dirs["previous"])
    _artefact_bidon(dirs["candidate"])
    monkeypatch.setattr(promote, "_evals_fraiches", lambda: (_baseline(), _rapport()))
    return dirs


def test_promote_gate_fail_refuse(sandbox, monkeypatch, capsys):
    """Gate FAIL (candidat sous la baseline) : exit != 0, dossiers INTACTS."""
    monkeypatch.setattr(
        promote,
        "_evals_fraiches",
        lambda: (_baseline(), _rapport(exactitude_ponderee=0.70)),
    )
    avant = sorted(p.name for p in sandbox["candidate"].iterdir())
    code = promote.main([])
    assert code == 1  # le code du gate
    err = capsys.readouterr().err
    assert "REFUS" in err and "gate FAIL" in err
    assert sorted(p.name for p in sandbox["candidate"].iterdir()) == avant  # intact
    assert not sandbox["promoted"].exists()
    assert not sandbox["previous"].exists()


def test_promote_rotation(sandbox, monkeypatch, capsys):
    """1re promotion -> promoted/ complet + eval-report ; 2e -> previous byte-identique."""
    assert promote.main([]) == 0
    assert "PROMU" in capsys.readouterr().out
    fichiers = sorted(p.name for p in sandbox["promoted"].iterdir())
    assert fichiers == ["calibrator.json", "eval-report.json", "metadata.json", "model.txt"]
    rapport_promu = json.loads((sandbox["promoted"] / "eval-report.json").read_text())
    assert rapport_promu["exactitude_ponderee"] == 0.90
    premier_model = (sandbox["promoted"] / "model.txt").read_bytes()

    # Nouveau candidat (contenu différent, rapport meilleur) puis 2e promotion.
    _artefact_bidon(sandbox["candidate"], contenu=b"modele factice v2")
    monkeypatch.setattr(
        promote, "_evals_fraiches", lambda: (_baseline(), _rapport(exactitude_ponderee=0.92))
    )
    assert promote.main([]) == 0
    assert (sandbox["previous"] / "model.txt").read_bytes() == premier_model  # byte-identique
    assert (sandbox["promoted"] / "model.txt").read_bytes() == b"modele factice v2"
    # Le rapport promu accompagne l'artefact (servira de --previous au prochain gate).
    assert (
        json.loads((sandbox["promoted"] / "eval-report.json").read_text())["exactitude_ponderee"]
        == 0.92
    )


def test_promote_refuse_fallback_contamine(sandbox, monkeypatch, capsys):
    """`fallback:heuristic` dans repartition_rules : REFUS exit 2, rien promu."""
    contamine = _rapport(repartition_rules={"ml:v05": 180, "fallback:heuristic": 1})
    monkeypatch.setattr(promote, "_evals_fraiches", lambda: (_baseline(), contamine))
    code = promote.main([])
    assert code == 2
    err = capsys.readouterr().err
    assert "REFUS" in err and "contaminée" in err
    assert not sandbox["promoted"].exists()


def test_rollback(sandbox, capsys):
    """Échange promoted/previous ; sans previous/ -> REFUS exit 2."""
    # Sans previous : refus propre.
    assert promote.main(["--rollback"]) == 2
    assert "REFUS" in capsys.readouterr().err

    _artefact_bidon(sandbox["promoted"], contenu=b"promu courant")
    _artefact_bidon(sandbox["previous"], contenu=b"promu precedent")
    assert promote.main(["--rollback"]) == 0
    assert "ROLLBACK" in capsys.readouterr().out
    assert (sandbox["promoted"] / "model.txt").read_bytes() == b"promu precedent"
    assert (sandbox["previous"] / "model.txt").read_bytes() == b"promu courant"


def test_promote_refuse_candidat_absent(sandbox, monkeypatch, capsys):
    """Évals fraîches impossibles (artefact candidat invalide) : REFUS exit 2."""

    def _explose():
        raise promote.RefusError("artefact ml_v05_candidate absent ou invalide")

    monkeypatch.setattr(promote, "_evals_fraiches", _explose)
    assert promote.main([]) == 2
    assert "REFUS" in capsys.readouterr().err
