"""Tests des adaptateurs de datasets publics (`router/data/public_datasets.py`, chantier R4).

Les fonctions de TÉLÉCHARGEMENT ne sont JAMAIS réellement exercées ici
(flag éteint par défaut) ; les fonctions de CONVERSION sont testées via des
fixtures locales qui SIMULENT le format des sources
(`router/tests/fixtures/`), jamais de vraies données téléchargées.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data"))

import public_datasets  # noqa: E402

from sobrio_router import ConversationSignals, PromptSignals  # noqa: E402

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


# ---------------------------------------------------------------------------
# Téléchargement : flag éteint -> refus
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "func",
    [
        public_datasets.download_lmsys_chat_1m,
        public_datasets.download_chatbot_arena,
        public_datasets.download_routellm_judge_data,
    ],
)
def test_download_functions_refuse_without_flag(func, monkeypatch, tmp_path):
    monkeypatch.delenv("SOBRIO_ALLOW_DATASET_DOWNLOAD", raising=False)
    with pytest.raises(RuntimeError, match="SOBRIO_ALLOW_DATASET_DOWNLOAD"):
        func(str(tmp_path))


@pytest.mark.parametrize(
    "func",
    [
        public_datasets.download_lmsys_chat_1m,
        public_datasets.download_chatbot_arena,
        public_datasets.download_routellm_judge_data,
    ],
)
def test_download_functions_refuse_wrong_flag_value(func, monkeypatch, tmp_path):
    monkeypatch.setenv("SOBRIO_ALLOW_DATASET_DOWNLOAD", "yes")  # pas "1"
    with pytest.raises(RuntimeError, match="SOBRIO_ALLOW_DATASET_DOWNLOAD"):
        func(str(tmp_path))


@pytest.mark.parametrize(
    "func",
    [
        public_datasets.download_lmsys_chat_1m,
        public_datasets.download_chatbot_arena,
        public_datasets.download_routellm_judge_data,
    ],
)
def test_download_functions_even_with_flag_never_perform_network_io(func, monkeypatch, tmp_path):
    """Flag activé : la fonction lève quand même — AUCUN chemin réseau n'existe (cf. module)."""
    monkeypatch.setenv("SOBRIO_ALLOW_DATASET_DOWNLOAD", "1")
    with pytest.raises(NotImplementedError):
        func(str(tmp_path))


# ---------------------------------------------------------------------------
# Conversion (fixtures locales, signaux seulement)
# ---------------------------------------------------------------------------


def test_convert_lmsys_record_returns_signals_only():
    records = _load_jsonl(_FIXTURES_DIR / "lmsys_sample.jsonl")
    for record in records:
        signals = public_datasets.convert_lmsys_record(record)
        assert set(signals.keys()) == {"prompt", "conversation"}
        prompt = PromptSignals(**signals["prompt"])
        conversation = ConversationSignals(**signals["conversation"])
        assert prompt.prompt_text is None
        assert conversation.msg_count == len(record["conversation"])
        dump = json.dumps(signals)
        assert "prompt_text" not in dump
        # Aucun texte source ne doit fuiter dans les signaux convertis.
        for turn in record["conversation"]:
            assert turn["content"] not in dump


def test_convert_chatbot_arena_record_returns_signals_only():
    records = _load_jsonl(_FIXTURES_DIR / "chatbot_arena_sample.jsonl")
    for record in records:
        signals = public_datasets.convert_chatbot_arena_record(record)
        assert set(signals.keys()) == {"prompt", "conversation"}
        PromptSignals(**signals["prompt"])
        ConversationSignals(**signals["conversation"])
        dump = json.dumps(signals)
        assert record["prompt"] not in dump


def test_convert_detects_code_hint():
    record = {"conversation": [{"role": "user", "content": "def add(a, b):\n    return a + b"}]}
    signals = public_datasets.convert_lmsys_record(record)
    assert signals["prompt"]["has_code"] is True


def test_convert_detects_math_hint():
    """Minor (correction ronde 0) : `has_math` n'avait aucun test dédié, symétrique
    de `test_convert_detects_code_hint` ci-dessus — matériau minimal, pas un prompt."""
    record = {"conversation": [{"role": "user", "content": "2 + 2 = 4"}]}
    signals = public_datasets.convert_lmsys_record(record)
    assert signals["prompt"]["has_math"] is True


def test_convert_lang_heuristic_fr_vs_en():
    # Soupe de mots-vides : exerce la détection de langue sans qu'aucune
    # chaîne ne ressemble à un prompt (règle n°1, appliquée même au matériau
    # de test inventé — jurisprudence privacy R2-r0).
    fr_record = {"prompt": "le la les et des dans pour avec sur une du au ce qui que"}
    en_record = {"prompt": "the and of to in for with on at is are this that from by"}
    fr_signals = public_datasets.convert_chatbot_arena_record(fr_record)
    en_signals = public_datasets.convert_chatbot_arena_record(en_record)
    assert fr_signals["prompt"]["lang"] == "fr"
    assert en_signals["prompt"]["lang"] == "en"


def test_convert_empty_conversation_is_safe():
    signals = public_datasets.convert_lmsys_record({"conversation": []})
    PromptSignals(**signals["prompt"])
    ConversationSignals(**signals["conversation"])
    assert signals["conversation"]["msg_count"] == 0
