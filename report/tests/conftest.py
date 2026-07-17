"""Fixtures des tests du Lot E (rapport mensuel PDF).

- rend ``report/generate.py`` importable depuis la racine du repo ;
- fournit une base PostgreSQL DÉDIÉE ``sobrio_test_report`` (jamais la base
  partagée ``sobrio`` — le Lot D tourne en parallèle) recréée à chaque session
  de test, avec le schéma de ``contracts/db_schema.sql`` et un jeu de données
  minimal plausible pour 2026-06 ;
- fournit des résultats de requêtes factices pour les tests sans base.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

REPORT_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = REPORT_DIR.parent
if str(REPORT_DIR) not in sys.path:
    sys.path.insert(0, str(REPORT_DIR))

# Base DÉDIÉE au Lot E — la base partagée "sobrio" appartient aux autres lots.
TEST_DB_NAME = "sobrio_test_report"
_PG = os.environ.get("SOBRIO_TEST_PG", "sobrio:sobrio_dev_password@localhost:5432")
ADMIN_URL = f"postgresql+psycopg://{_PG}/sobrio"
TEST_DB_URL = f"postgresql+psycopg://{_PG}/{TEST_DB_NAME}"

MOIS_DEMO = date(2026, 6, 1)


def _appliquer_schema(conn) -> None:
    """Applique contracts/db_schema.sql (source de vérité, jamais modifiée)."""
    schema = (REPO_ROOT / "contracts" / "db_schema.sql").read_text(encoding="utf-8")
    for instruction in schema.split(";"):
        if instruction.strip():
            conn.execute(text(instruction))


def _inserer_seed(conn) -> None:
    """Jeu de données minimal plausible pour le mois de démo 2026-06.

    Convention partagée : dimension « total » avec dim_value sentinelle « * ».
    Les ventilations par modèle / workspace somment vers le total.
    """
    token = os.environ.get("DEMO_ORG_TOKEN", "demo-token-not-a-secret")
    conn.execute(
        text("INSERT INTO orgs (org_id, name, api_token_hash) VALUES (:o, :n, :h)"),
        {
            "o": "demo",
            "n": "Organisation de démonstration",
            "h": hashlib.sha256(token.encode()).hexdigest(),
        },
    )

    lignes_agg = [
        # (dimension, dim_value, tokens, cost_usd, wh_min, wh_max)
        ("total", "*", 12_500_000, 1842.50, 2520.00, 10845.00),
        ("model", "claude-haiku-4-5", 6_000_000, 320.00, 540.00, 2520.00),
        ("model", "claude-sonnet-5", 4_500_000, 780.50, 1080.00, 4725.00),
        ("model", "claude-opus-4-8", 2_000_000, 742.00, 900.00, 3600.00),
        ("workspace", "ws_produit", 7_500_000, 1105.50, 1520.00, 6500.00),
        ("workspace", "ws_support", 5_000_000, 737.00, 1000.00, 4345.00),
    ]
    for dimension, dim_value, tokens, cost, wh_min, wh_max in lignes_agg:
        conn.execute(
            text(
                "INSERT INTO monthly_agg (org_id, month, dimension, dim_value, tokens_total,"
                " cost_usd, energy_wh_min, energy_wh_max, catalog_version)"
                " VALUES (:org, :mois, :dim, :val, :tok, :cout, :whmin, :whmax, :cat)"
            ),
            {
                "org": "demo",
                "mois": MOIS_DEMO,
                "dim": dimension,
                "val": dim_value,
                "tok": tokens,
                "cout": cost,
                "whmin": wh_min,
                "whmax": wh_max,
                "cat": "2026-07.2",
            },
        )

    # Événements de recommandation : features SANS texte (contrat OpenAPI, règle n°1).
    features = json.dumps(
        {
            "char_len": 320,
            "token_est": 80,
            "lang": "fr",
            "has_code": False,
            "has_attachment_hint": False,
            "keyword_flags": ["resume"],
        }
    )
    evenements = [
        # (ts, recommandé, final, followed, wh_min, wh_max, eur_min, eur_max)
        (
            datetime(2026, 6, 3, 9, 15, tzinfo=UTC),
            "claude-haiku-4-5",
            "claude-haiku-4-5",
            True,
            0.4,
            1.8,
            0.002,
            0.010,
        ),
        (
            datetime(2026, 6, 10, 14, 30, tzinfo=UTC),
            "claude-haiku-4-5",
            "claude-haiku-4-5",
            True,
            0.5,
            2.1,
            0.003,
            0.012,
        ),
        (
            datetime(2026, 6, 24, 11, 5, tzinfo=UTC),
            "claude-sonnet-5",
            "claude-sonnet-5",
            True,
            0.7,
            2.5,
            0.004,
            0.020,
        ),
        (
            datetime(2026, 6, 17, 16, 45, tzinfo=UTC),
            "claude-haiku-4-5",
            "claude-opus-4-8",
            False,
            None,
            None,
            None,
            None,
        ),
        (
            datetime(2026, 6, 28, 8, 0, tzinfo=UTC),
            "claude-sonnet-5",
            None,
            None,
            None,
            None,
            None,
            None,
        ),
        # Hors fenêtre (mai) : ne doit PAS compter dans le mois 2026-06.
        (
            datetime(2026, 5, 20, 10, 0, tzinfo=UTC),
            "claude-haiku-4-5",
            "claude-haiku-4-5",
            True,
            9.0,
            90.0,
            9.0,
            90.0,
        ),
    ]
    for ts, reco, final, followed, whmin, whmax, eurmin, eurmax in evenements:
        conn.execute(
            text(
                "INSERT INTO events_reco (reco_id, org_id, ts, surface, features_json,"
                " recommended_model, final_model, followed, confidence, rule,"
                " impact_wh_min, impact_wh_max, cost_eur_min, cost_eur_max)"
                " VALUES (:id, :org, :ts, 'claude_web', CAST(:features AS jsonb), :reco,"
                " :final, :followed, 0.8, 'heuristic:short_simple',"
                " :whmin, :whmax, :eurmin, :eurmax)"
            ),
            {
                "id": str(uuid.uuid4()),
                "org": "demo",
                "ts": ts,
                "features": features,
                "reco": reco,
                "final": final,
                "followed": followed,
                "whmin": whmin,
                "whmax": whmax,
                "eurmin": eurmin,
                "eurmax": eurmax,
            },
        )


@pytest.fixture(scope="session")
def base_test_url() -> str:
    """Recrée la base dédiée sobrio_test_report avec schéma + seed 2026-06."""
    admin = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DB_NAME} WITH (FORCE)"))
        conn.execute(text(f"CREATE DATABASE {TEST_DB_NAME}"))
    admin.dispose()

    engine = create_engine(TEST_DB_URL)
    with engine.begin() as conn:
        _appliquer_schema(conn)
        _inserer_seed(conn)
    engine.dispose()
    return TEST_DB_URL


@pytest.fixture()
def resultats_factices() -> dict:
    """Résultats de requêtes plausibles, au format retourné par run_queries()."""
    return {
        "monthly_total": [
            {
                "tokens_total": 12_500_000,
                "cost_usd": 1842.50,
                "energy_wh_min": 2520.00,
                "energy_wh_max": 10845.00,
                "catalog_version": "2026-07.2",
            }
        ],
        "by_model": [
            {
                "model": "claude-haiku-4-5",
                "tokens_total": 6_000_000,
                "cost_usd": 320.00,
                "energy_wh_min": 540.00,
                "energy_wh_max": 2520.00,
            },
            {
                "model": "claude-opus-4-8",
                "tokens_total": 2_000_000,
                "cost_usd": 742.00,
                "energy_wh_min": 900.00,
                "energy_wh_max": 3600.00,
            },
        ],
        "by_workspace": [
            {
                "workspace": "ws_produit",
                "tokens_total": 7_500_000,
                "cost_usd": 1105.50,
                "energy_wh_min": 1520.00,
                "energy_wh_max": 6500.00,
            }
        ],
        "reco_adoption": [
            {"n_events": 5, "n_followed": 3, "n_decided": 4, "adoption_rate_pct": 75.0}
        ],
        "reco_savings": [{"n_followed": 3, "savings_eur_min": 0.009, "savings_eur_max": 0.042}],
        "footprint_avoided": [{"n_followed": 3, "avoided_wh_min": 1.6, "avoided_wh_max": 6.4}],
    }
