"""Tests du pipeline de distillation dry-run (`router/data/distill.py`, chantier R4).

Convention d'import : `sys.path.insert` de `router/data/` (module autonome,
même esprit que `router/eval/loader.py`).
"""

from __future__ import annotations

import gzip
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data"))

import distill  # noqa: E402
import generate_corpus  # noqa: E402
import public_datasets  # noqa: E402
import quality_report  # noqa: E402
from generate_corpus import generate  # noqa: E402

from sobrio_router import VISIBLE_MODELS  # noqa: E402

# Garde renforcée (M6, correction ronde 0) : la version précédente ne
# cherchait que la sous-chaîne littérale `"import X"` — un `from httpx
# import Client` passait inaperçu. Ancrée en DÉBUT DE LIGNE (`^\s*`,
# MULTILINE) : ne détecte que de VRAIS imports de module, jamais une
# mention en prose au milieu d'une ligne de docstring (ex. « ni de client
# HTTP (`httpx`, `requests`, ... »).
_NETWORK_IMPORT_RE = re.compile(
    r"^\s*(import|from)\s+(anthropic|openai|httpx|requests|socket|urllib|http\b)",
    re.MULTILINE,
)


@pytest.fixture
def small_corpus(tmp_path: Path) -> Path:
    rows, _, _ = generate(50, seed=4242, bruit_rate=0.03)
    payload = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n"
    path = tmp_path / "corpus-v1.jsonl.gz"
    path.write_bytes(gzip.compress(payload.encode("utf-8"), mtime=0))
    return path


@pytest.fixture(autouse=True)
def _reset_stop_counter():
    """Le compteur d'arrêt est un état module-level : isole les tests entre eux."""
    distill._stop_counter = 0
    yield
    distill._stop_counter = 0


# ---------------------------------------------------------------------------
# Aucun motif réseau dans les modules de router/data/ (invariant cost-guard,
# M6 : garde renforcée regex `import X` ET `from X import Y`, appliquée aux
# QUATRE modules de router/data/ — distill/public_datasets/quality_report
# (les trois modules existants) + generate_corpus (devenu golden-aware, M1 :
# importe `loader`, doit rester lui aussi exempt de tout motif réseau).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "module", [distill, public_datasets, quality_report, generate_corpus], ids=lambda m: m.__name__
)
def test_no_network_imports_in_router_data_modules(module):
    source = Path(module.__file__).read_text(encoding="utf-8")
    match = _NETWORK_IMPORT_RE.search(source)
    assert match is None, (
        f"import réseau interdit détecté dans {module.__name__} : {match.group(0)!r}"
    )
    assert "urlopen" not in source
    assert "Anthropic(" not in source


def test_no_network_imports_in_distill_module():
    source = Path(distill.__file__).read_text(encoding="utf-8")
    forbidden = ("anthropic", "httpx", "requests", "urllib.request", "socket", "http.client")
    for name in forbidden:
        assert f"import {name}" not in source, f"import réseau interdit trouvé : {name}"
    assert "urlopen" not in source
    assert "Anthropic(" not in source


def test_no_network_imports_in_public_datasets_module():
    source = Path(public_datasets.__file__).read_text(encoding="utf-8")
    forbidden = ("anthropic", "httpx", "requests", "urllib.request", "socket", "http.client")
    for name in forbidden:
        assert f"import {name}" not in source, f"import réseau interdit trouvé : {name}"


def test_network_import_guard_detects_bare_import_and_from_import():
    """Contrôle négatif : la regex détecte bien LES DEUX formes, prouvé par injection.

    Avant M6, seule la sous-chaîne `"import X"` était cherchée : un `from
    httpx import Client` ne déclenchait AUCUNE alerte (défaut prouvé ici en
    reproduisant l'ancienne logique sur le même échantillon empoisonné).
    """
    poisoned_bare = "from __future__ import annotations\n\nimport socket\n"
    poisoned_from = "from __future__ import annotations\n\nfrom httpx import Client\n"
    clean = Path(distill.__file__).read_text(encoding="utf-8")

    assert _NETWORK_IMPORT_RE.search(poisoned_bare) is not None
    match_from = _NETWORK_IMPORT_RE.search(poisoned_from)
    assert match_from is not None
    assert "httpx" in match_from.group(0)
    assert _NETWORK_IMPORT_RE.search(clean) is None

    # L'ANCIENNE garde (substring "import X") ratait la forme from-import :
    forbidden = ("anthropic", "httpx", "requests", "urllib.request", "socket", "http.client")
    old_guard_would_catch = any(f"import {name}" in poisoned_from for name in forbidden)
    assert old_guard_would_catch is False, "l'ancienne garde aurait dû rater ce cas (régression)"


