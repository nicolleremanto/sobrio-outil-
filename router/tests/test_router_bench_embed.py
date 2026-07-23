"""Tests du bench du pipeline complet étage 2 (`router/bench_embed.py`) — R6 Lot 6, §11/§10.5.

RECADRAGE (ledger 2026-07-23, geste fondateur non advenu) : le bench RÉEL
est impossible aujourd'hui — deps/modèle absents => REFUS exit 2 propre
(message renvoyant au geste fondateur), testé ici DÉTERMINISTIQUEMENT
(chemins monkeypatchés) ET dans un interpréteur aux deps empoisonnées.
La logique de MESURE (soupes seedées, warmup, percentiles, conversion RSS
par plateforme, rapport, verdicts aux bornes) est prouvée avec un encodeur
FACTICE monkeypatché — 100 % stdlib, aucune dépendance embed requise.

Convention d'import : `sys.path.insert` de `router/` racine (module
autonome, même esprit que `router/data/` dans test_router_data_distill).
Textes = soupes de mots-vides seedées (convention §10.1) — JAMAIS de texte
type prompt.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import promote_embed  # noqa: E402 — cohérence bench <-> garde D8 (conftest : router/train/)

import bench_embed  # noqa: E402
from sobrio_router.embed import ENCODER_DIR, EmbedHead, EmbedRouter  # noqa: E402
from sobrio_router.ml import LABEL_ORDER  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# Soupes de mots-vides : déterminisme, bornes, mélange fr/en, vocab fermé.
# ---------------------------------------------------------------------------


def test_soupes_deterministes_bit_identiques():
    premier = bench_embed.generer_soupes(500, bench_embed._SEED)
    second = bench_embed.generer_soupes(500, bench_embed._SEED)
    assert premier == second
    assert len(premier) == 500


def test_soupes_longueurs_bornees_10_4000():
    soupes = bench_embed.generer_soupes(500, bench_embed._SEED)
    for soupe in soupes:
        assert 10 <= len(soupe) <= 4000


def test_soupes_melange_fr_en_et_vocabulaire_ferme():
    """Chaque mot COMPLET vient du vocabulaire de mots-vides (le dernier mot
    peut être tronqué au caractère près) ; les deux langues sont présentes."""
    soupes = bench_embed.generer_soupes(100, bench_embed._SEED)
    vocab_fr = set(bench_embed._MOTS_VIDES["fr"])
    vocab_en = set(bench_embed._MOTS_VIDES["en"])
    vus_fr = vus_en = 0
    for soupe in soupes:
        mots = soupe.split(" ")[:-1]  # le dernier mot peut être tronqué
        assert set(mots) <= vocab_fr | vocab_en, sorted(set(mots) - (vocab_fr | vocab_en))
        if set(mots) <= vocab_fr:
            vus_fr += 1
        if set(mots) <= vocab_en:
            vus_en += 1
    assert vus_fr > 0 and vus_en > 0


def test_seed_change_change_les_soupes():
    assert bench_embed.generer_soupes(50, 42) != bench_embed.generer_soupes(50, 43)


# ---------------------------------------------------------------------------
# Conversion RSS (§11, MINOR-4) : les DEUX branches de plateforme.
# ---------------------------------------------------------------------------


def test_rss_darwin_ru_maxrss_en_octets():
    assert bench_embed.rss_peak_mb(512 * 1024 * 1024, "darwin") == 512.0


def test_rss_linux_ru_maxrss_en_kilo_octets():
    assert bench_embed.rss_peak_mb(512 * 1024, "linux") == 512.0


def test_rss_facteur_1024_entre_les_deux_branches():
    """Le cœur de MINOR-4 : même ru_maxrss, verdicts distants d'un facteur
    1024 selon la plateforme — la conversion est bien PAR plateforme."""
    ru = 800 * 1024 * 1024  # 800 Mo si darwin (octets), ~819200 Mo si Linux (Ko)
    assert bench_embed.rss_peak_mb(ru, "darwin") == 800.0
    assert bench_embed.rss_peak_mb(ru, "linux") == 1024 * bench_embed.rss_peak_mb(ru, "darwin")


# ---------------------------------------------------------------------------
# Verdicts aux bornes (§11) : p95 INCLUSIF, RSS STRICT.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("p95", "rss", "attendu"),
    [
        (30.0, 100.0, 0),  # borne p95 INCLUSIVE : 30.0 exact PASSE
        (30.0001, 100.0, 1),  # au-delà : ÉCHEC
        (1.0, 1023.99, 0),  # sous le plafond RSS : PASSE
        (1.0, 1024.0, 1),  # borne RSS STRICTE : 1024.0 exact ÉCHOUE
        (30.0001, 1024.0, 1),
    ],
)
def test_code_sortie_bornes(p95: float, rss: float, attendu: int):
    assert bench_embed.code_sortie(p95, rss) == attendu


def test_budgets_alignes_sur_la_garde_d8_de_promote_embed():
    """Le bench PROUVE ce que la garde D8 EXIGE : mêmes budgets, même chemin
    de rapport — un désalignement rendrait la preuve invérifiable."""
    assert bench_embed.P95_BUDGET_MS == promote_embed.BUDGET_MS == 30.0
    assert bench_embed.RSS_MAX_MB == promote_embed.RSS_MAX_MB == 1024.0
    assert bench_embed._ARTIFACT_PATH == promote_embed.BENCH_REPORT_PATH


# ---------------------------------------------------------------------------
# Sélection de tête (§11) : candidate > promoted > tête neutre jetable.
# ---------------------------------------------------------------------------


def _tetes_monkeypatchees(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, Path]:
    candidate = tmp_path / "heads" / "candidate"
    promoted = tmp_path / "heads" / "promoted"
    monkeypatch.setattr(bench_embed, "CANDIDATE_DIR", candidate)
    monkeypatch.setattr(bench_embed, "PROMOTED_DIR", promoted)
    return candidate, promoted


def test_selection_tete_priorite_candidate_puis_promoted_puis_none(monkeypatch, tmp_path):
    from test_router_embed import _ecrire_tete

    candidate, promoted = _tetes_monkeypatchees(monkeypatch, tmp_path)
    assert bench_embed._tete_dir_selectionnee() is None
    _ecrire_tete(promoted)
    assert bench_embed._tete_dir_selectionnee() == promoted
    _ecrire_tete(candidate)
    assert bench_embed._tete_dir_selectionnee() == candidate


def test_selection_ignore_une_tete_incomplete(monkeypatch, tmp_path):
    """Un dossier partiel (fichier manquant) n'est PAS sélectionné."""
    candidate, _ = _tetes_monkeypatchees(monkeypatch, tmp_path)
    candidate.mkdir(parents=True)
    (candidate / "head.json").write_text("{}", encoding="utf-8")
    assert bench_embed._tete_dir_selectionnee() is None


