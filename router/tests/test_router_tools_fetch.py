"""Tests Lot 2 RECADRÉ — outillage modèle (fetch CLI + manifest), spec §4.3/§4.4/§10.7, D9.

RECADRAGE 2026-07-23 : le premier fetch du modèle est un GESTE FONDATEUR —
le manifest committé porte des sources `null` et le CLI doit REFUSER toute
exécution (« source non approuvée : geste fondateur requis »). Ces tests
sont 100 % stdlib, ZÉRO réseau (aucun socket ouvert — imports réseau
empoisonnés pour LEVER s'ils sont touchés), zéro onnxruntime : la
vérification sha256 est prouvée sur de PETITS fichiers locaux factices
servis en `file://` (aucun Internet).

Périmètre :
- refus sans flag AVANT tout accès réseau ET avant lecture du manifest ;
- refus « source non approuvée » flag posé mais manifest incomplet
  (paramétré lacune par lacune, manifest COMMITTÉ inclus — il est
  INEXÉCUTABLE aujourd'hui, par construction) ;
- vérification sha256 sur fichier local factice, suppression sur mismatch,
  jamais d'écrasement silencieux, refus espace disque ;
- garde AST §10.7 : imports réseau UNIQUEMENT dans `_download()` ;
- manifest committé conforme §4.3 (recadré) ; .gitignore couvre le modèle ;
  requirements-embed non installable (pins candidats en commentaire).
"""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TOOLS_DIR = _REPO_ROOT / "router" / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import fetch_embed_model as fetch  # noqa: E402

_FLAG = "SOBRIO_ALLOW_MODEL_DOWNLOAD"
_REFUS_SOURCE = "source non approuvée : geste fondateur requis"

# Contenus factices DÉTERMINISTES (binaire/JSON neutre — aucun texte type
# prompt, convention chantier) pour la preuve sha256 sur fichiers locaux.
_CONTENU_MODEL = bytes(range(256)) * 3
_CONTENU_TOKENIZER = b'{"factice": true, "version": 1}'


def _sha256(contenu: bytes) -> str:
    return hashlib.sha256(contenu).hexdigest()


# ---------------------------------------------------------------------------
# Empoisonnement réseau : tout import d'un module réseau LÈVE (le refus doit
# se produire SANS le moindre accès réseau — recadrage Lot 2).
# ---------------------------------------------------------------------------

_MODULES_RESEAU = ("urllib.request", "http.client", "socket", "ssl")


class _ImportReseauInterdit:
    """Meta-path finder : lever si un module réseau est importé pendant le test."""

    def find_spec(self, fullname, path=None, target=None):  # noqa: ARG002
        if fullname in _MODULES_RESEAU:
            raise AssertionError(f"accès réseau tenté : import de {fullname}")
        return None


@pytest.fixture
def reseau_interdit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Purge les modules réseau déjà importés et fait LEVER tout ré-import."""
    for module in _MODULES_RESEAU:
        monkeypatch.delitem(sys.modules, module, raising=False)
    monkeypatch.setattr(sys, "meta_path", [_ImportReseauInterdit(), *sys.meta_path])


@pytest.fixture
def socket_ouverture_interdite(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pour les chemins `file://` : le module socket peut s'importer, mais
    toute OUVERTURE de connexion lève — preuve « aucun socket ouvert »."""
    import socket

    def _refus(*args, **kwargs):
        raise AssertionError("ouverture de socket interdite dans les tests du Lot 2")

    monkeypatch.setattr(socket.socket, "connect", _refus)


# ---------------------------------------------------------------------------
# Fabrique de manifests COMPLETS pointant sur des fichiers locaux (file://).
# ---------------------------------------------------------------------------


