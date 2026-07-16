"""Tests de la migration Alembic : base vierge -> schéma du contrat.

La fixture ``engine`` (conftest) crée ``sobrio_test_warehouse`` vierge puis
lance la commande canonique ``alembic -c warehouse/alembic.ini upgrade head``.
"""

from __future__ import annotations

import sqlalchemy as sa

TABLES_ATTENDUES = {"orgs", "usage_daily", "events_reco", "sync_runs", "monthly_agg"}

COLONNES_UNIQUE_USAGE_DAILY = {
    "org_id",
    "date",
    "source",
    "workspace_id",
    "api_key_id",
    "user_pseudonym",
    "product",
    "model",
    "snapshot_ts",
}


def test_migration_cree_les_5_tables(engine):
    inspector = sa.inspect(engine)
    assert TABLES_ATTENDUES <= set(inspector.get_table_names())


def test_usage_daily_a_sa_contrainte_unique(engine):
    with engine.connect() as conn:
        constraints = conn.execute(
            sa.text(
                """
                SELECT pg_get_constraintdef(oid)
                FROM pg_constraint
                WHERE conrelid = 'usage_daily'::regclass AND contype = 'u'
                """
            )
        ).fetchall()
    assert len(constraints) == 1, "usage_daily doit porter exactement une contrainte UNIQUE"
    definition = constraints[0][0]
    for colonne in COLONNES_UNIQUE_USAGE_DAILY:
        assert colonne in definition, f"colonne {colonne} absente de la contrainte UNIQUE"


def test_monthly_agg_pk_inclut_dim_value(engine):
    # dim_value fait partie de la PK -> la dimension total doit utiliser la
    # sentinelle '*' (jamais NULL).
    inspector = sa.inspect(engine)
    pk = inspector.get_pk_constraint("monthly_agg")
    assert set(pk["constrained_columns"]) == {"org_id", "month", "dimension", "dim_value"}


def test_version_alembic_estampillee(engine):
    with engine.connect() as conn:
        version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar()
    assert version == "0001_schema_initial"