def test_tete_neutre_passe_le_chargement_fail_closed_reel(tmp_path):
    """La tête neutre jetable emprunte `EmbedHead.load` RÉEL (gardes §5.1
    comprises) et émet une confiance uniforme 1/3 — nombres uniquement."""
    directory = bench_embed._ecrire_tete_neutre(tmp_path / "tete-neutre")
    tete = EmbedHead.load(directory)
    label, confiance = tete.predict([0.0] * 384)
    assert label == LABEL_ORDER[0]
    assert confiance == pytest.approx(1 / 3)


# ---------------------------------------------------------------------------
# REFUS exit 2 avant geste fondateur (recadrage ledger 2026-07-23).
# ---------------------------------------------------------------------------


def test_refus_exit_2_sans_encodeur_ni_tete(monkeypatch, capsys, tmp_path):
    """Déterministe quel que soit le poste : chemins pointés sur du vide —
    REFUS exit 2, message « geste fondateur », RIEN n'est écrit."""
    _tetes_monkeypatchees(monkeypatch, tmp_path)
    monkeypatch.setattr(bench_embed, "ENCODEUR_DIR", tmp_path / "encodeur-absent")
    artefact = tmp_path / "bench" / "embed-latest.json"
    monkeypatch.setattr(bench_embed, "_ARTIFACT_PATH", artefact)

    assert bench_embed.main() == 2

    sortie = capsys.readouterr()
    assert "REFUS" in sortie.err
    assert "GESTE FONDATEUR" in sortie.err
    assert "router-embed-model" in sortie.err
    assert not artefact.exists()
    assert not artefact.parent.exists()