def _manifest_complet(
    tmp_path: Path,
    sha_model: str | None = None,
    url_model: str | None = None,
) -> Path:
    """Écrit sources factices + manifest COMPLET (variante int8) ; retourne son chemin."""
    src = tmp_path / "sources"
    src.mkdir(exist_ok=True)
    model = src / "model.onnx"
    model.write_bytes(_CONTENU_MODEL)
    tokenizer = src / "tokenizer.json"
    tokenizer.write_bytes(_CONTENU_TOKENIZER)
    manifest = {
        "model": "multilingual-e5-small",
        "license": "MIT",
        "dim": 384,
        "upstream_repo": "intfloat/multilingual-e5-small",
        "upstream_license": "MIT",
        "variants": {
            "int8": {
                "source_repo": "exportateur-factice/e5-int8",
                "source_license": "MIT",
                "source_verified_date": "2026-07-23",
                "files": {
                    "model.onnx": {
                        "url": url_model if url_model is not None else model.as_uri(),
                        "sha256": sha_model if sha_model is not None else _sha256(_CONTENU_MODEL),
                        "size_bytes": len(_CONTENU_MODEL),
                    },
                    "tokenizer.json": {
                        "url": tokenizer.as_uri(),
                        "sha256": _sha256(_CONTENU_TOKENIZER),
                        "size_bytes": len(_CONTENU_TOKENIZER),
                    },
                },
            }
        },
        "manifest_version": "1",
    }
    chemin = tmp_path / "manifest-test.json"
    chemin.write_text(json.dumps(manifest), encoding="utf-8")
    return chemin


# ---------------------------------------------------------------------------
# 1. Refus sans flag — PROUVÉ sans accès réseau.
# ---------------------------------------------------------------------------


def test_refus_sans_flag_sans_le_moindre_acces_reseau(monkeypatch, capsys, reseau_interdit):
    monkeypatch.delenv(_FLAG, raising=False)
    rc = fetch.main(["--variant", "int8"])
    assert rc == 2
    err = capsys.readouterr().err
    assert err.startswith("REFUS")
    assert _FLAG in err
    assert "LICENSES.md" in err


@pytest.mark.parametrize("valeur", ["0", "true", "", " 1", "1 ", "yes"])
def test_refus_flag_valeur_differente_de_1(monkeypatch, capsys, reseau_interdit, valeur):
    """Patron `SOBRIO_ALLOW_DATASET_DOWNLOAD` : EXACTEMENT '1', rien d'autre."""
    monkeypatch.setenv(_FLAG, valeur)
    rc = fetch.main(["--variant", "int8"])
    assert rc == 2
    assert _FLAG in capsys.readouterr().err


def test_refus_sans_flag_precede_la_lecture_du_manifest(monkeypatch, capsys, tmp_path):
    """L'ORDRE est normatif (spec §4.4) : flag AVANT manifest — un manifest
    inexistant ne change pas le message quand le flag est éteint."""
    monkeypatch.delenv(_FLAG, raising=False)
    rc = fetch.main(["--manifest", str(tmp_path / "inexistant.json")])
    assert rc == 2
    err = capsys.readouterr().err
    assert _FLAG in err
    assert "inexistant.json" not in err


def test_subprocess_flag_eteint_aucun_module_reseau_dans_sys_modules(tmp_path):
    """Spec §10.7 : flag éteint → refus SANS qu'aucun module réseau ne soit
    entré dans `sys.modules` (interpréteur frais, preuve par subprocess)."""
    script = (
        "import sys\n"
        "socket_au_depart = 'socket' in sys.modules\n"
        f"sys.path.insert(0, {str(_TOOLS_DIR)!r})\n"
        "import fetch_embed_model as fetch\n"
        "rc = fetch.main(['--variant', 'int8'])\n"
        "assert rc == 2, rc\n"
        "assert 'urllib.request' not in sys.modules\n"
        "assert 'http.client' not in sys.modules\n"
        "assert ('socket' in sys.modules) == socket_au_depart\n"
        "print('OK-refus-hors-reseau')\n"
    )
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}
    proc = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, env=env, check=False
    )
    assert proc.returncode == 0, proc.stderr
    assert "OK-refus-hors-reseau" in proc.stdout


# ---------------------------------------------------------------------------
# 2. Flag posé mais source NON APPROUVÉE (manifest incomplet) — cœur du
#    recadrage : le manifest COMMITTÉ est inexécutable aujourd'hui.
# ---------------------------------------------------------------------------


def test_manifest_committe_refuse_source_non_approuvee(monkeypatch, capsys, reseau_interdit):
    """Le chemin réseau existe dans le code mais est INEXÉCUTABLE avec le
    manifest du repo (sources null) — refus AVANT tout accès réseau."""
    monkeypatch.setenv(_FLAG, "1")
    rc = fetch.main(["--variant", "int8"])
    assert rc == 2
    assert _REFUS_SOURCE in capsys.readouterr().err


@pytest.mark.parametrize("variant", ["int8", "fp32"])
def test_manifest_committe_refuse_les_deux_variantes(monkeypatch, capsys, reseau_interdit, variant):
    monkeypatch.setenv(_FLAG, "1")
    rc = fetch.main(["--variant", variant])
    assert rc == 2
    assert _REFUS_SOURCE in capsys.readouterr().err


