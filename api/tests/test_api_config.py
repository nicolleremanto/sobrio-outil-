"""Tests de /v1/extension/config : conformité, défauts sûrs, fusion policy_json."""

from __future__ import annotations

import sqlalchemy as sa
from helpers_api import AUTH_HEADERS

_CATALOG_IDS = ["claude-haiku-4-5", "claude-sonnet-5", "claude-opus-4-8"]


def test_config_conforms_and_send_prompt_text_false_by_default(client):
    response = client.get("/v1/extension/config", params={"org": "demo"}, headers=AUTH_HEADERS)
    assert response.status_code == 200
    payload = response.json()
    # Forme exacte du contrat ExtensionConfig.
    assert set(payload.keys()) == {
        "enabled",
        "mode",
        "models_visible",
        "send_prompt_text",
        "messages",
        "min_extension_version",
    }
    assert payload["enabled"] is True
    assert payload["mode"] == "equilibre"
    assert payload["models_visible"] == _CATALOG_IDS
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