def test_refus_exit_2_deps_embed_absentes_en_subprocess(tmp_path):
    """Interpréteur frais aux deps embed EMPOISONNÉES (patron §10.6) : même
    avec un encodeur local présent, le bench REFUSE exit 2 proprement —
    c'est l'état RÉEL du poste avant le geste fondateur."""
    script = """
import sys
from pathlib import Path


class _BloqueurDepsEmbed:
    _RACINES = ("onnxruntime", "tokenizers", "numpy")

    def find_spec(self, name, path=None, target=None):
        for racine in self._RACINES:
            if name == racine or name.startswith(racine + "."):
                raise ImportError(f"{racine} bloque (simulation absence)")
        return None


sys.meta_path.insert(0, _BloqueurDepsEmbed())
sys.path.insert(0, sys.argv[1])

import bench_embed

bench_embed._ARTIFACT_PATH = Path(sys.argv[2]) / "embed-latest.json"
raise SystemExit(bench_embed.main())
"""
    racine_router = str(Path(__file__).resolve().parents[1])
    proc = subprocess.run(
        [sys.executable, "-c", script, racine_router, str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 2, proc.stderr
    assert "REFUS" in proc.stderr
    assert "GESTE FONDATEUR" in proc.stderr
    assert "Traceback" not in proc.stderr
    assert not (tmp_path / "embed-latest.json").exists()


# ---------------------------------------------------------------------------
# Logique de mesure PROUVÉE avec un encodeur FACTICE (§10.5, recadrage) :
# pipeline decide() réel (troncature + préfixe + tête §5.2bis), seul
# `_embed` est monkeypatché — le bench réel attend le geste fondateur.
# ---------------------------------------------------------------------------

_OCTETS_ONNX_FACTICES = b"onnx-factice-bench-lot6"


def _routeur_factice(tmp_path: Path, appels: list[str]) -> EmbedRouter:
    """EmbedRouter sans __init__ : tête neutre RÉELLE (chargée fail-closed),
    encodeur remplacé par un embedding constant qui JOURNALISE ses entrées."""
    tete = EmbedHead.load(bench_embed._ecrire_tete_neutre(tmp_path / "tete-neutre"))
    routeur = EmbedRouter.__new__(EmbedRouter)
    routeur._head = tete

    def _embed_factice(prefixe: str) -> list[float]:
        appels.append(prefixe)
        return [1.0] + [0.0] * 383

    routeur._embed = _embed_factice
    return routeur


def _main_avec_encodeur_factice(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, ru_maxrss: int | None = None
) -> tuple[int, Path, list[str]]:
    encodeur_dir = tmp_path / "encodeur"
    encodeur_dir.mkdir(parents=True)
    (encodeur_dir / "model.onnx").write_bytes(_OCTETS_ONNX_FACTICES)
    monkeypatch.setattr(bench_embed, "ENCODEUR_DIR", encodeur_dir)
    artefact = tmp_path / "bench" / "embed-latest.json"
    monkeypatch.setattr(bench_embed, "_ARTIFACT_PATH", artefact)

    # ru_maxrss FIXÉ (déterminisme, leçon flake de l'audit de reprise) : le
    # pic RSS réel du processus pytest dépend des tests voisins — défaut :
    # 384 Mo exprimés dans l'unité de la plateforme courante (§11, MINOR-4).
    if ru_maxrss is None:
        ru_maxrss = 384 * (1024 * 1024 if bench_embed.sys.platform == "darwin" else 1024)
    usage = type("_Usage", (), {"ru_maxrss": ru_maxrss})()
    monkeypatch.setattr(bench_embed.resource, "getrusage", lambda who: usage)

    appels: list[str] = []
    routeur = _routeur_factice(tmp_path, appels)
    monkeypatch.setattr(bench_embed, "_construire_routeur", lambda: (routeur, "ab" * 32))
    return bench_embed.main(), artefact, appels


def test_main_encodeur_factice_exit_0_et_rapport_complet(monkeypatch, tmp_path, capsys):
    code, artefact, appels = _main_avec_encodeur_factice(monkeypatch, tmp_path)
    assert code == 0

    rapport = json.loads(artefact.read_text(encoding="utf-8"))
    assert set(rapport) == {
        "n",
        "p50_ms",
        "p95_ms",
        "rss_peak_mb",
        "platform",
        "encoder_sha256",
        "head_sha256",
        "date",
        "git_sha",
    }
    assert rapport["n"] == 500
    assert 0.0 <= rapport["p50_ms"] <= rapport["p95_ms"]
    assert rapport["rss_peak_mb"] > 0.0
    assert rapport["platform"] == sys.platform
    assert rapport["encoder_sha256"] == hashlib.sha256(_OCTETS_ONNX_FACTICES).hexdigest()
    assert rapport["head_sha256"] == "ab" * 32

    # Le stdout est le MÊME JSON que le fichier (aucun autre texte en sortie standard).
    sortie = capsys.readouterr()
    assert json.loads(sortie.out) == rapport

    # Warmup 50 + mesure 500 : le pipeline decide() a bien tourné 550 fois,
    # chaque entrée préfixée e5 et tronquée (bornes D11/§5.2.2-3).
    assert len(appels) == 550
    for prefixe in appels:
        assert prefixe.startswith("query: ")
        assert len(prefixe) <= len("query: ") + 4000


def test_rapport_sans_le_moindre_texte_libre(monkeypatch, tmp_path, capsys):
    """§10.1 : parcours COMPLET de l'arbre JSON — clés identifiantes, chaînes
    = plateforme, hash, date. AUCUN mot de soupe, AUCUN champ texte."""
    _, artefact, appels = _main_avec_encodeur_factice(monkeypatch, tmp_path)
    rapport = json.loads(artefact.read_text(encoding="utf-8"))

    motifs_surs = (
        re.compile(r"^[0-9a-f]{7,64}$"),  # sha256 / git sha court
        re.compile(r"^\d{4}-\d{2}-\d{2}[T ]?[\d:.+]*$"),  # date ISO
        re.compile(r"^unknown$"),  # _git_sha hors dépôt
    )
    for cle, valeur in rapport.items():
        assert re.match(r"^[a-z0-9_]+$", cle), cle
        assert cle not in {"prompt", "prompt_text", "text", "texte", "contenu"}
        if isinstance(valeur, str):
            assert valeur == sys.platform or any(m.match(valeur) for m in motifs_surs), valeur

    # Aucun fragment de soupe (mots-vides consécutifs) nulle part dans le
    # fichier écrit : les textes de mesure restent EN MÉMOIRE.
    brut = artefact.read_text(encoding="utf-8")
    for soupe in bench_embed.generer_soupes(5, bench_embed._SEED):
        assert soupe[:10] not in brut
    assert appels  # la mesure a réellement traversé l'encodeur factice


def test_platform_et_conversion_rss_cables_sur_la_plateforme_courante(monkeypatch, tmp_path):
    """Câblage main() (plateforme MONKEYPATCHÉE, §11) : `platform` consigné
    = sys.platform injecté, et la branche de conversion correspondante est
    bien celle appliquée à ru_maxrss — même valeur brute, verdicts opposés."""
    ru_fixe = 256 * 1024 * 1024  # 256 Mo en octets (darwin) / 262144 Mo en Ko (linux)

    monkeypatch.setattr(bench_embed.sys, "platform", "darwin")
    code, artefact, _ = _main_avec_encodeur_factice(monkeypatch, tmp_path / "d", ru_fixe)
    rapport = json.loads(artefact.read_text(encoding="utf-8"))
    assert rapport["platform"] == "darwin"
    assert rapport["rss_peak_mb"] == 256.0
    assert code == 0

    monkeypatch.setattr(bench_embed.sys, "platform", "linux")
    code, artefact, _ = _main_avec_encodeur_factice(monkeypatch, tmp_path / "l", ru_fixe)
    rapport = json.loads(artefact.read_text(encoding="utf-8"))
    assert rapport["platform"] == "linux"
    assert rapport["rss_peak_mb"] == 262144.0
    assert code == 1  # 262144 Mo >= plafond 1024 : le verdict RSS mord bien


# ---------------------------------------------------------------------------
# Tests tailles (§10.5, périmètre Lot 6).
# ---------------------------------------------------------------------------


def test_taille_encodeur_sous_500_mo():
    """§7/§10.5 : artefact modèle < 500 Mo — skip si modèle absent (patron
    corpus R5 ; le geste fondateur n'a pas eu lieu : skip attendu aujourd'hui)."""
    model = ENCODER_DIR / "model.onnx"
    tokenizer = ENCODER_DIR / "tokenizer.json"
    if not (model.is_file() and tokenizer.is_file()):
        pytest.skip("modèle e5 absent — récupérer via make router-embed-model")
    total = model.stat().st_size + tokenizer.stat().st_size
    assert total < 500 * 1024 * 1024, f"encodeur {total} octets >= 500 Mo (§7)"


def test_fichiers_committes_du_lot_sous_1_mo():
    """Verrou « rien > 20 Mo commité » avec marge (§10.5) — TOUJOURS actif,
    appliqué aux fichiers des Lots 6-7 (patron du test jumeau Lot 2)."""
    for relatif in (
        "router/bench_embed.py",
        "router/tests/test_router_bench_embed.py",
        "router/tests/test_router_ci_workflow.py",
        ".github/workflows/ci.yml",
        "Makefile",
    ):
        assert (_REPO_ROOT / relatif).stat().st_size < 1_000_000, relatif


def test_verdict_echec_p95_imprime_et_exit_1(monkeypatch, tmp_path, capsys):
    """p95 au-delà du budget (horloge monkeypatchée) : rapport ÉCRIT quand
    même (preuve d'échec consignée) puis exit 1 avec message §7/§11."""
    compteur = iter(range(10**6))
    # Chaque paire (début, fin) avance de 1 s => toutes les latences = 1000 ms.
    monkeypatch.setattr(bench_embed.time, "perf_counter", lambda: float(next(compteur)))
    code, artefact, _ = _main_avec_encodeur_factice(monkeypatch, tmp_path)
    assert code == 1
    rapport = json.loads(artefact.read_text(encoding="utf-8"))
    assert rapport["p95_ms"] > bench_embed.P95_BUDGET_MS
    assert "ÉCHEC" in capsys.readouterr().err