def _sans_cle(manifest: dict, *, variant: str = "int8", **mutations) -> dict:
    """Retourne une copie mutée de la variante (JSON round-trip = copie profonde)."""
    copie = json.loads(json.dumps(manifest))
    copie["variants"][variant].update(mutations)
    return copie


@pytest.mark.parametrize(
    "mutation",
    [
        {"source_repo": None},
        {"source_repo": "   "},
        {"source_license": None},
        {"source_verified_date": None},
        {"files": None},
    ],
    ids=lambda m: next(iter(m)),
)
def test_refus_source_incomplete_champ_par_champ(
    monkeypatch, capsys, tmp_path, reseau_interdit, mutation
):
    monkeypatch.setenv(_FLAG, "1")
    complet = json.loads(_manifest_complet(tmp_path).read_text(encoding="utf-8"))
    chemin = tmp_path / "manifest-mute.json"
    chemin.write_text(json.dumps(_sans_cle(complet, **mutation)), encoding="utf-8")
    rc = fetch.main(["--manifest", str(chemin), "--dest", str(tmp_path / "dest")])
    assert rc == 2
    assert _REFUS_SOURCE in capsys.readouterr().err


@pytest.mark.parametrize(
    "champ_fichier, valeur",
    [
        ("url", None),
        ("url", "ftp://exemple/model.onnx"),
        # http:// refusé (QA-R6-m2, ronde 1) : transport en clair exclu de
        # `_SCHEMES_AUTORISES` — seuls https:// et file:// sont admis.
        ("url", "http://exemple/model.onnx"),
        ("sha256", None),
        ("sha256", "abc123"),
        ("sha256", "Z" * 64),
        ("size_bytes", None),
        ("size_bytes", 0),
        ("size_bytes", True),
    ],
)
def test_refus_fichier_incomplet_champ_par_champ(
    monkeypatch, capsys, tmp_path, reseau_interdit, champ_fichier, valeur
):
    monkeypatch.setenv(_FLAG, "1")
    complet = json.loads(_manifest_complet(tmp_path).read_text(encoding="utf-8"))
    complet["variants"]["int8"]["files"]["model.onnx"][champ_fichier] = valeur
    chemin = tmp_path / "manifest-mute.json"
    chemin.write_text(json.dumps(complet), encoding="utf-8")
    rc = fetch.main(["--manifest", str(chemin), "--dest", str(tmp_path / "dest")])
    assert rc == 2
    assert _REFUS_SOURCE in capsys.readouterr().err


def test_refus_variante_absente_et_fichier_manquant(monkeypatch, capsys, tmp_path, reseau_interdit):
    monkeypatch.setenv(_FLAG, "1")
    complet = json.loads(_manifest_complet(tmp_path).read_text(encoding="utf-8"))
    # Variante demandée absente (le manifest de test ne porte pas fp32).
    chemin = tmp_path / "manifest-int8-seul.json"
    chemin.write_text(json.dumps(complet), encoding="utf-8")
    rc = fetch.main(["--manifest", str(chemin), "--variant", "fp32", "--dest", str(tmp_path / "d")])
    assert rc == 2
    assert _REFUS_SOURCE in capsys.readouterr().err
    # Entrée tokenizer.json manquante dans files.
    del complet["variants"]["int8"]["files"]["tokenizer.json"]
    chemin2 = tmp_path / "manifest-sans-tokenizer.json"
    chemin2.write_text(json.dumps(complet), encoding="utf-8")
    rc = fetch.main(["--manifest", str(chemin2), "--dest", str(tmp_path / "d")])
    assert rc == 2
    assert _REFUS_SOURCE in capsys.readouterr().err


def test_refus_manifest_corrompu_ou_non_objet(monkeypatch, capsys, tmp_path, reseau_interdit):
    monkeypatch.setenv(_FLAG, "1")
    corrompu = tmp_path / "corrompu.json"
    corrompu.write_text("{pas du json", encoding="utf-8")
    assert fetch.main(["--manifest", str(corrompu)]) == 2
    assert "REFUS" in capsys.readouterr().err
    non_objet = tmp_path / "liste.json"
    non_objet.write_text("[1, 2]", encoding="utf-8")
    assert fetch.main(["--manifest", str(non_objet)]) == 2
    assert "REFUS" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# 3. Vérification sha256 sur PETITS fichiers locaux (file:// — zéro Internet).
