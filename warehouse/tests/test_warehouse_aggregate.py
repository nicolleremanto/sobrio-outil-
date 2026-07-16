"""Tests de l'agrégation mensuelle : monthly_agg pour 2026-06."""

from __future__ import annotations

from datetime import date

import pytest
import sqlalchemy as sa

MOIS_DEMO = "2026-06"
MOIS_DEMO_DATE = date(2026, 6, 1)


@pytest.fixture(scope="module")
def aggregated(engine, migrated_db_url, seeded):
    """Lance l'agrégation DEUX fois (idempotence) sur le mois de démo."""
    import aggregate

    assert aggregate.main(["--org", "demo", "--month", MOIS_DEMO,
                           "--database-url", migrated_db_url]) == 0
    with engine.connect() as conn:
        rows_1 = conn.execute(
            sa.text(
                """
                SELECT dimension, dim_value, tokens_total, cost_usd,
                       energy_wh_min, energy_wh_max, catalog_version
                FROM monthly_agg
                WHERE org_id = 'demo' AND month = :m
                ORDER BY dimension, dim_value
                """
            ),
            {"m": MOIS_DEMO_DATE},
        ).fetchall()
    assert aggregate.main(["--org", "demo", "--month", MOIS_DEMO,
                           "--database-url", migrated_db_url]) == 0
    with engine.connect() as conn:
        rows_2 = conn.execute(
            sa.text(
                """
                SELECT dimension, dim_value, tokens_total, cost_usd,
                       energy_wh_min, energy_wh_max, catalog_version
                FROM monthly_agg
                WHERE org_id = 'demo' AND month = :m
                ORDER BY dimension, dim_value
                """
            ),
            {"m": MOIS_DEMO_DATE},
        ).fetchall()
    return rows_1, rows_2


def test_relance_sans_doublon(aggregated):
    rows_1, rows_2 = aggregated
    assert rows_1 == rows_2, "relancer l'agrégation doit produire un état identique"


def test_dimension_total_presente_avec_sentinelle(aggregated):
    rows, _ = aggregated
    totaux = [r for r in rows if r.dimension == "total"]
    assert len(totaux) == 1
    assert totaux[0].dim_value == "*", "la dimension total utilise la sentinelle '*'"
    assert totaux[0].tokens_total > 0
    assert totaux[0].cost_usd > 0


def test_les_5_dimensions_sont_remplies(aggregated):
    rows, _ = aggregated
    dimensions = {r.dimension for r in rows}
    assert dimensions == {"total", "model", "workspace", "api_key", "user"}
    # Topologie du seed : 3 modèles, 2 workspaces, 4 clés, 4 pseudonymes.
    assert len([r for r in rows if r.dimension == "model"]) == 3
    assert len([r for r in rows if r.dimension == "workspace"]) == 2
    assert len([r for r in rows if r.dimension == "api_key"]) == 4


def test_energie_en_fourchette_stricte(aggregated):
    # Règle n°3 : min < max sur chaque ligne (facteurs du catalogue distincts).
    rows, _ = aggregated
    assert rows, "monthly_agg vide pour 2026-06"
    for row in rows:
        assert row.energy_wh_min < row.energy_wh_max, f"fourchette invalide : {row}"


def test_catalog_version_tracee(aggregated):
    rows, _ = aggregated
    assert {r.catalog_version for r in rows} == {"2026-07"}


def test_coherence_total_vs_dimension_model(aggregated):
    # Le total doit être la somme de la dimension model (mêmes lignes sources).
    rows, _ = aggregated
    total = next(r for r in rows if r.dimension == "total")
    par_modele = [r for r in rows if r.dimension == "model"]
    assert sum(r.tokens_total for r in par_modele) == total.tokens_total
    assert float(sum(r.cost_usd for r in par_modele)) == pytest.approx(
        float(total.cost_usd), abs=0.05
    )
    assert float(sum(r.energy_wh_min for r in par_modele)) == pytest.approx(
        float(total.energy_wh_min), abs=0.5
    )
    assert float(sum(r.energy_wh_max for r in par_modele)) == pytest.approx(
        float(total.energy_wh_max), abs=0.5
    )
