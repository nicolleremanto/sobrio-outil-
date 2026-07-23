"""Tests tête v0 / harnais / gate / promotion embed (R6 Lot 5, spec §8-§9, §10.5/§10.8).

Couvre : harnais embed (registre, confiances SERVIES via `EmbedHead.predict`,
schéma accepté par `_validate_report` du gate, bande auto structurellement
vide sous plafond — §9.1/§9.2), gate `--suite embed --budget-ms 30` (borne
30.0 INCLUSIVE, câblage `--suite` tué par mutation — le flag FAIT basculer
le verdict via le sha attendu, patron QA-R3-m1), train de la tête v0
(déterminisme double-run bit-identique, metadata honnête D4, garde
d'étanchéité, refus sans numpy exit 2, garde anti-dégénérescence
[0.55, 0.999]) et `promote_embed` (rotation trois-temps, gardes bench D8 —
dont le REFUS avant geste fondateur sur le manifest RÉEL —, contamination,
rollback, exit codes 0/1/2).

Les tests exigeant numpy font `pytest.importorskip` (patron DQ-R3) : la
suite reste verte sur clone frais sans dépendances embed. AUCUN texte type
prompt nulle part (les fixtures sont des vecteurs seedés, D6).
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import gate
import harness_embed
import promote_embed
import pytest
import train_head_v0
from embed_fixtures import canonical_eval_set, embed_golden_sha256
from loader import golden_sha256
from test_router_embed import _ecrire_tete

from sobrio_router.embed import EmbedHead
from sobrio_router.ml import LABEL_ORDER

_SHA_EMBED = embed_golden_sha256()
_SHA_GOLDEN = golden_sha256()


# ---------------------------------------------------------------------------
# Fabriques locales.
# ---------------------------------------------------------------------------


def _tete_sur_confiante(directory: Path) -> Path:
    """Tête stdlib valide dont le softmax BRUT sature ~1.0 : sert à prouver
    que la chaîne servie plafonne à `confidence_cap` (§9.2)."""
    w = [[50.0 if j == i else 0.0 for j in range(384)] for i in range(3)]
    return _ecrire_tete(directory, w=w, calibrator={"x": [0.0, 1.0], "y": [0.0, 1.0]})


def _rapport_embed(**overrides: object) -> dict:
    """Rapport candidat canonique PASS (schéma gate satisfait, sha embed épinglé)."""
    base: dict = {
        "exactitude_ponderee": 0.75,
        "ece": 0.07,
        "p95_ms": 0.08,
        "golden_sha": _SHA_EMBED,
        "sous_dimensionnement": {"n": 41, "taux": 0.1708},
        "calibration_bande_auto": {
            "seuil": 0.75,
            "n": 0,
            "taux_justesse": None,
            "confiance_moyenne": None,
            "ecart": 0.0,
        },
        "repartition_rules": {"embed:v0": 240},
    }
    base.update(overrides)
    return base


def _baseline_prior(**overrides: object) -> dict:
    return _rapport_embed(
        exactitude_ponderee=0.5,
        ece=0.1667,
        p95_ms=0.001,
        sous_dimensionnement={"n": 80, "taux": 0.3333},
        repartition_rules={"embed:prior": 240},
        **overrides,
    )


# ---------------------------------------------------------------------------
# Harnais embed (§9.1) — stdlib : EmbedHead est pur, le prior aussi.
# ---------------------------------------------------------------------------


def test_harnais_prior_schema_et_metriques():
    """La baseline prior (D13) : sonnet@0.5 constant, wa=0.5, schéma gate OK."""
    report = harness_embed.run("prior")
    assert gate._validate_report(report, "prior") == []
    assert report["n"] == 240
    assert report["exactitude_ponderee"] == 0.5
    assert report["exactitude_globale"] == round(1 / 3, 4)
    assert report["sous_dimensionnement"]["taux"] == 0.3333
    assert report["repartition_rules"] == {"embed:prior": 240}
    assert report["golden_sha"] == _SHA_EMBED
    assert report["latence_perimetre"] == "head_only"
    assert report["calibration_bande_auto"]["n"] == 0


def test_harnais_head_candidate_via_predict(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """`head_candidate` charge le MÊME EmbedHead que le service et mesure les
    confiances SERVIES : rules 100 % embed:v0, aucune confiance > cap."""
    monkeypatch.setattr(harness_embed, "CANDIDATE_DIR", _tete_sur_confiante(tmp_path / "tete"))
    report = harness_embed.run("head_candidate")
    assert gate._validate_report(report, "candidat") == []
    assert report["repartition_rules"] == {"embed:v0": 240}
    # Confiances servies plafonnées : la bande auto candidate (conf >= 0.75)
    # est STRUCTURELLEMENT vide par construction (§9.2, correction MAJOR-1).
    assert report["calibration_bande_auto"]["n"] == 0
    cellules = report["calibration_par_confiance_informatif"]
    assert max(float(c) for c in cellules) <= 0.74


def test_toutes_les_confiances_servies_sous_le_cap(tmp_path: Path):
    """Assertion directe §9.2 : sur TOUT le set canonique, `predict` n'émet
    jamais plus que `confidence_cap` — même avec un softmax brut saturé."""
    tete = EmbedHead.load(_tete_sur_confiante(tmp_path / "tete"))
    for row in canonical_eval_set():
        _, confiance = tete.predict(list(row.embedding))
        assert confiance <= 0.74


def test_harnais_registre_inconnu_refuse():
    with pytest.raises(ValueError) as excinfo:
        harness_embed.run("inconnue")
    assert "registre" in str(excinfo.value)


def test_harnais_cli_ecrit_le_rapport(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys):
    monkeypatch.setattr(harness_embed, "_ARTIFACTS_DIR", tmp_path / "eval")
    assert harness_embed.main(["--router", "prior"]) == 0
    out_path = tmp_path / "eval" / "embed-prior-latest.json"
    assert out_path.is_file()
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert report["router_name"] == "prior"
    assert "rapport écrit" in capsys.readouterr().err


def test_harnais_cli_refus_exit2_tete_absente(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    """Tête candidate absente : ÉCHEC BRUYANT exit 2 (jamais d'éval « prouvée
    à vide », leçon R4), aucun rapport écrit."""
    monkeypatch.setattr(harness_embed, "CANDIDATE_DIR", tmp_path / "vide")
    monkeypatch.setattr(harness_embed, "_ARTIFACTS_DIR", tmp_path / "eval")
    assert harness_embed.main(["--router", "head_candidate"]) == 2
    assert "REFUS" in capsys.readouterr().err
    assert not (tmp_path / "eval").exists()


def test_rapport_degenere_refuse_par_le_gate():
    """§10.8 : un rapport embed dégénéré => FAIL STRUCTURÉ de `_validate_report`."""
    degenere = _rapport_embed(exactitude_ponderee=5.0, ece=-1.0)
    result = gate.evaluate_gate(degenere, _baseline_prior(), expected_golden_sha=_SHA_EMBED)
    assert not result.passed
    assert any("FAIL schéma" in raison for raison in result.reasons)


_CLES_INTERDITES = {"prompt", "prompt_text", "text", "texte", "contenu", "message"}
# Une CLÉ d'artefact est un identifiant système (minuscules/chiffres/_.:-),
# jamais du texte libre (pas d'espace, pas de majuscule, pas d'accent).
_MOTIF_CLE = re.compile(r"^[a-z0-9_.:\-]+$")
_MOTIFS_SURS = (
    re.compile(r"^[0-9a-f]{7,64}$"),  # sha256 / git sha court
    re.compile(r"^\d{4}-\d{2}-\d{2}[T ]?[\d:.+]*$"),  # dates ISO
    re.compile(r"^\d+(\.\d+)*$"),  # versions / cellules de confiance
    re.compile(r"^motif_\d$"),  # catégories des fixtures
    re.compile(r"^unknown$"),  # _git_sha hors dépôt
)


def _verifier_arbre_sans_texte(obj: object, autorisees: frozenset[str]) -> None:
    """Parcours COMPLET d'un artefact JSON (§10.1) : aucune clé texte-esque,
    chaque chaîne = constante connue du système ou motif sûr (hash, date,
    version) — un texte libre inattendu fait échouer."""
    if isinstance(obj, dict):
        for cle, valeur in obj.items():
            assert cle not in _CLES_INTERDITES, f"clé interdite dans un artefact : {cle}"
            assert _MOTIF_CLE.match(cle), f"clé non-identifiant dans un artefact : {cle!r}"
            _verifier_arbre_sans_texte(valeur, autorisees)
    elif isinstance(obj, list):
        for valeur in obj:
            _verifier_arbre_sans_texte(valeur, autorisees)
    elif isinstance(obj, str):
        assert obj in autorisees or any(motif.match(obj) for motif in _MOTIFS_SURS), (
            f"chaîne inattendue dans un artefact : {obj!r}"
        )


_CHAINES_RAPPORT = frozenset(
    {
        *LABEL_ORDER,
        *(f"motif_{k}" for k in range(4)),
        "prior",
        "head_candidate",
        "head_promoted",
        harness_embed.PRIOR_RULE,
        harness_embed.HEAD_RULE,
        harness_embed.LATENCE_PERIMETRE,
        harness_embed.NOTE_INTEGRITE,
    }
)


def test_rapport_harnais_sans_champ_texte(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """§10.1 : l'arbre JSON complet du rapport embed ne porte AUCUN texte
    libre — uniquement le vocabulaire système, des nombres et des hash."""
    monkeypatch.setattr(harness_embed, "CANDIDATE_DIR", _tete_sur_confiante(tmp_path / "tete"))
    for nom in ("prior", "head_candidate"):
        _verifier_arbre_sans_texte(harness_embed.run(nom), _CHAINES_RAPPORT)


# ---------------------------------------------------------------------------
# Gate `--suite embed --budget-ms 30` (§9.2, §10.5).
# ---------------------------------------------------------------------------


def _ecrire_rapports(tmp_path: Path, candidat: dict, baseline: dict) -> tuple[Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    cand_path = tmp_path / "candidat.json"
    base_path = tmp_path / "baseline.json"
    cand_path.write_text(json.dumps(candidat), encoding="utf-8")
    base_path.write_text(json.dumps(baseline), encoding="utf-8")
    return cand_path, base_path


def test_gate_embed_pass_borne_30_exact(tmp_path: Path, capsys):
    """Borne INCLUSIVE (convention R5) : p95 == 30.0 PASSE à --budget-ms 30."""
    cand, base = _ecrire_rapports(tmp_path, _rapport_embed(p95_ms=30.0), _baseline_prior())
    code = gate.main(
        ["--candidate", str(cand), "--baseline", str(base), "--suite", "embed", "--budget-ms", "30"]
    )
    assert code == 0
    sortie = capsys.readouterr()
    assert "PASS latence" in sortie.out
    assert "VERDICT : PASS" in sortie.err


def test_gate_embed_fail_30_0001(tmp_path: Path, capsys):
    cand, base = _ecrire_rapports(tmp_path, _rapport_embed(p95_ms=30.0001), _baseline_prior())
    code = gate.main(
        ["--candidate", str(cand), "--baseline", str(base), "--suite", "embed", "--budget-ms", "30"]
    )
    assert code == 1
    assert "FAIL latence" in capsys.readouterr().out


def test_cablage_suite_mute_le_verdict_via_le_sha(tmp_path: Path, capsys):
    """Mutation du câblage (patron QA-R3-m1) : les MÊMES rapports basculent
    PASS/FAIL selon `--suite` — preuve que le flag choisit RÉELLEMENT la
    source du hash canonique injecté (§9.2)."""
    cand, base = _ecrire_rapports(tmp_path, _rapport_embed(), _baseline_prior())
    args = ["--candidate", str(cand), "--baseline", str(base), "--budget-ms", "30"]
    # Rapports épinglés embed : PASS avec --suite embed…
    assert gate.main([*args, "--suite", "embed"]) == 0
    capsys.readouterr()
    # …FAIL sans le flag (suite golden par défaut, sha attendu différent).
    assert gate.main(args) == 1
    assert "FAIL golden_sha" in capsys.readouterr().out
    # Et symétriquement : des rapports épinglés GOLDEN passent par défaut
    # mais échouent sous --suite embed.
    cand_g, base_g = _ecrire_rapports(
        tmp_path / "golden",
        _rapport_embed(golden_sha=_SHA_GOLDEN),
        _baseline_prior(golden_sha=_SHA_GOLDEN),
    )
    args_g = ["--candidate", str(cand_g), "--baseline", str(base_g), "--budget-ms", "30"]
    assert gate.main(args_g) == 0
    capsys.readouterr()
    assert gate.main([*args_g, "--suite", "embed"]) == 1
    assert "FAIL golden_sha" in capsys.readouterr().out


def test_gate_embed_bande_auto_vide_branche_rien_a_degrader(tmp_path: Path, capsys):
    """§9.2 : sous plafond 0.74, la bande candidate est vide PAR CONSTRUCTION
    — le critère 7 passe par « rien à dégrader », le 7-bis n'est PAS évalué."""
    cand, base = _ecrire_rapports(tmp_path, _rapport_embed(), _baseline_prior())
    assert gate.main(
        ["--candidate", str(cand), "--baseline", str(base), "--suite", "embed", "--budget-ms", "30"]
    ) == 0
    sortie = capsys.readouterr().out
    assert "rien à dégrader" in sortie
    assert "bande-auto-absolu" not in sortie  # 7-bis non évalué (n == 0)


