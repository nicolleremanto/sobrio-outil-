"""Test (a) — pagination du FixturesClient : p1 + p2 concaténées, dans l'ordre."""

from __future__ import annotations

import json

import pytest

from connector.client import DEFAULT_FIXTURES_DIR, FixturesClient


def _load(name: str) -> dict:
    return json.loads((DEFAULT_FIXTURES_DIR / name).read_text(encoding="utf-8"))


def test_fixtures_pagination_metadata() -> None:
    """Sanité des fixtures : p1 annonce une suite, p2 clôt la pagination."""
    p1 = _load("usage_report_messages_p1.json")
    p2 = _load("usage_report_messages_p2.json")
    assert p1["has_more"] is True
    assert p1["next_page"]
    assert p2["has_more"] is False
    assert p2["next_page"] is None


def test_usage_pagination_concatenates_all_pages() -> None:
    """L'itérateur rejoue la pagination et rend p1 puis p2, sans perte ni doublon."""
    p1 = _load("usage_report_messages_p1.json")
    p2 = _load("usage_report_messages_p2.json")

    buckets = list(FixturesClient().usage_report_messages())

    assert len(buckets) == len(p1["data"]) + len(p2["data"])
    assert buckets == p1["data"] + p2["data"]
    # Continuité temporelle à la frontière des pages.
    assert buckets[len(p1["data"])]["starting_at"] == p2["data"][0]["starting_at"]


def test_single_page_endpoints() -> None:
    """cost_report et analytics tiennent sur une page (has_more=false)."""
    client = FixturesClient()
    cost = list(client.cost_report())
    analytics = list(client.analytics_by_user())
    assert cost == _load("cost_report_p1.json")["data"]
    assert analytics == _load("analytics_by_user_p1.json")["data"]


def test_missing_fixture_raises(tmp_path) -> None:
    """Répertoire vide : erreur explicite, pas d'itérateur silencieusement vide."""
    with pytest.raises(FileNotFoundError):
        list(FixturesClient(tmp_path).usage_report_messages())
