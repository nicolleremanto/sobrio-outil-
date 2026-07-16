"""Test (b) — pseudonymisation : jamais d'email en clair, hash stable (règle n°1)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from connector.client import FixturesClient
from connector.normalize import MissingSaltError, normalize_analytics_rows, pseudonymize

SNAPSHOT = datetime(2026, 7, 9, tzinfo=UTC)


def test_no_clear_email_in_normalized_rows(pseudonym_salt: str) -> None:
    """Aucune valeur des lignes normalisées ne contient d'email ni de domaine."""
    raw = list(FixturesClient().analytics_by_user())
    assert raw, "fixtures analytics vides"
    emails = {item["user_email"] for item in raw}

    rows = normalize_analytics_rows(raw, org_id="demo", snapshot_ts=SNAPSHOT)

    assert len(rows) == len(raw)
    for row in rows:
        for value in row.values():
            text_value = str(value)
            assert "@" not in text_value
            assert "exemple-client.eu" not in text_value
            assert text_value not in emails
        assert row["user_pseudonym"]
        assert len(row["user_pseudonym"]) == 16


def test_pseudonym_stable_for_same_salt(pseudonym_salt: str) -> None:
    """Même sel + même email => même pseudonyme (agrégations mensuelles stables)."""
    p1 = pseudonymize("a.martin@exemple-client.eu")
    p2 = pseudonymize("a.martin@exemple-client.eu")
    assert p1 == p2
    assert pseudonymize("c.dubois@exemple-client.eu") != p1


def test_pseudonym_changes_with_salt(monkeypatch: pytest.MonkeyPatch) -> None:
    """Le sel participe bien au hash (pas un simple sha256 de l'email)."""
    monkeypatch.setenv("PSEUDONYM_SALT", "sel-a")
    p_a = pseudonymize("a.martin@exemple-client.eu")
    monkeypatch.setenv("PSEUDONYM_SALT", "sel-b")
    p_b = pseudonymize("a.martin@exemple-client.eu")
    assert p_a != p_b


def test_missing_salt_refuses_to_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sans PSEUDONYM_SALT : refus explicite, jamais de repli en clair."""
    monkeypatch.delenv("PSEUDONYM_SALT", raising=False)
    with pytest.raises(MissingSaltError):
        pseudonymize("a.martin@exemple-client.eu")
