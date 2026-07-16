"""Test (d) — la clé ANTHROPIC_ADMIN_KEY ne fuit ni dans repr() ni dans les logs.

Règle n°5 : la clé d'administration est un actif critique. Ces tests sont des
garde-fous de non-régression : toute fuite dans une représentation ou un log
doit casser la CI.
"""

from __future__ import annotations

import logging

import pytest

from connector.client import AnthropicAdminClient, MissingAdminKeyError
from connector.sync import run_sync

# Fausse clé construite par concaténation pour ne pas déclencher le hook
# pre-commit anti-secrets (regex sur les littéraux « sk-ant-... ») tout en
# gardant le format réaliste à l'exécution.
FAKE_KEY = "sk-ant-" + "admin-TEST-NE-DOIT-JAMAIS-FUITER-0123456789"


def test_repr_never_exposes_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """repr()/str() du client réel ne contiennent jamais la clé, même partielle."""
    monkeypatch.setenv("ANTHROPIC_ADMIN_KEY", FAKE_KEY)
    client = AnthropicAdminClient()
    try:
        for rendered in (repr(client), str(client), f"{client}"):
            assert FAKE_KEY not in rendered
            assert "NE-DOIT-JAMAIS-FUITER" not in rendered
            assert "0123456789" not in rendered
    finally:
        client.close()


def test_missing_key_raises_without_echoing_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sans clé : erreur explicite orientant vers le mode fixtures."""
    monkeypatch.delenv("ANTHROPIC_ADMIN_KEY", raising=False)
    with pytest.raises(MissingAdminKeyError):
        AnthropicAdminClient()


def test_sync_logs_never_contain_key(
    clean_db: str,
    pseudonym_salt: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Un run complet (clé présente dans l'env) ne logge jamais la clé."""
    monkeypatch.setenv("ANTHROPIC_ADMIN_KEY", FAKE_KEY)
    with caplog.at_level(logging.DEBUG):
        run_sync("demo", clean_db, fixtures=True)

    assert caplog.records, "le sync doit journaliser son déroulement"
    for record in caplog.records:
        message = record.getMessage()
        assert FAKE_KEY not in message
        assert "NE-DOIT-JAMAIS-FUITER" not in message
    # Ceinture et bretelles : le texte agrégé non plus.
    assert FAKE_KEY not in caplog.text
