"""Tests du pipeline de distillation dry-run (`router/data/distill.py`, chantier R4).

Convention d'import : `sys.path.insert` de `router/data/` (module autonome,
même esprit que `router/eval/loader.py`).
"""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data"))

import distill  # noqa: E402
from generate_corpus import generate  # noqa: E402

from sobrio_router import VISIBLE_MODELS  # noqa: E402


@pytest.fixture
def small_corpus(tmp_path: Path) -> Path:
    rows, _ = generate(50, seed=4242, bruit_rate=0.03)
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
# Aucun motif réseau dans le module (invariant cost-guard)
# ---------------------------------------------------------------------------


def test_no_network_imports_in_distill_module():
    source = Path(distill.__file__).read_text(encoding="utf-8")
    forbidden = ("anthropic", "httpx", "requests", "urllib.request", "socket", "http.client")
    for name in forbidden:
        assert f"import {name}" not in source, f"import réseau interdit trouvé : {name}"
    assert "urlopen" not in source
    assert "Anthropic(" not in source


def test_no_network_imports_in_public_datasets_module():
    import public_datasets

    source = Path(public_datasets.__file__).read_text(encoding="utf-8")
    forbidden = ("anthropic", "httpx", "requests", "urllib.request", "socket", "http.client")
    for name in forbidden:
        assert f"import {name}" not in source, f"import réseau interdit trouvé : {name}"


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

    rows, _ = generate(100, seed=4242, bruit_rate=0.03)
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
    report = distill.dry_run(small_corpus)
    assert "note_cgu" in report and len(report["note_cgu"]) > 0


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
# CLI
# ---------------------------------------------------------------------------


def test_main_dry_run_writes_report(small_corpus, tmp_path):
    out = tmp_path / "out.json"
    code = distill.main(["--corpus", str(small_corpus), "--out", str(out)])
    assert code == 0
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["mode"] == "dry_run"


def test_main_real_flag_raises(small_corpus, monkeypatch):
    monkeypatch.delenv("SOBRIO_ALLOW_PAID_CALLS", raising=False)
    with pytest.raises(RuntimeError):
        distill.main(["--corpus", str(small_corpus), "--real"])
