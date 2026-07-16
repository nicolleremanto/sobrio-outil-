"""Constantes et fabriques partagées par les tests du Lot B.

Module au nom unique (préfixe du lot) pour éviter toute collision d'import
quand plusieurs suites de tests tournent depuis la racine.
"""

from __future__ import annotations

import hashlib
import os

DEMO_TOKEN = os.environ.get("DEMO_ORG_TOKEN", "demo-token-not-a-secret")
DEMO_TOKEN_HASH = hashlib.sha256(DEMO_TOKEN.encode()).hexdigest()
AUTH_HEADERS = {"Authorization": f"Bearer {DEMO_TOKEN}"}


def make_features(**overrides) -> dict:
    """Features valides par défaut, surchargeables par test."""
    features = {
        "char_len": 120,
        "token_est": 40,
        "lang": "fr",
        "has_code": False,
        "has_attachment_hint": False,
        "keyword_flags": [],
    }
    features.update(overrides)
    return features


def make_recommend_body(**feature_overrides) -> dict:
    """Corps de requête /v1/recommend valide par défaut."""
    return {
        "org_id": "demo",
        "surface": "claude_web",
        "features": make_features(**feature_overrides),
    }
