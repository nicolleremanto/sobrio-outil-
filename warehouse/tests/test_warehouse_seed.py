"""Tests du seed : déterminisme, idempotence, volumes et règle n°1."""

from __future__ import annotations

import hashlib
import os
from datetime import date

import sqlalchemy as sa

# Clés autorisées dans features_json : schéma Features de contracts/openapi.yaml.
FEATURES_KEYS_CONTRAT = {
    "char_len",
    "token_est",
    "lang",
    "has_code",
    "has_attachment_hint",
    "keyword_flags",
}

MODELES_CATALOGUE = {"haiku-4-5", "sonnet-4-6", "opus-4-8"}


def test_seed_deux_fois_etat_identique(seeded):
    # Déterminisme + idempotence : relancer le seed ne change RIEN.
    state_1, state_2 = seeded
    assert state_1 == state_2


def test_org_demo_presente_avec_token_hache(engine, seeded):
    token = os.environ.get("DEMO_ORG_TOKEN", "demo-token-not-a-secret")
    attendu = hashlib.sha256(token.encode()).hexdigest()
    with engine.connect() as conn:
        row = conn.execute(
            sa.text("SELECT api_token_hash FROM orgs WHERE org_id = 'demo'")
        ).fetchone()
    assert row is not None, "org demo absente"
    assert row[0] == attendu


def test_usage_daily_60_jours_et_modeles_du_catalogue(engine, seeded):
    with engine.connect() as conn:
        stats = conn.execute(
            sa.text(
                """
                SELECT count(DISTINCT date), min(date), max(date),
                       count(DISTINCT snapshot_ts)
                FROM usage_daily WHERE org_id = 'demo'
                """
            )
        ).fetchone()
        modeles = {
            r[0]
            for r in conn.execute(
                sa.text("SELECT DISTINCT model FROM usage_daily WHERE org_id = 'demo'")
            )
        }
        sources = {
            r[0]
            for r in conn.execute(
                sa.text("SELECT DISTINCT source FROM usage_daily WHERE org_id = 'demo'")
            )
        }
    n_jours, date_min, date_max, n_snapshots = stats
    assert n_jours == 60
    assert date_min == date(2026, 5, 12)
    assert date_max == date(2026, 7, 10)
    assert n_snapshots == 1, "snapshot_ts doit être FIXE (règle n°6)"
    assert modeles == MODELES_CATALOGUE
    assert sources == {"anthropic_admin"}


def test_events_reco_volume_et_repartition(engine, seeded):
    with engine.connect() as conn:
        total, suivis = conn.execute(
            sa.text(
                """
                SELECT count(*), count(*) FILTER (WHERE followed)
                FROM events_reco WHERE org_id = 'demo'
                """
            )
        ).fetchone()
        hors_juin = conn.execute(
            sa.text(
                """
                SELECT count(*) FROM events_reco
                WHERE org_id = 'demo'
                  AND (ts < '2026-06-01T00:00:00Z' OR ts >= '2026-07-01T00:00:00Z')
                """
            )
        ).scalar_one()
        regles = {
            r[0]
            for r in conn.execute(
                sa.text("SELECT DISTINCT rule FROM events_reco WHERE org_id = 'demo'")
            )
        }
    assert 280 <= total <= 320, "~300 événements attendus"
    assert 0.60 <= suivis / total <= 0.80, "taux de suivi attendu ~70%"
    assert hors_juin == 0, "tous les événements doivent être en juin 2026"
    assert regles == {
        "heuristic:short_simple",
        "heuristic:code_task",
        "heuristic:complex_task",
    }


def test_events_reco_sans_texte_et_fourchettes_valides(engine, seeded):
    # Règle n°1 : features_json ne contient QUE les clés du contrat (aucun texte).
    with engine.connect() as conn:
        cles = {
            r[0]
            for r in conn.execute(
                sa.text(
                    """
                    SELECT DISTINCT jsonb_object_keys(features_json)
                    FROM events_reco WHERE org_id = 'demo'
                    """
                )
            )
        }
        # Règle n°3 : fourchettes cohérentes (min <= max) et modèles du catalogue.
        invalides = conn.execute(
            sa.text(
                """
                SELECT count(*) FROM events_reco
                WHERE org_id = 'demo'
                  AND (impact_wh_min > impact_wh_max OR cost_eur_min > cost_eur_max)
                """
            )
        ).scalar_one()
        modeles = {
            r[0]
            for r in conn.execute(
                sa.text(
                    """
                    SELECT DISTINCT recommended_model FROM events_reco WHERE org_id = 'demo'
                    UNION
                    SELECT DISTINCT final_model FROM events_reco
                    WHERE org_id = 'demo' AND final_model IS NOT NULL
                    """
                )
            )
        }
    assert cles == FEATURES_KEYS_CONTRAT
    assert invalides == 0
    assert modeles <= MODELES_CATALOGUE