def test_network_import_guard_detects_from_import_when_injected_in_tmp_copy(tmp_path):
    """Preuve par exécution (M6) : copie /tmp d'un module réel, empoisonnée d'un
    `from X import Y`, détectée par la garde renforcée — alors que l'ANCIENNE
    garde (substring `"import X"`) la ratait (défaut réel corrigé par M6) :
    `"from httpx import AsyncClient"` ne contient JAMAIS la sous-chaîne
    `"import httpx"` (l'ordre des mots est inversé)."""
    real_source = Path(public_datasets.__file__).read_text(encoding="utf-8")
    poisoned_path = tmp_path / "public_datasets_poisoned.py"
    poisoned_path.write_text(
        real_source + "\nfrom httpx import AsyncClient  # injection de test M6\n",
        encoding="utf-8",
    )
    poisoned_source = poisoned_path.read_text(encoding="utf-8")

    # Nouvelle garde (M6) : détecte.
    match = _NETWORK_IMPORT_RE.search(poisoned_source)
    assert match is not None
    assert "httpx" in match.group(0)

    # Ancienne garde (substring "import X") : NE détecte PAS — c'est
    # exactement le défaut que M6 corrige.
    forbidden = ("anthropic", "httpx", "requests", "urllib.request", "socket", "http.client")
    old_guard_would_flag = any(f"import {name}" in poisoned_source for name in forbidden)
    assert old_guard_would_flag is False, "l'ancienne garde aurait dû rater ce cas (régression)"


# ---------------------------------------------------------------------------
# Coût — cohérence avec le catalogue
# ---------------------------------------------------------------------------


def test_catalog_prices_cover_visible_models_and_are_positive():
    prices = distill._catalog_prices()
    assert VISIBLE_MODELS <= set(prices)
    for model in VISIBLE_MODELS:
        assert prices[model]["price_in_usd_mtok"] > 0
        assert prices[model]["price_out_usd_mtok"] >= prices[model]["price_in_usd_mtok"]


def test_estimate_cost_is_positive_and_scales_with_n(small_corpus, tmp_path):
    estimate = distill.estimate_cost(small_corpus)
    assert estimate["n_lignes"] == 50
    assert estimate["cout_estime_usd"] > 0
    assert estimate["teacher_model_hypothese"] == distill._DEFAULT_TEACHER_MODEL

    rows, _, _ = generate(100, seed=4242, bruit_rate=0.03)
    payload = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n"
    bigger = tmp_path / "bigger.jsonl.gz"
    bigger.write_bytes(gzip.compress(payload.encode("utf-8"), mtime=0))
    bigger_estimate = distill.estimate_cost(bigger)
    # Deux fois plus de lignes, même distribution de longueur -> coût ~doublé.
    assert bigger_estimate["cout_estime_usd"] > estimate["cout_estime_usd"]


def test_estimate_cost_unknown_teacher_model_raises(small_corpus):
    with pytest.raises(ValueError):
        distill.estimate_cost(small_corpus, teacher_model="claude-inconnu")


# ---------------------------------------------------------------------------
# Dry-run
# ---------------------------------------------------------------------------


def test_dry_run_mode_and_no_text(small_corpus):
    report = distill.dry_run(small_corpus)
    assert report["mode"] == "dry_run"
    assert "avertissement" in report
    assert "SIMULATION" in report["avertissement"]
    assert len(report["echantillon_labels_simules"]) <= distill._SAMPLE_SIZE
    for item in report["echantillon_labels_simules"]:
        assert set(item.keys()) == {"id", "label_simule"}
        assert item["label_simule"] in VISIBLE_MODELS
    dump = json.dumps(report)
    assert "prompt_text" not in dump


def test_dry_run_labels_are_deterministic(small_corpus):
    r1 = distill.dry_run(small_corpus)
    r2 = distill.dry_run(small_corpus)
    assert r1["distribution_labels_simules"] == r2["distribution_labels_simules"]
    assert r1["echantillon_labels_simules"] == r2["echantillon_labels_simules"]


