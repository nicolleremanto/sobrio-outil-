"""Tests du pont routeur (chantier R1, corrections ronde 0).

Vérifie la posture défensive de `router_bridge` : `router_version` mal typé
(entier, null) et ÉCHEC DE CONSTRUCTION du routeur primaire (artefact ML
manquant/corrompu au chargement, R5) — dans tous les cas /v1/recommend
répond 200, jamais 500 (invariant §5.2 : l'API reste disponible).
"""

from __future__ import annotations

import sqlalchemy as sa
from helpers_api import AUTH_HEADERS, make_recommend_body

from app import router_bridge


def _with_policy(test_engine, policy_sql: str):
    with test_engine.begin() as conn:
        conn.execute(
            sa.text(f"UPDATE orgs SET policy_json = {policy_sql}::jsonb WHERE org_id = 'demo'")
        )


def _reset_policy(test_engine):
    with test_engine.begin() as conn:
        conn.execute(sa.text("UPDATE orgs SET policy_json = '{}'::jsonb WHERE org_id = 'demo'"))


def test_router_version_integer_falls_back_to_heuristic(client, test_engine):
    """router_version=42 (mauvais type DANS un objet valide) -> heuristique, 200."""
    _with_policy(test_engine, "'{\"router_version\": 42}'")
    try:
        response = client.post(
            "/v1/recommend", json=make_recommend_body(token_est=50), headers=AUTH_HEADERS
        )
        assert response.status_code == 200
        assert response.json()["rule"] == "heuristic:short_simple"
    finally:
        _reset_policy(test_engine)


def test_router_version_null_falls_back_to_heuristic(client, test_engine):
    """router_version=null -> heuristique, 200."""
    _with_policy(test_engine, "'{\"router_version\": null}'")
    try:
        response = client.post(
            "/v1/recommend", json=make_recommend_body(token_est=50), headers=AUTH_HEADERS
        )
        assert response.status_code == 200
        assert response.json()["rule"] == "heuristic:short_simple"
    finally:
        _reset_policy(test_engine)


def test_corrupt_primary_output_serves_fallback_end_to_end(client, monkeypatch):
    """Primaire qui CONSTRUIT sainement mais renvoie une Decision corrompue.

    Comble l'écart relevé par qa (ronde 2) entre la couverture unitaire de
    SafeRouter._validated et le chemin API complet : bridge -> SafeRouter ->
    réponse pydantic. Chaque sortie corrompue doit donner 200 +
    rule=fallback:heuristic — jamais un 500.
    """
    import math

    from sobrio_router import Decision, Router

    corrupt_decisions = [
        Decision(model="claude-sonnet-5", confidence=0.9, rule=None),  # 500 pydantic sinon
        Decision(model="claude-sonnet-5", confidence=math.inf, rule="ml:v05"),
        Decision(model="claude-fable-5", confidence=0.9, rule="ml:v05"),  # non visible
    ]
    for corrupt in corrupt_decisions:

        class _CorruptRouter(Router):
            def __init__(self, decision):
                self._decision = decision

            def decide(self, signals):
                return self._decision

        router_bridge._router_for_version.cache_clear()
        monkeypatch.setattr(
            router_bridge,
            "_build_primary",
            lambda version, _d=corrupt: _CorruptRouter(_d),
        )
        try:
            response = client.post(
                "/v1/recommend", json=make_recommend_body(token_est=50), headers=AUTH_HEADERS
            )
            assert response.status_code == 200, corrupt
            payload = response.json()
            assert payload["rule"] == "fallback:heuristic", corrupt
            assert 0 <= payload["confidence"] <= 1, corrupt
        finally:
            router_bridge._router_for_version.cache_clear()


def test_primary_construction_failure_serves_fallback(client, monkeypatch):
    """Artefact manquant au CHARGEMENT : l'API répond via le repli heuristique.

    Correction ronde 0 (ml-architect) : un échec dans le constructeur du
    routeur primaire contournait le SafeRouter (lru_cache sans garde) -> 500.
    Désormais : garde de construction -> SafeRouter(primary=None), décisions
    marquées `fallback:heuristic`, API verte.
    """

    def _explosive_build(version: str):
        raise RuntimeError("artefact ML manquant (simulation R5)")

    router_bridge._router_for_version.cache_clear()
    monkeypatch.setattr(router_bridge, "_build_primary", _explosive_build)
    try:
        response = client.post(
            "/v1/recommend", json=make_recommend_body(token_est=50), headers=AUTH_HEADERS
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["rule"] == "fallback:heuristic"
        assert payload["recommended_model"] == "claude-haiku-4-5"  # décision du repli
    finally:
        # Purge le singleton mémorisé pour ne pas polluer les autres tests.
        router_bridge._router_for_version.cache_clear()
