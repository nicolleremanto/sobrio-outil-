"""Tests de /v1/telemetry/reco_event : happy path, 404, schéma strict (anti-fuite)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from helpers_api import AUTH_HEADERS, make_recommend_body


def _create_reco(client) -> dict:
    response = client.post("/v1/recommend", json=make_recommend_body(), headers=AUTH_HEADERS)
    assert response.status_code == 200
    return response.json()


def _telemetry_body(reco_id: str, followed: bool, overridden_to: str | None) -> dict:
    return {
        "reco_id": reco_id,
        "followed": followed,
        "overridden_to": overridden_to,
        "ts": datetime.now(tz=UTC).isoformat(),
    }


def test_telemetry_followed_updates_row(client, db):
    """Happy path : 204 et final_model = modèle recommandé (pas de dérogation)."""
    reco = _create_reco(client)
    response = client.post(
        "/v1/telemetry/reco_event",
        json=_telemetry_body(reco["reco_id"], followed=True, overridden_to=None),
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 204
    row = db.execute(
        sa.text("SELECT followed, final_model FROM events_reco WHERE reco_id = :id"),
        {"id": reco["reco_id"]},
    ).one()
    assert row.followed is True
    assert row.final_model == reco["recommended_model"]


def test_telemetry_override_sets_final_model(client, db):
    """Dérogation : final_model = overridden_to."""
    reco = _create_reco(client)
    response = client.post(
        "/v1/telemetry/reco_event",
        json=_telemetry_body(reco["reco_id"], followed=False, overridden_to="claude-opus-4-8"),
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 204
    row = db.execute(
        sa.text("SELECT followed, final_model FROM events_reco WHERE reco_id = :id"),
        {"id": reco["reco_id"]},
    ).one()
    assert row.followed is False
    assert row.final_model == "claude-opus-4-8"


def test_telemetry_unknown_reco_id_is_404(client):
    response = client.post(
        "/v1/telemetry/reco_event",
        json=_telemetry_body(str(uuid.uuid4()), followed=True, overridden_to=None),
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 404


def test_telemetry_extra_field_is_422(client):
    """GARDE-FOU ANTI-FUITE (règle n°1) : tout champ supplémentaire ⇒ 422.

    En particulier, un `prompt_text` qui s'y glisserait est rejeté avant
    toute persistance.
    """
    reco = _create_reco(client)
    for extra in ({"prompt_text": "du texte interdit"}, {"foo": "bar"}):
        body = _telemetry_body(reco["reco_id"], followed=True, overridden_to=None)
        body.update(extra)
        response = client.post("/v1/telemetry/reco_event", json=body, headers=AUTH_HEADERS)
        assert response.status_code == 422, extra


def test_telemetry_without_token_is_401(client):
    response = client.post(
        "/v1/telemetry/reco_event",
        json=_telemetry_body(str(uuid.uuid4()), followed=True, overridden_to=None),
    )
    assert response.status_code == 401
