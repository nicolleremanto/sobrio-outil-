"""Fixtures pytest du Lot C — base Postgres DÉDIÉE `sobrio_test_connector`.

On ne touche JAMAIS à la base partagée `sobrio` : chaque session de test
recrée sa propre base (DROP/CREATE) et y applique `contracts/db_schema.sql`.
Lancer depuis la racine du monorepo : `.venv/bin/pytest connector/tests`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

# Rend `connector` importable quand pytest est lancé depuis la racine.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

TEST_DB_NAME = "sobrio_test_connector"
# Base d'administration : sert uniquement à créer/détruire la base de test.
ADMIN_DB_URL = "postgresql+psycopg://sobrio:sobrio_dev_password@localhost:5432/sobrio"
TEST_DB_URL = f"postgresql+psycopg://sobrio:sobrio_dev_password@localhost:5432/{TEST_DB_NAME}"

SCHEMA_PATH = REPO_ROOT / "contracts" / "db_schema.sql"
FIXTURES_DIR = REPO_ROOT / "fixtures" / "anthropic"


@pytest.fixture(scope="session")
def test_database_url() -> str:
    """Recrée la base de test dédiée et y applique le schéma des contrats."""
    admin_engine = create_engine(ADMIN_DB_URL, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB_NAME} WITH (FORCE)"))
        conn.execute(text(f"CREATE DATABASE {TEST_DB_NAME}"))
    admin_engine.dispose()

    engine = create_engine(TEST_DB_URL)
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with engine.begin() as conn:
        # psycopg3 (protocole étendu) n'accepte qu'un ordre par execute().
        for statement in schema_sql.split(";"):
            if statement.strip():
                conn.execute(text(statement))
    engine.dispose()
    return TEST_DB_URL


@pytest.fixture()
def clean_db(test_database_url: str) -> str:
    """Vide les tables avant chaque test qui écrit en base."""
    engine = create_engine(test_database_url)
    with engine.begin() as conn:
        conn.execute(
            text("TRUNCATE usage_daily, events_reco, sync_runs, monthly_agg, orgs CASCADE")
        )
    engine.dispose()
    return test_database_url


@pytest.fixture()
def pseudonym_salt(monkeypatch: pytest.MonkeyPatch) -> str:
    """Sel de test pour la pseudonymisation (règle n°1)."""
    salt = "sel-de-test-lot-c"
    monkeypatch.setenv("PSEUDONYM_SALT", salt)
    return salt