def test_dry_run_note_cgu_present(small_corpus):
    """Minor (correction ronde 0) : compare au contenu RÉEL de `distill._NOTE_CGU`, pas
    seulement à sa présence — un test qui ne vérifie que `len() > 0` passerait même si
    le texte de la note dérivait silencieusement d'une future édition du module."""
    report = distill.dry_run(small_corpus)
    assert "note_cgu" in report
    assert report["note_cgu"] == distill._NOTE_CGU
    assert "CGU" in report["note_cgu"]


# ---------------------------------------------------------------------------
# Gates du chemin payant
# ---------------------------------------------------------------------------


def test_run_real_refuses_without_allow_flag(small_corpus, monkeypatch):
    monkeypatch.delenv("SOBRIO_ALLOW_PAID_CALLS", raising=False)
    with pytest.raises(RuntimeError, match="SOBRIO_ALLOW_PAID_CALLS"):
        distill.run_real(small_corpus)
    assert distill.get_stop_counter() == 0


def test_run_real_refuses_when_flag_not_exactly_one(small_corpus, monkeypatch):
    monkeypatch.setenv("SOBRIO_ALLOW_PAID_CALLS", "true")  # pas "1"
    with pytest.raises(RuntimeError, match="SOBRIO_ALLOW_PAID_CALLS"):
        distill.run_real(small_corpus)


def test_run_real_refuses_over_spend_cap(small_corpus, monkeypatch):
    monkeypatch.setenv("SOBRIO_ALLOW_PAID_CALLS", "1")
    monkeypatch.setenv("SOBRIO_MAX_SPEND_USD", "0.00001")
    with pytest.raises(RuntimeError, match="cap"):
        distill.run_real(small_corpus)
    assert distill.get_stop_counter() == 0


def test_run_real_stops_before_any_call_when_gates_pass(small_corpus, monkeypatch):
    monkeypatch.setenv("SOBRIO_ALLOW_PAID_CALLS", "1")
    monkeypatch.setenv("SOBRIO_MAX_SPEND_USD", "20")
    with pytest.raises(RuntimeError, match="décision fondateurs"):
        distill.run_real(small_corpus)
    assert distill.get_stop_counter() == 1
    # Un second appel incrémente à nouveau (compteur cumulatif de l'audit).
    with pytest.raises(RuntimeError, match="décision fondateurs"):
        distill.run_real(small_corpus)
    assert distill.get_stop_counter() == 2


def test_run_real_default_cap_applies_without_explicit_env(small_corpus, monkeypatch):
    monkeypatch.setenv("SOBRIO_ALLOW_PAID_CALLS", "1")
    monkeypatch.delenv("SOBRIO_MAX_SPEND_USD", raising=False)
    # Le petit corpus de test reste bien sous le cap par défaut (20$) : le
    # gate de coût passe, la fonction s'arrête au message founders-decision.
    with pytest.raises(RuntimeError, match="décision fondateurs"):
        distill.run_real(small_corpus)


# ---------------------------------------------------------------------------
# M5 (correction ronde 0) — cap de dépense FAIL-CLOSED : SOBRIO_MAX_SPEND_USD
# doit être un float FINI strictement positif (bool exclu). Avant cette
# correction, nan/inf rendaient `cout_estime_usd > cap` silencieusement
# toujours FAUX (bypass complet du gate, prouvé par exécution ci-dessous).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_cap", ["nan", "inf", "-inf", "-5", "abc", ""])
def test_parse_spend_cap_rejects_all_malformed_values(bad_cap):
    with pytest.raises(distill.SpendCapError):
        distill._parse_spend_cap(bad_cap)


@pytest.mark.parametrize("bad_cap", ["nan", "inf", "-inf", "-5", "abc", ""])
def test_run_real_fail_closed_on_malformed_spend_cap(small_corpus, monkeypatch, bad_cap):
    """Preuve par exécution (M5) : nan/inf/-5/abc/vide lèvent TOUS `SpendCapError`,
    AVANT toute estimation de coût — comparaison silencieusement favorable interdite."""
    monkeypatch.setenv("SOBRIO_ALLOW_PAID_CALLS", "1")
    monkeypatch.setenv("SOBRIO_MAX_SPEND_USD", bad_cap)
    with pytest.raises(distill.SpendCapError):
        distill.run_real(small_corpus)
    # AUCUN franchissement de gate compté : le refus a lieu AVANT le point d'arrêt.
    assert distill.get_stop_counter() == 0


