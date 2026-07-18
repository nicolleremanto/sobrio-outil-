"""Tests de /v1/recommend : conformité au contrat, variation de la reco, auth."""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from helpers_api import AUTH_HEADERS, make_recommend_body

_CATALOG_IDS = {"claude-haiku-4-5", "claude-sonnet-5", "claude-opus-4-8"}


def _assert_conforms_to_contract(payload: dict) -> None:
    """Vérifie la forme exacte de RecommendResponse (contrat v1.0)."""
    assert set(payload.keys()) == {
        "reco_id",
        "recommended_model",
        "confidence",
        "rule",
        "alternatives",
        "impact_estimate",
        "budget",
    }
    uuid.UUID(payload["reco_id"])  # format uuid
    assert payload["recommended_model"] in _CATALOG_IDS
    assert 0 <= payload["confidence"] <= 1
    assert payload["rule"].startswith("heuristic:")
    # Alternatives = les 2 autres modèles du catalogue, deltas en fourchette.
    alt_models = {alt["model"] for alt in payload["alternatives"]}
    assert alt_models == _CATALOG_IDS - {payload["recommended_model"]}
    for alt in payload["alternatives"]:
        assert set(alt.keys()) == {
            "model",
            "delta_cost_eur_per_call_min",
            "delta_cost_eur_per_call_max",
        }
        assert alt["delta_cost_eur_per_call_min"] <= alt["delta_cost_eur_per_call_max"]
    # Impact : fourchettes uniquement (règle n°3).
    impact = payload["impact_estimate"]
    assert set(impact.keys()) == {"energy_wh_min", "energy_wh_max", "cost_eur_min", "cost_eur_max"}
    assert impact["energy_wh_min"] <= impact["energy_wh_max"]
    assert impact["cost_eur_min"] <= impact["cost_eur_max"]
    # Budget : null au Lot 0 (TODO(LotB)).
    assert payload["budget"] is None


def test_recommend_short_simple_returns_haiku(client, db):
    response = client.post(
        "/v1/recommend", json=make_recommend_body(token_est=50), headers=AUTH_HEADERS
    )
    assert response.status_code == 200
    payload = response.json()
    _assert_conforms_to_contract(payload)
    assert payload["recommended_model"] == "claude-haiku-4-5"
    assert payload["rule"] == "heuristic:short_simple"

    # INSERT réel dans events_reco, final_model/followed NULL à ce stade.
    row = db.execute(
        sa.text(
            "SELECT recommended_model, final_model, followed, rule, features_json "
            "FROM events_reco WHERE reco_id = :id"
        ),
        {"id": payload["reco_id"]},
    ).one()
    assert row.recommended_model == "claude-haiku-4-5"
    assert row.final_model is None
    assert row.followed is None
    # features_json = uniquement les clés du contrat.
    assert set(row.features_json.keys()) == {
        "char_len",
        "token_est",
        "lang",
        "has_code",
        "has_attachment_hint",
        "keyword_flags",
    }


def test_recommend_varies_with_features(client):
    """La reco varie selon token_est / has_code (démo vivante pour le Lot A)."""
    cases = [
        # (surcharges de features, modèle attendu, règle attendue)
        ({"token_est": 50}, "claude-haiku-4-5", "heuristic:short_simple"),
        ({"token_est": 50, "has_code": True}, "claude-sonnet-5", "heuristic:code_context"),
        ({"token_est": 50, "keyword_flags": ["code"]}, "claude-sonnet-5", "heuristic:code_context"),
        (
            {"token_est": 900, "keyword_flags": ["analyse"]},
            "claude-opus-4-8",
            "heuristic:complex_task",
        ),
        (
            {"token_est": 100, "keyword_flags": ["contrat"]},
            "claude-opus-4-8",
            "heuristic:complex_task",
        ),
    ]
    for overrides, expected_model, expected_rule in cases:
        response = client.post(
            "/v1/recommend", json=make_recommend_body(**overrides), headers=AUTH_HEADERS
        )
        assert response.status_code == 200, overrides
        payload = response.json()
        assert payload["recommended_model"] == expected_model, overrides
        assert payload["rule"] == expected_rule, overrides


def test_recommend_unknown_field_rejected(client):
    """Schéma strict : champ inconnu dans la requête ⇒ 422."""
    body = make_recommend_body()
    body["champ_inattendu"] = "x"
    response = client.post("/v1/recommend", json=body, headers=AUTH_HEADERS)
    assert response.status_code == 422


def test_recommend_without_token_is_401(client):
    response = client.post("/v1/recommend", json=make_recommend_body())
    assert response.status_code == 401


def test_recommend_with_wrong_token_is_401(client):
    response = client.post(
        "/v1/recommend",
        json=make_recommend_body(),
        headers={"Authorization": "Bearer mauvais-token"},
    )
    assert response.status_code == 401


def test_recommend_unknown_router_version_falls_back_to_heuristic(client, test_engine):
    """policy_json.router_version inconnu (chantier R1) -> heuristique, jamais 500."""
    with test_engine.begin() as conn:
        conn.execute(
            sa.text(
                "UPDATE orgs SET policy_json = "
                """'{"router_version": "ml-v42-inexistant"}'::jsonb """
                "WHERE org_id = 'demo'"
            )
        )
    try:
        response = client.post(
            "/v1/recommend", json=make_recommend_body(token_est=50), headers=AUTH_HEADERS
        )
        assert response.status_code == 200
        payload = response.json()
        _assert_conforms_to_contract(payload)
        assert payload["rule"] == "heuristic:short_simple"
    finally:
        with test_engine.begin() as conn:
            conn.execute(sa.text("UPDATE orgs SET policy_json = '{}'::jsonb WHERE org_id = 'demo'"))


def test_recommend_non_object_policy_falls_back_to_heuristic(client, test_engine):
    """RÈGLE 3 : un policy_json non-objet (tableau/scalaire) -> heuristique, jamais 500."""
    with test_engine.begin() as conn:
        conn.execute(
            sa.text("UPDATE orgs SET policy_json = '[1, 2, 3]'::jsonb WHERE org_id = 'demo'")
        )
    try:
        response = client.post(
            "/v1/recommend", json=make_recommend_body(token_est=50), headers=AUTH_HEADERS
        )
        assert response.status_code == 200
        assert response.json()["rule"] == "heuristic:short_simple"
    finally:
        with test_engine.begin() as conn:
            conn.execute(sa.text("UPDATE orgs SET policy_json = '{}'::jsonb WHERE org_id = 'demo'"))
