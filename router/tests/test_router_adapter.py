"""Tests de l'adaptateur `features_to_signals` : mapping fidèle, conversation neutre."""

from __future__ import annotations

from dataclasses import dataclass

from sobrio_router import ConversationSignals
from sobrio_router.adapter import features_to_signals


@dataclass
class _FakeFeatures:
    """Double léger de `app.schemas.Features` — le routeur n'importe pas pydantic."""

    char_len: int
    token_est: int
    lang: str
    has_code: bool
    has_attachment_hint: bool
    keyword_flags: list[str]


def test_maps_prompt_fields_faithfully():
    features = _FakeFeatures(
        char_len=321,
        token_est=77,
        lang="fr",
        has_code=True,
        has_attachment_hint=True,
        keyword_flags=["code", "analyse"],
    )
    signals = features_to_signals(features)
    assert signals.prompt.char_len == 321
    assert signals.prompt.token_est == 77
    assert signals.prompt.lang == "fr"
    assert signals.prompt.has_code is True
    assert signals.prompt.keyword_flags == ("code", "analyse")


def test_keyword_flags_become_a_tuple():
    features = _FakeFeatures(
        char_len=1, token_est=1, lang="en", has_code=False, has_attachment_hint=False,
        keyword_flags=[],
    )
    signals = features_to_signals(features)
    assert signals.prompt.keyword_flags == ()
    assert isinstance(signals.prompt.keyword_flags, tuple)


def test_has_math_defaults_to_false():
    """`has_math` n'existe pas dans `features` v1.0 (nouveau signal RFC-0001)."""
    features = _FakeFeatures(
        char_len=1, token_est=1, lang="fr", has_code=False, has_attachment_hint=False,
        keyword_flags=[],
    )
    signals = features_to_signals(features)
    assert signals.prompt.has_math is False


def test_has_attachment_hint_not_interpreted():
    """v0 : `has_attachment_hint` n'influence ni prompt ni conversation (TODO RFC)."""
    with_hint = features_to_signals(
        _FakeFeatures(
            char_len=1, token_est=1, lang="fr", has_code=False, has_attachment_hint=True,
            keyword_flags=[],
        )
    )
    without_hint = features_to_signals(
        _FakeFeatures(
            char_len=1, token_est=1, lang="fr", has_code=False, has_attachment_hint=False,
            keyword_flags=[],
        )
    )
    assert with_hint == without_hint


def test_conversation_is_fully_neutral():
    features = _FakeFeatures(
        char_len=999, token_est=999, lang="other", has_code=True, has_attachment_hint=True,
        keyword_flags=["contrat"],
    )
    signals = features_to_signals(features)
    assert signals.conversation == ConversationSignals()
    assert signals.conversation.msg_count == 0
    assert signals.conversation.context_token_est == 0
    assert signals.conversation.seen_code is False
    assert signals.conversation.seen_math is False
    assert signals.conversation.seen_reasoning is False
    assert signals.conversation.current_model is None
    assert signals.conversation.recos_shown == 0
    assert signals.conversation.recos_followed == 0
    assert signals.conversation.derogations_up == 0