# ---------------------------------------------------------------------------


def test_fetch_local_verifie_sha_et_depose_les_fichiers(
    monkeypatch, capsys, tmp_path, socket_ouverture_interdite
):
    monkeypatch.setenv(_FLAG, "1")
    manifest = _manifest_complet(tmp_path)
    dest = tmp_path / "dest"
    rc = fetch.main(["--manifest", str(manifest), "--dest", str(dest)])
    assert rc == 0
    assert (dest / "model.onnx").read_bytes() == _CONTENU_MODEL
    assert (dest / "tokenizer.json").read_bytes() == _CONTENU_TOKENIZER
    assert not list(dest.glob("*.part"))
    sortie = capsys.readouterr().out
    assert _sha256(_CONTENU_MODEL) in sortie
    assert "2 fichiers" in sortie


def test_mismatch_sha_supprime_le_fichier_et_refuse(
    monkeypatch, capsys, tmp_path, socket_ouverture_interdite
):
    """Écart de sha : REFUS exit 2, fichier téléchargé SUPPRIMÉ, message =
    hash/chemins uniquement — rien n'est écrit sous la destination."""
    monkeypatch.setenv(_FLAG, "1")
    sha_faux = _sha256(b"autre-contenu")
    manifest = _manifest_complet(tmp_path, sha_model=sha_faux)
    dest = tmp_path / "dest"
    rc = fetch.main(["--manifest", str(manifest), "--dest", str(dest)])
    assert rc == 2
    assert list(dest.iterdir()) == []  # ni fichier final, ni .part restant
    err = capsys.readouterr().err
    assert sha_faux in err
    assert _sha256(_CONTENU_MODEL) in err


def test_jamais_d_ecrasement_silencieux_d_un_fichier_local_divergent(
    monkeypatch, capsys, tmp_path, socket_ouverture_interdite
):
    monkeypatch.setenv(_FLAG, "1")
    manifest = _manifest_complet(tmp_path)
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "model.onnx").write_bytes(b"contenu-local-divergent")
    rc = fetch.main(["--manifest", str(manifest), "--dest", str(dest)])
    assert rc == 2
    assert (dest / "model.onnx").read_bytes() == b"contenu-local-divergent"  # intact
    assert "REFUS" in capsys.readouterr().err


def test_fichier_local_identique_est_saute_sans_telechargement(monkeypatch, capsys, tmp_path):
    """sha local == manifest → « deja_present », AUCUN téléchargement (les
    URLs pointent vers des chemins SUPPRIMÉS : toute tentative lèverait)."""
    monkeypatch.setenv(_FLAG, "1")
    manifest = _manifest_complet(tmp_path)
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "model.onnx").write_bytes(_CONTENU_MODEL)
    (dest / "tokenizer.json").write_bytes(_CONTENU_TOKENIZER)
    for source in (tmp_path / "sources").iterdir():
        source.unlink()
    rc = fetch.main(["--manifest", str(manifest), "--dest", str(dest)])
    assert rc == 0
    assert capsys.readouterr().out.count("deja_present") == 2


@pytest.mark.parametrize(
    "exception_cls, nom_classe",
    [
        ("URLError", "URLError"),
        ("FileNotFoundError", "FileNotFoundError"),
    ],
    ids=str,
)
def test_echec_de_telechargement_refus_exit2_sans_traceback(
    monkeypatch, capsys, tmp_path, socket_ouverture_interdite, exception_cls, nom_classe
):
    """QA-R6-M2 (ronde 0) : un échec du téléchargement lui-même — panne réseau
    transitoire (URLError) ou chemin inexistant (FileNotFoundError), le
    scénario RÉALISTE du premier fetch du geste fondateur — produit un REFUS
    « téléchargement échoué : <nom> (<classe>) » exit 2, ZÉRO traceback,
    fichier temporaire supprimé. Prouvé HORS RÉSEAU : `_download`
    monkeypatché pour lever."""
    monkeypatch.setenv(_FLAG, "1")
    manifest = _manifest_complet(tmp_path)

    def _panne(url, dest):
        if exception_cls == "URLError":
            import urllib.error

            raise urllib.error.URLError("connexion interrompue (simulation hors réseau)")
        raise FileNotFoundError(2, "chemin source inexistant (simulation)")

    monkeypatch.setattr(fetch, "_download", _panne)
    dest = tmp_path / "dest"
    rc = fetch.main(["--manifest", str(manifest), "--dest", str(dest)])
    assert rc == 2
    err = capsys.readouterr().err
    assert err.startswith("REFUS")
    assert "téléchargement échoué" in err
    assert "model.onnx" in err  # le nom du fichier en échec
    assert nom_classe in err  # la classe d'exception, jamais son contenu
    assert "Traceback" not in err
    assert not list(dest.glob("*.part"))  # le finally a supprimé le temporaire
    assert not (dest / "model.onnx").exists()