def test_gate_suite_embed_manifest_illisible_exit2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
):
    """Pin embed illisible : refus fail-closed exit 2 (comme un rapport illisible)."""
    import embed_fixtures

    cand, base = _ecrire_rapports(tmp_path, _rapport_embed(), _baseline_prior())
    monkeypatch.setattr(embed_fixtures, "MANIFEST_PATH", tmp_path / "absent.json")
    code = gate.main(
        ["--candidate", str(cand), "--baseline", str(base), "--suite", "embed", "--budget-ms", "30"]
    )
    assert code == 2
    assert "VERDICT : FAIL" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Entraînement de la tête v0 (§8) — numpy requis (skip propre sinon).
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def tete_v0(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Tête candidate ENTRAÎNÉE (fonctions réelles, fixtures canoniques) —
    une fois par session, jamais dans router/artifacts/ (patron artefact_v05)."""
    pytest.importorskip("numpy")
    out_dir = tmp_path_factory.mktemp("tete_v0") / "candidate"
    train_head_v0.run_training(out_dir)
    return out_dir


def test_train_double_run_bit_identique(tete_v0: Path, tmp_path: Path):
    """Déterminisme §8 : deux entraînements (même seed) => head.json et
    calibrator.json BIT-identiques (le metadata ne diffère que par la date)."""
    pytest.importorskip("numpy")
    autre = tmp_path / "candidate-bis"
    train_head_v0.run_training(autre)
    assert (autre / "head.json").read_bytes() == (tete_v0 / "head.json").read_bytes()
    assert (autre / "calibrator.json").read_bytes() == (tete_v0 / "calibrator.json").read_bytes()
    meta_a = json.loads((tete_v0 / "metadata.json").read_text(encoding="utf-8"))
    meta_b = json.loads((autre / "metadata.json").read_text(encoding="utf-8"))
    for volatile in ("date_train", "git_sha"):
        meta_a.pop(volatile), meta_b.pop(volatile)
    assert meta_a == meta_b


def test_train_artefact_charge_par_embed_head(tete_v0: Path):
    """Les DEUX côtés du contrat §6.3 : ce que le train écrit, `EmbedHead.load`
    l'exige — chargement fail-closed OK, confiances servies sous le cap."""
    tete = EmbedHead.load(tete_v0)
    label, confiance = tete.predict([0.05] * 384)
    assert label in LABEL_ORDER
    assert 0.0 <= confiance <= 0.74


def test_train_metadata_honnete_d4(tete_v0: Path):
    """Metadata §6.3 : statut v0 consigné mot pour mot, spec/mapping/cap/sha."""
    metadata = json.loads((tete_v0 / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["artefact"] == "embed_head_v0"
    assert metadata["statut"] == train_head_v0.STATUT_V0
    assert metadata["train_source"] == "synthetic_embed_fixtures"
    assert metadata["head_reelle_attend_telemetrie_v1"] is True
    assert metadata["confidence_cap"] == 0.74
    assert metadata["train_seed"] == 20260723
    assert metadata["eval_seed"] == 20260724
    from sobrio_router.embed import expected_embed_spec

    assert metadata["embed_spec"] == expected_embed_spec()
    assert metadata["label_mapping"] == {label: i for i, label in enumerate(LABEL_ORDER)}
    assert metadata["n_train"] + metadata["n_val"] == 3000
    for fichier, cle in (
        ("head.json", "sha256_head_json"),
        ("calibrator.json", "sha256_calibrator_json"),
    ):
        assert metadata[cle] == hashlib.sha256((tete_v0 / fichier).read_bytes()).hexdigest()


_CHAINES_ARTEFACT_TETE = frozenset(
    {
        *LABEL_ORDER,
        "embed_head_v0",
        train_head_v0.STATUT_V0,
        "synthetic_embed_fixtures",
        "isotonic_top_conservative",
        "val",
        "multilingual-e5-small",
        "int8",
        "mean_masked",
        "l2",
        "query: ",
    }
)


def test_train_artefacts_sans_champ_texte(tete_v0: Path):
    """§10.1 : l'arbre JSON complet des trois fichiers écrits par le train ne
    porte AUCUN texte libre hors constantes système consignées."""
    for nom in ("head.json", "calibrator.json", "metadata.json"):
        arbre = json.loads((tete_v0 / nom).read_text(encoding="utf-8"))
        _verifier_arbre_sans_texte(arbre, _CHAINES_ARTEFACT_TETE)


def test_train_garde_anti_degenerescence(tete_v0: Path, monkeypatch: pytest.MonkeyPatch):
    """§10.8 : exactitude de la tête candidate sur l'éval canonique dans
    [0.55, 0.999] — 1.0 = fixtures dégénérées, < 0.55 = générateur cassé."""
    monkeypatch.setattr(harness_embed, "CANDIDATE_DIR", tete_v0)
    report = harness_embed.run("head_candidate")
    assert 0.55 <= report["exactitude_globale"] <= 0.999


def test_train_refuse_seeds_identiques(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Garde d'étanchéité §8 : REFUS si eval_seed == train_seed."""
    pytest.importorskip("numpy")
    monkeypatch.setattr(train_head_v0, "EVAL_SEED", train_head_v0.TRAIN_SEED)
    with pytest.raises(train_head_v0.RefusError) as excinfo:
        train_head_v0.run_training(tmp_path / "candidate")
    assert "étanchéité" in str(excinfo.value)


def test_train_cli_sans_numpy_exit2(tmp_path: Path):
    """§10.6 : numpy bloqué => exit 2, « REFUS … requirements-embed », zéro
    traceback (patron DQ-R3 des skips lightgbm)."""
    script = (
        "import sys\n"
        "class _Bloqueur:\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name == 'numpy' or name.startswith('numpy.'):\n"
        "            raise ImportError('numpy bloque (simulation absence)')\n"
        "        return None\n"
        "sys.meta_path.insert(0, _Bloqueur())\n"
        "sys.path.insert(0, 'router/train')\n"
        "sys.path.insert(0, 'router/eval')\n"
        "import train_head_v0\n"
        f"raise SystemExit(train_head_v0.main(['--out-dir', {str(tmp_path)!r}]))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=Path(__file__).resolve().parents[2],
    )
    assert proc.returncode == 2, proc.stderr
    assert "REFUS" in proc.stderr
    assert "requirements-embed" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_train_cli_nominal_sortie_nombres_et_hash(tmp_path: Path, capsys):
    pytest.importorskip("numpy")
    assert train_head_v0.main(["--out-dir", str(tmp_path / "candidate")]) == 0
    sortie = capsys.readouterr().out
    assert "split : " in sortie
    assert "sha256 head.json : " in sortie
    assert "l'éval qui fait foi est harness_embed" in sortie


# ---------------------------------------------------------------------------
# promote_embed (§9.3) — sandbox complète, patron test_router_promote.
# ---------------------------------------------------------------------------


def _sha_hex(contenu: bytes) -> str:
    return hashlib.sha256(contenu).hexdigest()


_SHA_ENCODEUR_FACTICE = _sha_hex(b"encodeur factice lot5")


def _ecrire_manifest_factice(path: Path, sha: str = _SHA_ENCODEUR_FACTICE) -> Path:
    path.write_text(
        json.dumps({"variants": {"int8": {"files": {"model.onnx": {"sha256": sha}}}}}),
        encoding="utf-8",
    )
    return path


def _ecrire_bench_factice(
    path: Path,
    p95_ms: object = 12.4,
    rss_peak_mb: object = 512.0,
    encoder_sha256: str = _SHA_ENCODEUR_FACTICE,
) -> Path:
    rapport = {"p95_ms": p95_ms, "rss_peak_mb": rss_peak_mb, "encoder_sha256": encoder_sha256}
    path.write_text(json.dumps(rapport), encoding="utf-8")
    return path


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Chemins promote_embed.* redirigés vers tmp + évals substituées + preuve
    bench et manifest FACTICES cohérents (le gate RÉEL reste le juge)."""
    dirs = {
        "candidate": tmp_path / "candidate",
        "promoted": tmp_path / "promoted",
        "previous": tmp_path / "previous",
    }
    monkeypatch.setattr(promote_embed, "CANDIDATE_DIR", dirs["candidate"])
    monkeypatch.setattr(promote_embed, "PROMOTED_DIR", dirs["promoted"])
    monkeypatch.setattr(promote_embed, "PREVIOUS_DIR", dirs["previous"])
    monkeypatch.setattr(
        promote_embed, "MANIFEST_PATH", _ecrire_manifest_factice(tmp_path / "manifest.json")
    )
    monkeypatch.setattr(
        promote_embed, "BENCH_REPORT_PATH", _ecrire_bench_factice(tmp_path / "bench.json")
    )
    _ecrire_tete(dirs["candidate"])
    monkeypatch.setattr(
        promote_embed, "_evals_fraiches", lambda: (_baseline_prior(), _rapport_embed())
    )
    return dirs


def test_promote_gate_fail_refuse_rien_touche(sandbox, monkeypatch, capsys):
    """Gate FAIL (candidat sous la baseline prior) : exit 1, dossiers INTACTS."""
    monkeypatch.setattr(
        promote_embed,
        "_evals_fraiches",
        lambda: (_baseline_prior(), _rapport_embed(exactitude_ponderee=0.40)),
    )
    avant = sorted(p.name for p in sandbox["candidate"].iterdir())
    assert promote_embed.main([]) == 1
    err = capsys.readouterr().err
    assert "REFUS" in err and "gate FAIL" in err
    assert sorted(p.name for p in sandbox["candidate"].iterdir()) == avant
    assert not sandbox["promoted"].exists()
    assert not sandbox["previous"].exists()


def test_promote_rotation_trois_temps(sandbox, monkeypatch, capsys):
    """1re promotion -> promoted/ complet + eval-report ; 2e -> previous
    byte-identique (rotation §9.3.5)."""
    assert promote_embed.main([]) == 0
    assert "PROMU" in capsys.readouterr().out
    fichiers = sorted(p.name for p in sandbox["promoted"].iterdir())
    assert fichiers == ["calibrator.json", "eval-report.json", "head.json", "metadata.json"]
    rapport_promu = json.loads(
        (sandbox["promoted"] / "eval-report.json").read_text(encoding="utf-8")
    )
    assert rapport_promu["exactitude_ponderee"] == 0.75
    premier_head = (sandbox["promoted"] / "head.json").read_bytes()

    # Nouveau candidat (poids différents, rapport meilleur) puis 2e promotion.
    _ecrire_tete(sandbox["candidate"], b=[0.1, 0.0, -0.1])
    monkeypatch.setattr(
        promote_embed,
        "_evals_fraiches",
        lambda: (_baseline_prior(), _rapport_embed(exactitude_ponderee=0.78)),
    )
    assert promote_embed.main([]) == 0
    assert (sandbox["previous"] / "head.json").read_bytes() == premier_head
    assert (
        json.loads((sandbox["promoted"] / "eval-report.json").read_text(encoding="utf-8"))[
            "exactitude_ponderee"
        ]
        == 0.78
    )


def test_promote_refuse_contamination(sandbox, monkeypatch, capsys):
    """La moindre règle étrangère dans repartition_rules : REFUS exit 2 (§9.3.3)."""
    contamine = _rapport_embed(repartition_rules={"embed:v0": 239, "fallback:heuristic": 1})
    monkeypatch.setattr(
        promote_embed, "_evals_fraiches", lambda: (_baseline_prior(), contamine)
    )
    assert promote_embed.main([]) == 2
    err = capsys.readouterr().err
    assert "REFUS" in err and "contaminée" in err
    assert not sandbox["promoted"].exists()


def test_promote_refuse_bench_absent(sandbox, monkeypatch, capsys):
    """Garde D8 : pas de preuve bench => REFUS exit 2, rien promu (§9.3.4)."""
    monkeypatch.setattr(promote_embed, "BENCH_REPORT_PATH", sandbox["candidate"] / "absent.json")
    assert promote_embed.main([]) == 2
    err = capsys.readouterr().err
    assert "REFUS" in err and "preuve bench absente" in err
    assert not sandbox["promoted"].exists()


@pytest.mark.parametrize(
    ("champ", "valeur", "motif"),
    [
        ("p95_ms", 30.0001, "p95_ms"),
        ("p95_ms", float("nan"), "p95_ms"),
        ("rss_peak_mb", 1024.0, "rss_peak_mb"),
        ("encoder_sha256", "0" * 64, "périmée"),
    ],
)
def test_promote_refuse_bench_depasse_ou_perime(sandbox, monkeypatch, capsys, champ, valeur, motif):
    """Budget dépassé (borne 30.0 inclusive), RSS >= 1 Go ou sha encodeur
    divergent du manifest : REFUS exit 2."""
    bench = {"p95_ms": 12.4, "rss_peak_mb": 512.0, "encoder_sha256": _SHA_ENCODEUR_FACTICE}
    bench[champ] = valeur
    promote_embed.BENCH_REPORT_PATH.write_text(json.dumps(bench), encoding="utf-8")
    assert promote_embed.main([]) == 2
    err = capsys.readouterr().err
    assert "REFUS" in err and motif in err
    assert not sandbox["promoted"].exists()


def test_promote_bench_borne_30_inclusive(sandbox, capsys):
    """p95 bench == 30.0 exact : la borne est INCLUSIVE, la promotion passe."""
    _ecrire_bench_factice(promote_embed.BENCH_REPORT_PATH, p95_ms=30.0)
    assert promote_embed.main([]) == 0
    assert "PROMU" in capsys.readouterr().out


def test_promote_refuse_avant_geste_fondateur(sandbox, monkeypatch, capsys):
    """Manifest RÉEL committé (sources null, geste fondateur non advenu) :
    AUCUNE promotion effective possible — REFUS exit 2 explicite (D4/D8).
    C'est l'état de PRODUCTION à la clôture R6 : heads/promoted/ reste vide."""
    manifest_reel = Path(promote_embed.__file__).resolve().parents[1] / (
        "tools/embed_model_manifest.json"
    )
    assert manifest_reel.is_file()
    monkeypatch.setattr(promote_embed, "MANIFEST_PATH", manifest_reel)
    assert promote_embed.main([]) == 2
    err = capsys.readouterr().err
    assert "REFUS" in err and "geste fondateur" in err
    assert not sandbox["promoted"].exists()


def test_promote_refuse_integrite_candidate(sandbox, monkeypatch, capsys):
    """Sha head.json divergent du metadata : REFUS exit 2 après gate PASS."""
    (sandbox["candidate"] / "head.json").write_text('{"w": [], "b": []}', encoding="utf-8")
    assert promote_embed.main([]) == 2
    assert "intégrité" in capsys.readouterr().err
    assert not sandbox["promoted"].exists()


def test_promote_refuse_candidat_absent(sandbox, monkeypatch, capsys):
    """Évals fraîches impossibles (tête candidate invalide) : REFUS exit 2."""

    def _explose():
        raise promote_embed.RefusError("tête head_candidate absente ou invalide")

    monkeypatch.setattr(promote_embed, "_evals_fraiches", _explose)
    assert promote_embed.main([]) == 2
    assert "REFUS" in capsys.readouterr().err


def test_rollback_trois_temps(sandbox, capsys):
    """Échange promoted/previous ; sans previous/ -> REFUS exit 2."""
    assert promote_embed.main(["--rollback"]) == 2
    assert "REFUS" in capsys.readouterr().err

    _ecrire_tete(sandbox["promoted"], b=[0.2, 0.0, 0.0])
    _ecrire_tete(sandbox["previous"], b=[0.0, 0.0, 0.2])
    head_promu = (sandbox["promoted"] / "head.json").read_bytes()
    head_precedent = (sandbox["previous"] / "head.json").read_bytes()
    assert promote_embed.main(["--rollback"]) == 0
    assert "ROLLBACK" in capsys.readouterr().out
    assert (sandbox["promoted"] / "head.json").read_bytes() == head_precedent
    assert (sandbox["previous"] / "head.json").read_bytes() == head_promu


def test_promote_e2e_train_reel_gate_reel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys):
    """E2E §10.8 (skip sans numpy) : train RÉEL -> évals FRAÎCHES réelles ->
    gate PASS -> rotation effective ; puis candidat DÉGRADÉ -> gate FAIL ->
    REFUS, aucun dossier touché. Environnement jetable intégral (D4 :
    heads/promoted/ du repo reste vide)."""
    pytest.importorskip("numpy")
    candidate = tmp_path / "candidate"
    train_head_v0.run_training(candidate)

    monkeypatch.setattr(harness_embed, "CANDIDATE_DIR", candidate)
    monkeypatch.setattr(harness_embed, "_ARTIFACTS_DIR", tmp_path / "eval")
    monkeypatch.setattr(promote_embed, "CANDIDATE_DIR", candidate)
    monkeypatch.setattr(promote_embed, "PROMOTED_DIR", tmp_path / "promoted")
    monkeypatch.setattr(promote_embed, "PREVIOUS_DIR", tmp_path / "previous")
    monkeypatch.setattr(
        promote_embed, "MANIFEST_PATH", _ecrire_manifest_factice(tmp_path / "manifest.json")
    )
    monkeypatch.setattr(
        promote_embed, "BENCH_REPORT_PATH", _ecrire_bench_factice(tmp_path / "bench.json")
    )

    # Promotion RÉELLE : évals fraîches non substituées, gate réel PASS.
    assert promote_embed.main([]) == 0
    sortie = capsys.readouterr()
    assert "PROMU" in sortie.out
    assert (tmp_path / "promoted" / "eval-report.json").is_file()
    assert (tmp_path / "eval" / "embed-prior-latest.json").is_file()
    assert (tmp_path / "eval" / "embed-head_candidate-latest.json").is_file()
    rapport = json.loads(
        (tmp_path / "promoted" / "eval-report.json").read_text(encoding="utf-8")
    )
    assert rapport["golden_sha"] == _SHA_EMBED
    assert rapport["ece"] <= 0.10
    assert rapport["calibration_bande_auto"]["n"] == 0

    # Candidat DÉGRADÉ (tête constante haiku : sous-dimensionnement massif,
    # sous la baseline prior) : gate FAIL, promoted/previous INTACTS.
    etat_promoted = sorted(p.name for p in (tmp_path / "promoted").iterdir())
    w_haiku = [[0.0] * 384, [-50.0] * 384, [-50.0] * 384]
    _ecrire_tete(candidate, w=w_haiku, b=[10.0, -10.0, -10.0])
    assert promote_embed.main([]) == 1
    err = capsys.readouterr().err
    assert "gate FAIL" in err
    assert sorted(p.name for p in (tmp_path / "promoted").iterdir()) == etat_promoted
    assert not (tmp_path / "previous").exists()


# ---------------------------------------------------------------------------
# Garde anti-réseau en GLOB sur `router/eval/*.py` (§1.3/§10.7 — les
# nouveaux modules du lot, embed_fixtures et harness_embed, y vivent :
# couverture d'office, même patron M6 que router/data et router/train).
# ---------------------------------------------------------------------------

_EVAL_DIR = Path(__file__).resolve().parents[1] / "eval"
# Regex M6 (miroir de test_router_data_distill) : ancrée début de ligne,
# formes `import X` ET `from X import Y`, jamais une mention en prose.
_MOTIF_IMPORT_RESEAU = re.compile(
    r"^\s*(import|from)\s+(anthropic|openai|httpx|requests|socket|urllib|http\b)",
    re.MULTILINE,
)


@pytest.mark.parametrize("module_path", sorted(_EVAL_DIR.glob("*.py")), ids=lambda p: p.name)
def test_no_network_imports_in_router_eval_modules(module_path: Path):
    source = module_path.read_text(encoding="utf-8")
    match = _MOTIF_IMPORT_RESEAU.search(source)
    assert match is None, (
        f"import réseau interdit détecté dans {module_path.name} : {match.group(0)!r}"
    )
    assert "urlopen" not in source
    assert "Anthropic(" not in source


def test_router_eval_dir_couvert_par_la_garde():
    """Garde-fou du garde-fou : le glob voit bien les modules R3/R5 ET les
    nouveaux modules du lot (dossier déplacé => garde inerte détectée)."""
    noms = {p.name for p in _EVAL_DIR.glob("*.py")}
    assert {"harness.py", "gate.py", "loader.py", "embed_fixtures.py", "harness_embed.py"} <= noms
