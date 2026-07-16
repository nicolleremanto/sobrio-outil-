"""Fixtures des tests du Lot B (API).

- Base dédiée `sobrio_test_api` (DROP/CREATE à chaque session de tests),
  schéma appliqué depuis contracts/db_schema.sql — la base partagée `sobrio`
  n'est JAMAIS touchée.
- DATABASE_URL surchargé AVANT tout import de l'app (l'engine est paresseux
  mais mis en cache : l'ordre compte).
- Lancement depuis la racine du repo : api/ (pour `from app...`) et
  api/tests/ (pour `helpers_api`) sont insérés dans sys.path.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa

_TESTS_DIR = Path(__file__).resolve().parent  # api/tests/
_API_DIR = _TESTS_DIR.parent  # api/
_REPO_ROOT = _API_DIR.parent

for path in (str(_API_DIR), str(_TESTS_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

from helpers_api import DEMO_TOKEN_HASH  # noqa: E402 (après insertion sys.path)

_TEST_DB = "sobrio_test_api"
_PG_HOST = os.environ.get("SOBRIO_TEST_PG_HOST", "localhost:5432")
_PG_CREDS = "sobrio:sobrio_dev_password"
_ADMIN_URL = f"postgresql+psycopg://{_PG_CREDS}@{_PG_HOST}/sobrio"
_TEST_URL = f"postgresql+psycopg://{_PG_CREDS}@{_PG_HOST}/{_TEST_DB}"

# AVANT tout import de app.* : l'engine (app/db.py) lit DATABASE_URL.
os.environ["DATABASE_URL"] = _TEST_URL


def _apply_schema(conn: sa.Connection) -> None:
    """Applique contracts/db_schema.sql (source de vérité) instruction par instruction."""
    schema_sql = (_REPO_ROOT / "contracts" / "db_schema.sql").read_text(encoding="utf-8")
    for statement in schema_sql.split(";"):
        if statement.strip():
            conn.execute(sa.text(statement))


@pytest.fixture(scope="session")
def test_engine():
    """Base de test dédiée : DROP/CREATE + schéma + org de démo."""
    admin_engine = sa.create_engine(_ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(sa.text(f"DROP DATABASE IF EXISTS {_TEST_DB} WITH (FORCE)"))
        conn.execute(sa.text(f"CREATE DATABASE {_TEST_DB}"))
    admin_engine.dispose()

    engine = sa.create_engine(_TEST_URL)
    with engine.begin() as conn:
        _apply_schema(conn)
        conn.execute(
            sa.text(
                "INSERT INTO orgs (org_id, name, api_token_hash, policy_json) "
                "VALUES ('demo', 'Organisation de démo', :h, '{}'::jsonb)"
            ),
            {"h": DEMO_TOKEN_HASH},
        )
    yield engine
    engine.dispose()


@pytest.fixture()
def client(test_engine):
    """TestClient FastAPI branché sur la base de test."""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db(test_engine):
    """Connexion directe à la base de test pour les vérifications SQL."""
    with test_engine.connect() as conn:
        yield conn