def test_refus_espace_disque_insuffisant_avant_telechargement(
    monkeypatch, capsys, tmp_path, reseau_interdit
):
    """La sonde disque REFUSE avant tout téléchargement (marge 200 Mo) —
    réseau empoisonné : le refus doit arriver sans l'avoir touché."""
    monkeypatch.setenv(_FLAG, "1")
    manifest = _manifest_complet(tmp_path)

    def _disque_plein(chemin):
        return type("Usage", (), {"total": 10**12, "used": 10**12 - 1024, "free": 1024})()

    monkeypatch.setattr(fetch.shutil, "disk_usage", _disque_plein)
    rc = fetch.main(["--manifest", str(manifest), "--dest", str(tmp_path / "dest")])
    assert rc == 2
    assert "espace disque insuffisant" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# 4. Garde AST (spec §10.7) : imports réseau UNIQUEMENT dans `_download()`.
# ---------------------------------------------------------------------------

_RACINES_RESEAU = {"urllib", "http", "socket", "ssl", "httpx", "requests", "anthropic", "openai"}


def _noeuds_import_reseau(arbre: ast.AST) -> list[int]:
    lignes = []
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            if any(alias.name.split(".")[0] in _RACINES_RESEAU for alias in noeud.names):
                lignes.append(noeud.lineno)
        elif isinstance(noeud, ast.ImportFrom):
            if noeud.module and noeud.module.split(".")[0] in _RACINES_RESEAU:
                lignes.append(noeud.lineno)
    return sorted(lignes)


def test_garde_ast_imports_reseau_uniquement_dans_download():
    source = (_TOOLS_DIR / "fetch_embed_model.py").read_text(encoding="utf-8")
    arbre = ast.parse(source)
    dans_module = _noeuds_import_reseau(arbre)
    fonctions_download = [
        noeud
        for noeud in ast.walk(arbre)
        if isinstance(noeud, ast.FunctionDef) and noeud.name == "_download"
    ]
    assert len(fonctions_download) == 1
    dans_download = _noeuds_import_reseau(fonctions_download[0])
    assert dans_module == dans_download, (
        f"imports réseau hors _download : {sorted(set(dans_module) - set(dans_download))}"
    )
    assert len(dans_download) >= 1  # la garde n'est pas vide : urllib.request y vit


def test_garde_ast_detecte_une_injection_hors_download(tmp_path):
    """Contrôle négatif (patron M6) : un import réseau au niveau module DOIT
    être vu par la garde."""
    source = (_TOOLS_DIR / "fetch_embed_model.py").read_text(encoding="utf-8")
    empoisonne = ast.parse(source + "\nimport socket\n")
    dans_module = _noeuds_import_reseau(empoisonne)
    fonction = next(
        noeud
        for noeud in ast.walk(empoisonne)
        if isinstance(noeud, ast.FunctionDef) and noeud.name == "_download"
    )
    assert set(dans_module) - set(_noeuds_import_reseau(fonction))


def test_aucun_import_module_niveau_module_du_paquet_tools():
    """`router/tools/__init__.py` reste VIDE (spec §1.1) — aucun code exécuté
    à l'import du paquet."""
    assert (_TOOLS_DIR / "__init__.py").read_text(encoding="utf-8").strip() == ""


# ---------------------------------------------------------------------------
# 5. Manifest COMMITTÉ conforme §4.3 (recadré) — bi-variante, sources null,
#    mention d'approbation, candidats documentés sans choix.
# ---------------------------------------------------------------------------


def _manifest_committe() -> dict:
    return json.loads((_TOOLS_DIR / "embed_model_manifest.json").read_text(encoding="utf-8"))


def test_manifest_committe_structure_et_amont():
    manifest = _manifest_committe()
    assert manifest["model"] == "multilingual-e5-small"
    assert manifest["upstream_repo"] == "intfloat/multilingual-e5-small"
    assert manifest["upstream_license"] == "MIT"
    assert manifest["dim"] == 384
    assert manifest["manifest_version"] == "1"
    assert set(manifest["variants"]) == {"int8", "fp32"}


