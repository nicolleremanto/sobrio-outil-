"""Tests du vecteur de features (`sobrio_router/features.py`, chantier R5 §1).

Couvre : encodage EXACT (liste littérale), constantes FIGÉES (couplage au
vocabulaire du corpus), le feature_spec INTÉGRAL pinné en littéral
([QA-R5-m1], transfert de clôture R5), neutralité totale hors vocabulaire
(jamais d'exception), et l'invariant §5.1 — `prompt_text`
inconditionnellement ignoré.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data"))

import generate_corpus  # noqa: E402
from conftest_helpers import make_signals  # noqa: E402

from sobrio_router import ConversationSignals, PromptSignals, Signals  # noqa: E402
from sobrio_router.features import (  # noqa: E402
    CURRENT_MODEL_RANK,
    FEATURE_NAMES,
    FLAG_VOCAB,
    LANGS,
    expected_feature_spec,
    signals_to_vector,
)


def test_vecteur_exact():
    """Signals construit à la main -> liste littérale attendue (ordre §1 FIGÉ)."""
    signals = Signals(
        prompt=PromptSignals(
            char_len=1234,
            token_est=300,
            lang="en",
            has_code=True,
            has_math=False,
            keyword_flags=("code", "analyse"),
        ),
        conversation=ConversationSignals(
            msg_count=7,
            context_token_est=800,
            seen_code=True,
            seen_math=False,
            seen_reasoning=True,
            current_model="claude-opus-4-8",
            recos_shown=3,
            recos_followed=2,
            derogations_up=1,
        ),
    )
    assert signals_to_vector(signals) == [
        1234.0,  # char_len
        300.0,  # token_est
        1.0,  # has_code
        0.0,  # has_math
        0.0,  # lang_fr
        1.0,  # lang_en
        0.0,  # lang_other
        1.0,  # flag_analyse
        1.0,  # flag_code
        0.0,  # flag_contrat
        0.0,  # flag_demonstration
        0.0,  # flag_resume
        0.0,  # flag_traduction
        7.0,  # msg_count
        800.0,  # context_token_est
        1.0,  # seen_code
        0.0,  # seen_math
        1.0,  # seen_reasoning
        3.0,  # current_model_rank (opus)
        3.0,  # recos_shown
        2.0,  # recos_followed
        1.0,  # derogations_up
    ]


def test_feature_names_figes():
    """`FEATURE_NAMES` == tuple littéral (22) ; `FLAG_VOCAB` couplé au corpus."""
    assert FEATURE_NAMES == (
        "char_len",
        "token_est",
        "has_code",
        "has_math",
        "lang_fr",
        "lang_en",
        "lang_other",
        "flag_analyse",
        "flag_code",
        "flag_contrat",
        "flag_demonstration",
        "flag_resume",
        "flag_traduction",
        "msg_count",
        "context_token_est",
        "seen_code",
        "seen_math",
        "seen_reasoning",
        "current_model_rank",
        "recos_shown",
        "recos_followed",
        "derogations_up",
    )
    assert len(FEATURE_NAMES) == 22
    assert LANGS == ("fr", "en", "other")
    # Garde de couplage : le vocabulaire de flags est EXACTEMENT celui du
    # corpus (_ALLOWED_FLAGS de generate_corpus.py), trié alphabétiquement.
    assert FLAG_VOCAB == tuple(sorted(generate_corpus._ALLOWED_FLAGS))


def test_feature_spec_integral_pinne():
    """[QA-R5-m1] Le feature_spec ml_v05 INTÉGRAL, pinné en littéral dur.

    Rôle kill-de-mutant : le constructeur unique `expected_feature_spec()`
    (lot ronde 5) a supprimé la duplication croisée train/garde-de-chargement
    qui tuait ses mutants en clone frais — un mutant interne (version bumpée,
    langue retirée, rang altéré...) rend train et garde AUTO-COHÉRENTS, et
    seuls des tests dépendant d'artefacts locaux (SKIP en clone frais, donc
    en CI) le détectaient. Ce littéral complet — stdlib, TOUJOURS exécuté —
    restaure le kill indépendamment des artefacts. Copié depuis la sortie
    RÉELLE du constructeur, vérifiée champ à champ contre `features.py`
    (FEATURE_NAMES, LANGS, FLAG_VOCAB, CURRENT_MODEL_RANK avec la convention
    clé None -> "null", FEATURE_SPEC_VERSION). Un bump volontaire du spec
    (R6) ÉDITE ce littéral en même temps que le constructeur — c'est le prix,
    voulu, du pin.
    """
    assert expected_feature_spec() == {
        "names": [
            "char_len",
            "token_est",
            "has_code",
            "has_math",
            "lang_fr",
            "lang_en",
            "lang_other",
            "flag_analyse",
            "flag_code",
            "flag_contrat",
            "flag_demonstration",
            "flag_resume",
            "flag_traduction",
            "msg_count",
            "context_token_est",
            "seen_code",
            "seen_math",
            "seen_reasoning",
            "current_model_rank",
            "recos_shown",
            "recos_followed",
            "derogations_up",
        ],
        "langs": ["fr", "en", "other"],
        "flag_vocab": [
            "analyse",
            "code",
            "contrat",
            "demonstration",
            "resume",
            "traduction",
        ],
        "current_model_rank": {
            "null": 0.0,
            "claude-haiku-4-5": 1.0,
            "claude-sonnet-5": 2.0,
            "claude-opus-4-8": 3.0,
            "claude-fable-5": 4.0,
        },
        "version": "1",
    }


def test_valeurs_hors_vocabulaire_neutres():
    """Hors vocabulaire : neutralité totale, JAMAIS d'exception."""
    # lang inconnue -> one-hot entièrement nul.
    vec = signals_to_vector(make_signals(lang="de"))
    assert vec[4:7] == [0.0, 0.0, 0.0]
    # flag inconnu -> ignoré silencieusement (multi-hot nul).
    vec = signals_to_vector(make_signals(keyword_flags=("hors-vocab", "inconnu")))
    assert vec[7:13] == [0.0] * 6
    # current_model inconnu -> 0.0 ; fable (observé, jamais prédit) -> 4.0.
    assert signals_to_vector(make_signals(current_model="gpt-9-leaked"))[18] == 0.0
    assert signals_to_vector(make_signals(current_model="claude-fable-5"))[18] == 4.0
    assert signals_to_vector(make_signals(current_model=None))[18] == 0.0
    assert CURRENT_MODEL_RANK[None] == 0.0


def test_prompt_text_ignore():
    """Invariant §5.1 : le vecteur est IDENTIQUE avec et sans `prompt_text`."""
    sans = make_signals()
    avec = Signals(
        prompt=PromptSignals(
            char_len=sans.prompt.char_len,
            token_est=sans.prompt.token_est,
            lang=sans.prompt.lang,
            has_code=sans.prompt.has_code,
            has_math=sans.prompt.has_math,
            keyword_flags=sans.prompt.keyword_flags,
            prompt_text="contenu confidentiel qui ne doit JAMAIS influencer le vecteur",
        ),
        conversation=sans.conversation,
    )
    assert signals_to_vector(avec) == signals_to_vector(sans)
