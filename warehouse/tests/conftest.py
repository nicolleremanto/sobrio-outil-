"""Fixtures des tests du Lot D (entrepôt).

Les tests d'intégration utilisent une base DÉDIÉE ``sobrio_test_warehouse``
(recréée à chaque session) : la base partagée ``sobrio`` n'est JAMAIS touchée.

Lancement (depuis la racine du repo) : .venv/bin/pytest warehouse/tests
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa

WAREHOUSE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = WAREHOUSE_DIR.parent

# Rend `import seed` / `import aggregate` possibles depuis la racine.
if str(WAREHOUSE_DIR) not in sys.path:
    sys.path.insert(0, str(WAREHOUSE_DIR))

TEST_DB_NAME = "sobrio_test_warehouse"
DEFAULT_DATABASE_URL = "postgresql+psycopg://sobrio:sobrio_dev_password@localhost:5432/sobrio"


def _admin_url() -> sa.URL:
    """URL de maintenance (base partagée) pour créer/détruire la base de test."""
    return sa.make_url(os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL))


@pytest.fixture(scope="session")
def test_db_url() -> str:
    """Crée une base de test VIERGE ``sobrio_test_warehouse`` et retourne son URL."""
    admin_engine = sa.create_engine(_admin_url(), isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(sa.text(f"DROP DATABASE IF EXISTS {TEST_DB_NAME} WITH (FORCE)"))
        conn.execute(sa.text(f"CREATE DATABASE {TEST_DB_NAME}"))
    admin_engine.dispose()
    # render_as_string(hide_password=False) : str(URL) masquerait le mot de passe.
    return _admin_url().set(database=TEST_DB_NAME).render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def migrated_db_url(test_db_url: str) -> str:
    """Applique la migration Alembic (commande canonique, depuis la racine)."""
    result = subprocess.run(
        [
            str(REPO_ROOT / ".venv" / "bin" / "alembic"),
            "-c",
            str(REPO_ROOT / "warehouse" / "alembic.ini"),
            "upgrade",
            "head",
        ],
        cwd=REPO_ROOT,
        env={**os.environ, "DATABASE_URL": test_db_url},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"alembic upgrade head a échoué :\n{result.stderr}"
    return test_db_url


@pytest.fixture(scope="session")
def engine(migrated_db_url: str):
    """Moteur SQLAlchemy sur la base de test migrée."""
    eng = sa.create_engine(migrated_db_url)
    yield eng
    eng.dispose()


def snapshot_state(engine: sa.Engine) -> tuple:
    """Empreinte complète de l'état seedé (pour vérifier déterminisme + idempotence).

    Exclut usage_daily.id (BIGSERIAL, non significatif).
    """
    with engine.connect() as conn:
        orgs = conn.execute(
            sa.text("SELECT org_id, name, api_token_hash, policy_json::text FROM orgs ORDER BY org_id")
        ).fetchall()
        usage_hash = conn.execute(
            sa.text(
                """
                SELECT count(*),
                       md5(string_agg(
                           concat_ws('|', org_id, date, source, workspace_id, api_key_id,
                                     user_pseudonym, product, model, tokens_in_uncached,
                                     tokens_in_cached, tokens_cache_write, tokens_out,
                                     cost_usd, snapshot_ts),
                           ';' ORDER BY org_id, date, workspace_id, api_key_id, model))
                FROM usage_daily
                """
            )
        ).fetchone()
        events_hash = conn.execute(
            sa.text(
                """
                SELECT count(*),
                       md5(string_agg(
                           concat_ws('|', reco_id, org_id, ts, surface, features_json::text,
                                     recommended_model, final_model, followed, confidence,
                                     rule, impact_wh_min, impact_wh_max,
                                     cost_eur_min, cost_eur_max),
                           ';' ORDER BY reco_id))
                FROM events_reco
                """
            )
        ).fetchone()
    return (tuple(orgs), tuple(usage_hash), tuple(events_hash))


@pytest.fixture(scope="session")
def seeded(engine: sa.Engine, migrated_db_url: str) -> tuple:
    """Lance le seed DEUX fois et retourne les deux empreintes d'état."""
    import seed

    assert seed.main(["--org", "demo", "--database-url", migrated_db_url]) == 0
    state_1 = snapshot_state(engine)
    assert seed.main(["--org", "demo", "--database-url", migrated_db_url]) == 0
    state_2 = snapshot_state(engine)
    return state_1, state_2