@pytest.mark.parametrize("variant", ["int8", "fp32"])
def test_manifest_committe_sources_null_en_attente_du_geste(variant):
    donnees = _manifest_committe()["variants"][variant]
    assert donnees["source_repo"] is None
    assert donnees["source_license"] is None
    assert donnees["source_verified_date"] is None
    assert set(donnees["files"]) == {"model.onnx", "tokenizer.json"}
    for entree in donnees["files"].values():
        assert entree["url"] is None
        assert entree["sha256"] is None
        assert entree["size_bytes"] is None


def test_croise_litteraux_embed_spec_egaux_au_manifest_int8():
    """ML-R6r0-m2 / DQ-R6-m1 (ronde 0) : les littéraux sha d'`embed.py` (via
    `expected_embed_spec()`) sont ÉGAUX aux sha256 int8 du manifest committé
    (spec §6.1 « littéral, = manifest int8 ») — vrai aujourd'hui (None ==
    null, geste fondateur non advenu) et VERROU automatique le jour J :
    renseigner UN SEUL des deux côtés fait échouer la suite immédiatement,
    au lieu d'une EmbedLoadError tardive découverte au runtime. Stdlib,
    toujours exécuté."""
    from sobrio_router.embed import expected_embed_spec

    fichiers = _manifest_committe()["variants"]["int8"]["files"]
    spec = expected_embed_spec()
    assert spec["encoder_sha256"] == fichiers["model.onnx"]["sha256"]
    assert spec["tokenizer_sha256"] == fichiers["tokenizer.json"]["sha256"]


def test_manifest_committe_mention_d_approbation_et_candidats_sans_choix():
    manifest = _manifest_committe()
    assert "À APPROUVER PAR LE FONDATEUR" in manifest["statut"]
    assert "geste" in manifest["statut"]
    documentation = manifest["documentation_candidats"]
    assert len(documentation["candidats"]) >= 2  # informatif : officiel éventuel + communautaires
    assert "AUCUN" in documentation["note"]


# ---------------------------------------------------------------------------
# 6. Hygiène du lot : gitignore, requirements-embed, tailles committées.
# ---------------------------------------------------------------------------


def test_gitignore_couvre_le_repertoire_du_modele():
    """`router/artifacts/embed/` est ignoré via `router/artifacts/*` — et
    AUCUNE exception ne le ré-inclut (seuls bench/ et eval/ le sont)."""
    lignes = [
        ligne.strip()
        for ligne in (_REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        if ligne.strip() and not ligne.strip().startswith("#")
    ]
    assert "router/artifacts/*" in lignes
    reinclusions = [ligne for ligne in lignes if ligne.startswith("!router/artifacts/")]
    assert reinclusions == [
        "!router/artifacts/bench/",
        "!router/artifacts/bench/*",
        "!router/artifacts/eval/",
        "!router/artifacts/eval/*",
    ]
    assert not any("embed" in ligne for ligne in reinclusions)


def test_requirements_embed_pins_candidats_en_commentaire_non_installables():
    """Recadrage : onnxruntime/tokenizers NE sont PAS installables depuis le
    fichier (pins CANDIDATS en commentaire, confirmés au geste fondateur)."""
    contenu = (_REPO_ROOT / "router" / "requirements-embed.txt").read_text(encoding="utf-8")
    lignes_actives = [
        ligne.strip()
        for ligne in contenu.splitlines()
        if ligne.strip() and not ligne.strip().startswith("#")
    ]
    assert not any("onnxruntime" in ligne for ligne in lignes_actives)
    assert not any("tokenizers" in ligne for ligne in lignes_actives)
    assert "# onnxruntime==" in contenu
    assert "# tokenizers==" in contenu
    assert "geste fondateur" in contenu
    assert "numpy==2.5.1" in lignes_actives  # pin connu, aligné requirements-ml


def test_fichiers_committes_du_lot_sous_1_mo():
    """Verrou « rien > 20 Mo commité » avec marge (spec §10.5) — appliqué aux
    fichiers du Lot 2."""
    for relatif in (
        "router/tools/fetch_embed_model.py",
        "router/tools/embed_model_manifest.json",
        "router/tools/__init__.py",
        "router/requirements-embed.txt",
        "router/tests/test_router_tools_fetch.py",
    ):
        assert (_REPO_ROOT / relatif).stat().st_size < 1_000_000, relatif
