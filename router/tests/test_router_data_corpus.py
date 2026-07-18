"""Tests du générateur de corpus + rapport data-quality (chantier R4).

Convention d'import : `router/data/` n'est pas un paquet installé (même
esprit que `router/eval/`, cf. `loader.py`) — on ajoute son chemin à
`sys.path` explicitement, ainsi que `router/eval/` pour comparer contre le
golden set FIGÉ (anti-fuite par signature).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))

from generate_corpus import generate  # noqa: E402
from loader import load_golden  # noqa: E402
from quality_report import analyze  # noqa: E402

from sobrio_router import VISIBLE_MODELS, ConversationSignals, PromptSignals  # noqa: E402


def _corpus_hash(rows: list[dict]) -> str:
    payload = "".join(json.dumps(r, sort_keys=True) for r in rows)
    return hashlib.sha256(payload.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Déterminisme
# ---------------------------------------------------------------------------


def test_generate_is_deterministic_same_seed():
    """Deux runs, même (n, seed, bruit) -> sha256 identique (§5.6)."""
    rows1, stats1 = generate(200, seed=4242, bruit_rate=0.03)
    rows2, stats2 = generate(200, seed=4242, bruit_rate=0.03)
    assert _corpus_hash(rows1) == _corpus_hash(rows2)
    assert stats1 == stats2


def test_generate_differs_with_different_seed():
    """Contrôle négatif : un seed différent change le corpus (le test positif ne triche pas)."""
    rows1, _ = generate(200, seed=4242, bruit_rate=0.03)
    rows2, _ = generate(200, seed=777, bruit_rate=0.03)
    assert _corpus_hash(rows1) != _corpus_hash(rows2)


def test_default_seed_differs_from_golden_seed():
    """Le seed par défaut (4242) est bien différent du seed du golden (2026) — cf. docstring."""
    import generate_corpus

    assert generate_corpus.DEFAULT_SEED == 4242
    assert generate_corpus.DEFAULT_SEED != 2026


# ---------------------------------------------------------------------------
# Schéma
# ---------------------------------------------------------------------------


def test_rows_load_as_signals_without_error():
    """Chaque ligne échantillonnée se charge en `Signals` via `sobrio_router.types`."""
    rows, _ = generate(300, seed=4242, bruit_rate=0.03)
    for row in rows:
        prompt = PromptSignals(**row["signals"]["prompt"])
        conversation = ConversationSignals(**row["signals"]["conversation"])
        assert prompt.prompt_text is None
        assert isinstance(conversation.msg_count, int)


def test_labels_are_visible_models():
    rows, _ = generate(300, seed=4242, bruit_rate=0.03)
    for row in rows:
        assert row["label"] in VISIBLE_MODELS


def test_ids_are_corp_prefixed_and_unique():
    rows, _ = generate(300, seed=4242, bruit_rate=0.03)
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids))
    for row_id in ids:
        assert row_id.startswith("corp-")
        assert not row_id.startswith("gold-")


def test_no_prompt_text_anywhere():
    rows, _ = generate(300, seed=4242, bruit_rate=0.03)
    dump = json.dumps(rows)
    assert "prompt_text" not in dump


def test_row_shape_is_exact():
    """Chaque ligne = exactement {id, category, label, signals}, rien de plus."""
    rows, _ = generate(50, seed=4242, bruit_rate=0.03)
    for row in rows:
        assert set(row.keys()) == {"id", "category", "label", "signals"}
        assert set(row["signals"].keys()) == {"prompt", "conversation"}


def test_recos_followed_never_exceeds_recos_shown():
    rows, _ = generate(2000, seed=4242, bruit_rate=0.03)
    for row in rows:
        c = row["signals"]["conversation"]
        assert c["recos_followed"] <= c["recos_shown"]


# ---------------------------------------------------------------------------
# Anti-fuite
# ---------------------------------------------------------------------------


def _canonical_signature(prompt: dict, conversation: dict) -> tuple:
    return (
        prompt["char_len"],
        prompt["token_est"],
        prompt["lang"],
        prompt["has_code"],
        prompt["has_math"],
        tuple(sorted(prompt["keyword_flags"])),
        conversation["msg_count"],
        conversation["context_token_est"],
        conversation["seen_code"],
        conversation["seen_math"],
        conversation["seen_reasoning"],
        conversation["current_model"],
        conversation["recos_shown"],
        conversation["recos_followed"],
        conversation["derogations_up"],
    )


def test_no_gold_ids_in_corpus():
    """Aucun id `gold-*` n'apparaît dans le corpus généré (anti-fuite d'ids)."""
    rows, _ = generate(2000, seed=4242, bruit_rate=0.03)
    for row in rows:
        assert not row["id"].startswith("gold-")
    assert "gold-" not in json.dumps(rows)


def test_no_exact_signal_signature_overlap_with_golden():
    """AUCUNE ligne du corpus n'a la signature signaux EXACTE d'une entrée du golden.

    Compare des signatures CANONIQUES (mêmes champs, même ordre) construites
    indépendamment depuis les deux sources — le golden via `loader.load_golden()`
    (dataclasses `Signals`), le corpus via ses dicts JSON bruts.
    """
    golden_entries = load_golden()
    golden_signatures = {
        _canonical_signature(
            {
                "char_len": e.signals.prompt.char_len,
                "token_est": e.signals.prompt.token_est,
                "lang": e.signals.prompt.lang,
                "has_code": e.signals.prompt.has_code,
                "has_math": e.signals.prompt.has_math,
                "keyword_flags": list(e.signals.prompt.keyword_flags),
            },
            {
                "msg_count": e.signals.conversation.msg_count,
                "context_token_est": e.signals.conversation.context_token_est,
                "seen_code": e.signals.conversation.seen_code,
                "seen_math": e.signals.conversation.seen_math,
                "seen_reasoning": e.signals.conversation.seen_reasoning,
                "current_model": e.signals.conversation.current_model,
                "recos_shown": e.signals.conversation.recos_shown,
                "recos_followed": e.signals.conversation.recos_followed,
                "derogations_up": e.signals.conversation.derogations_up,
            },
        )
        for e in golden_entries
    }
    rows, _ = generate(5000, seed=4242, bruit_rate=0.03)
    corpus_signatures = {
        _canonical_signature(r["signals"]["prompt"], r["signals"]["conversation"]) for r in rows
    }
    overlap = golden_signatures & corpus_signatures
    assert not overlap, f"signatures partagées golden/corpus : {overlap}"


# ---------------------------------------------------------------------------
# quality_report
# ---------------------------------------------------------------------------


def test_quality_report_healthy_corpus_is_ok():
    rows, _ = generate(1000, seed=4242, bruit_rate=0.03)
    report = analyze(rows)
    assert report["verdict"]["ok"] is True, report["verdict"]["alertes"]


def test_quality_report_flags_duplicates_and_imbalance():
    """Corpus FABRIQUÉ (doublons massifs + déséquilibre extrême) -> alertes."""
    dup_signals = {
        "prompt": {
            "char_len": 100,
            "token_est": 40,
            "lang": "fr",
            "has_code": False,
            "has_math": False,
            "keyword_flags": [],
        },
        "conversation": {
            "msg_count": 0,
            "context_token_est": 0,
            "seen_code": False,
            "seen_math": False,
            "seen_reasoning": False,
            "current_model": None,
            "recos_shown": 0,
            "recos_followed": 0,
            "derogations_up": 0,
        },
    }
    rows = [
        {
            "id": f"corp-{i:06d}",
            "category": "redaction_simple",
            "label": "claude-haiku-4-5",
            "signals": dup_signals,
        }
        for i in range(1, 96)
    ] + [
        {
            "id": f"corp-{i:06d}",
            "category": "redaction_simple",
            "label": "claude-opus-4-8",
            "signals": {**dup_signals, "prompt": {**dup_signals["prompt"], "char_len": 100 + i}},
        }
        for i in range(96, 101)
    ]
    report = analyze(rows)
    assert report["verdict"]["ok"] is False
    assert report["taux_doublons_signature"] > 0.05
    assert any("doublons" in a for a in report["verdict"]["alertes"])
    assert any("cellules" in a or "déséquilibre" in a for a in report["verdict"]["alertes"])


def test_quality_report_empty_corpus():
    report = analyze([])
    assert report["verdict"]["ok"] is False