def test_parse_spend_cap_accepts_finite_positive_values():
    assert distill._parse_spend_cap("20") == 20.0
    assert distill._parse_spend_cap("0.5") == 0.5


def test_parse_spend_cap_default_when_env_absent():
    assert distill._parse_spend_cap(None) == distill._DEFAULT_MAX_SPEND_USD


def test_parse_spend_cap_rejects_bool_like_zero_and_negative_zero():
    # `cap <= 0` : zéro et négatif exclus (un cap non-positif ne serait jamais
    # franchi, refus TOUJOURS silencieux — pas une protection réelle).
    with pytest.raises(distill.SpendCapError):
        distill._parse_spend_cap("0")
    with pytest.raises(distill.SpendCapError):
        distill._parse_spend_cap("-0.0001")


def test_main_real_flag_with_malformed_cap_exits_2_clean(small_corpus, monkeypatch, capsys):
    """CLI (M5) : cap malformé -> exit 2, message propre sur stderr, PAS de traceback."""
    monkeypatch.setenv("SOBRIO_ALLOW_PAID_CALLS", "1")
    monkeypatch.setenv("SOBRIO_MAX_SPEND_USD", "nan")
    code = distill.main(["--corpus", str(small_corpus), "--real"])
    assert code == 2
    captured = capsys.readouterr()
    assert "SOBRIO_MAX_SPEND_USD" in captured.err
    assert "Traceback" not in captured.err


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_main_dry_run_writes_report(small_corpus, tmp_path):
    out = tmp_path / "out.json"
    code = distill.main(["--corpus", str(small_corpus), "--out", str(out)])
    assert code == 0
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["mode"] == "dry_run"


def test_main_real_flag_clean_refusal_exit_2(small_corpus, monkeypatch, capsys):
    """Refus de gate LÉGITIME (flag absent) : message propre + exit 2, pas de
    traceback brut (minor qa ronde 1 — aligné sur le style de router/data/)."""
    monkeypatch.delenv("SOBRIO_ALLOW_PAID_CALLS", raising=False)
    code = distill.main(["--corpus", str(small_corpus), "--real"])
    assert code == 2
    err = capsys.readouterr().err
    assert "REFUS" in err and "dry-run" in err and "Traceback" not in err


def test_main_real_founders_stop_clean_exit_2(small_corpus, monkeypatch, capsys):
    """Gates franchis (flag + cap suffisant) : l'arrêt « décision fondateurs »
    est lui aussi un refus propre exit 2 — jamais d'appel réseau."""
    monkeypatch.setenv("SOBRIO_ALLOW_PAID_CALLS", "1")
    monkeypatch.setenv("SOBRIO_MAX_SPEND_USD", "100000")
    code = distill.main(["--corpus", str(small_corpus), "--real"])
    assert code == 2
    err = capsys.readouterr().err
    assert "fondateurs" in err and "Traceback" not in err


def test_parse_spend_cap_rejects_bool():
    """« bool exclu » (minor qa r1) : True passait comme 1.0 — désormais rejeté,
    l'affirmation du ledger/docstring est vraie (même précaution que SafeRouter)."""
    with pytest.raises(distill.SpendCapError):
        distill._parse_spend_cap(True)
    with pytest.raises(distill.SpendCapError):
        distill._parse_spend_cap(False)


# ---------------------------------------------------------------------------
# R5 : la garde réseau s'étend à `router/train/` (train_v05, promote — même
# invariant cost-guard, dépense 0,00 $ : aucun motif réseau dans le pipeline
# d'entraînement/promotion).
# ---------------------------------------------------------------------------

_TRAIN_DIR = Path(__file__).resolve().parents[1] / "train"


@pytest.mark.parametrize("module_path", sorted(_TRAIN_DIR.glob("*.py")), ids=lambda p: p.name)
def test_no_network_imports_in_router_train_modules(module_path):
    source = module_path.read_text(encoding="utf-8")
    match = _NETWORK_IMPORT_RE.search(source)
    assert match is None, (
        f"import réseau interdit détecté dans {module_path.name} : {match.group(0)!r}"
    )
    assert "urlopen" not in source
    assert "Anthropic(" not in source


def test_router_train_dir_couvert_par_la_garde():
    """Garde-fou du garde-fou : le dossier existe et contient bien les deux modules R5."""
    noms = {p.name for p in _TRAIN_DIR.glob("*.py")}
    assert {"train_v05.py", "promote.py"} <= noms
