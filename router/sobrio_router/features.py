"""Vecteur de features de l'étage 1 (ml_v05) — stdlib SEULE, spec R5 §1.

`signals_to_vector` transforme un `Signals` (RFC-0001) en vecteur de 22
flottants, dans l'ORDRE FIGÉ de `FEATURE_NAMES`. Invariant §5.1 : AUCUNE
feature texte — `prompt_text` est inconditionnellement ignoré (le champ n'est
jamais lu), seules des MESURES et un VOCABULAIRE FERMÉ entrent dans le
vecteur. La fonction est PURE et TOTALE : elle ne lève JAMAIS sur des valeurs
hors vocabulaire (lang inconnue -> one-hot nul ; flag inconnu -> ignoré ;
current_model inconnu -> 0.0).

Ce module est importable SANS lightgbm/numpy (aucun import tiers) : le
paquet `sobrio_router` reste sans dépendance (contrat R1, import paresseux
de lightgbm confiné à `ml.py` §7.1).

Réconciliation des écarts consignés en clôture R4 (spec R5 §1) :
- `demonstration` (hors enum OpenAPI v1.0) : CONSERVÉ dans `FLAG_VOCAB` —
  l'adaptateur serveur ne le produit jamais aujourd'hui (feature à 0 en
  prod), il devient vivant avec la RFC-0001 et vit déjà côté mock extension.
- `has_math` : feature entraînée mais dormante côté serveur (l'adaptateur
  pose `has_math=False`) jusqu'à la RFC-0001. `has_attachment_hint` n'existe
  pas dans `Signals` : l'information arrive déjà encodée en `flag_analyse`
  (mapping `adapter.py`).
"""

from __future__ import annotations

from .types import Signals

# Ordre de l'enum OpenAPI (contracts/openapi.yaml, champ lang).
LANGS: tuple[str, ...] = ("fr", "en", "other")

# = _ALLOWED_FLAGS du corpus (router/data/generate_corpus.py), TRIÉ
# alphabétiquement — vocabulaire CLOS, superset de l'enum OpenAPI v1.0
# (couplage vérifié par test_router_features.test_feature_names_figes).
FLAG_VOCAB: tuple[str, ...] = (
    "analyse",
    "code",
    "contrat",
    "demonstration",
    "resume",
    "traduction",
)

# Rang de COÛT du modèle courant du fil (ordinal, pas one-hot : le rang de
# coût est réellement ordonné — sémantique produit « le fil tourne déjà sur
# un palier N »). `claude-fable-5` est OBSERVABLE en conversation (jamais
# prédit, RFC-0002) ; chaîne inconnue -> 0.0 (comme un fil vierge).
CURRENT_MODEL_RANK: dict[str | None, float] = {
    None: 0.0,
    "claude-haiku-4-5": 1.0,
    "claude-sonnet-5": 2.0,
    "claude-opus-4-8": 3.0,
    "claude-fable-5": 4.0,
}

# 22 features, ORDRE FIGÉ — toute dérive artefact/code est refusée au
# chargement (ml.py §7.1 : booster.feature_name() == list(FEATURE_NAMES)).
FEATURE_NAMES: tuple[str, ...] = (
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


def signals_to_vector(signals: Signals) -> list[float]:
    """Encode `signals` en vecteur de 22 flottants (ordre `FEATURE_NAMES`, §1).

    - char_len/token_est : bruts (les arbres n'exigent aucune normalisation ;
      la quasi-colinéarité char_len/token_est est sans danger pour un GBDT) ;
    - lang : one-hot sur `LANGS` (aucun ordre entre fr/en/other) — hors enum
      => trois zéros, JAMAIS d'exception ;
    - keyword_flags : multi-hot sur `FLAG_VOCAB` — flag hors vocabulaire
      IGNORÉ silencieusement ;
    - current_model : ordinal de coût via `CURRENT_MODEL_RANK` ;
    - `prompt_text` : jamais lu (invariant §5.1, test dédié).
    """
    prompt = signals.prompt
    conversation = signals.conversation
    flags = set(prompt.keyword_flags)
    return [
        float(prompt.char_len),
        float(prompt.token_est),
        1.0 if prompt.has_code else 0.0,
        1.0 if prompt.has_math else 0.0,
        *(1.0 if prompt.lang == lang else 0.0 for lang in LANGS),
        *(1.0 if flag in flags else 0.0 for flag in FLAG_VOCAB),
        float(conversation.msg_count),
        float(conversation.context_token_est),
        1.0 if conversation.seen_code else 0.0,
        1.0 if conversation.seen_math else 0.0,
        1.0 if conversation.seen_reasoning else 0.0,
        CURRENT_MODEL_RANK.get(conversation.current_model, 0.0),
        float(conversation.recos_shown),
        float(conversation.recos_followed),
        float(conversation.derogations_up),
    ]
