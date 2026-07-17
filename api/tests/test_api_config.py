"""Tests de /v1/extension/config : conformité, défauts sûrs, fusion policy_json."""

from __future__ import annotations

import sqlalchemy as sa
from helpers_api import AUTH_HEADERS

_CATALOG_IDS = ["claude-haiku-4-5", "claude-sonnet-5", "claude-opus-4-8"]


def test_config_conforms_and_send_prompt_text_false_by_default(client):
    response = client.get("/v1/extension/config", params={"org": "demo"}, headers=AUTH_HEADERS)
    assert response.status_code == 200
    payload = response.json()
    # Forme exacte du contrat ExtensionConfig (RFC-0003 : + assist_mode + seuil).
    assert set(payload.keys()) == {
        "enabled",
        "mode",
        "models_visible",
        "assist_mode",
        "auto_confidence_threshold",
        "send_prompt_text",
        "messages",
        "min_extension_version",
    }
    assert payload["enabled"] is True
    assert payload["mode"] == "equilibre"
    assert payload["models_visible"] == _CATALOG_IDS
    # RFC-0003 : défauts sûrs (compat ascendante) — one_click, seuil 0,75.
    assert payload["assist_mode"] == "one_click"
    assert payload["auto_confidence_threshold"] == 0.75
    # false PAR CONTRAT : l'envoi du texte est un opt-in explicite de l'org.
    assert payload["send_prompt_text"] is False
    assert "fr" in payload["messages"]
    assert payload["messages"]["fr"]  # au moins quelques libellés
    assert payload["min_extension_version"] == "0.1.0"


def test_config_other_org_is_404(client):
    """404 si l'org demandée n'est pas celle du token (pas d'énumération)."""
    response = client.get("/v1/extension/config", params={"org": "autre-org"}, headers=AUTH_HEADERS)
    assert response.status_code == 404


def test_config_without_token_is_401(client):
    response = client.get("/v1/extension/config", params={"org": "demo"})
    assert response.status_code == 401


def test_config_merges_policy_json(client, test_engine):
    """policy_json de l'org prime sur les défauts sûrs (fusion superficielle)."""
    with test_engine.begin() as conn:
        conn.execute(
            sa.text(
                "UPDATE orgs SET policy_json = "
                """'{"mode": "eco", "cle_hors_contrat": true}'::jsonb """
                "WHERE org_id = 'demo'"
            )
        )
    try:
        response = client.get("/v1/extension/config", params={"org": "demo"}, headers=AUTH_HEADERS)
        assert response.status_code == 200
        payload = response.json()
        assert payload["mode"] == "eco"  # surchargé par la politique
        assert payload["enabled"] is True  # défaut conservé
        assert "cle_hors_contrat" not in payload  # clé hors contrat filtrée
    finally:
        with test_engine.begin() as conn:
            conn.execute(sa.text("UPDATE orgs SET policy_json = '{}'::jsonb WHERE org_id = 'demo'"))


def test_config_invalid_policy_falls_back_not_500(client, test_engine):
    """RFC-0003 : un policy_json mal formé (seuil hors 0..1) → défauts sûrs, pas 500."""
    with test_engine.begin() as conn:
        conn.execute(
            sa.text(
                "UPDATE orgs SET policy_json = "
                """'{"auto_confidence_threshold": 1.5}'::jsonb """
                "WHERE org_id = 'demo'"
            )
        )
    try:
        response = client.get("/v1/extension/config", params={"org": "demo"}, headers=AUTH_HEADERS)
        assert response.status_code == 200  # jamais 500 (règle 3)
        payload = response.json()
        assert payload["auto_confidence_threshold"] == 0.75  # repli sur le défaut sûr
        assert payload["assist_mode"] == "one_click"
    finally:
        with test_engine.begin() as conn:
            conn.execute(sa.text("UPDATE orgs SET policy_json = '{}'::jsonb WHERE org_id = 'demo'"))


def test_config_assist_mode_guide_kill_switch(client, test_engine):
    """RFC-0003 : l'org peut forcer assist_mode=guide (kill-switch prudence CGU)."""
    with test_engine.begin() as conn:
        conn.execute(
            sa.text(
                "UPDATE orgs SET policy_json = "
                """'{"assist_mode": "guide", "auto_confidence_threshold": 0.9}'::jsonb """
                "WHERE org_id = 'demo'"
            )
        )
    try:
        response = client.get("/v1/extension/config", params={"org": "demo"}, headers=AUTH_HEADERS)
        assert response.status_code == 200
        payload = response.json()
        assert payload["assist_mode"] == "guide"  # kill-switch appliqué
        assert payload["auto_confidence_threshold"] == 0.9
    finally:
        with test_engine.begin() as conn:
            conn.execute(sa.text("UPDATE orgs SET policy_json = '{}'::jsonb WHERE org_id = 'demo'"))
