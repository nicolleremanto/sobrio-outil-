"""Test (c) — IDEMPOTENCE : deux runs fixtures => usage_daily strictement identique."""

from __future__ import annotations

import hashlib

from sqlalchemy import create_engine, text

from connector.sync import run_sync

_SELECT_ALL = text(
    """
    SELECT org_id, date, source, workspace_id, api_key_id, user_pseudonym, product,
           model, tokens_in_uncached, tokens_in_cached, tokens_cache_write,
           tokens_out, cost_usd, snapshot_ts
    FROM usage_daily
    ORDER BY date, source, workspace_id, api_key_id, user_pseudonym, product, model
    """
)


def _table_state(database_url: str) -> tuple[int, str]:
    """(nombre de lignes, somme de contrôle du contenu, id série exclu)."""
    engine = create_engine(database_url)
    with engine.connect() as conn:
        rows = conn.execute(_SELECT_ALL).all()
    engine.dispose()
    digest = hashlib.sha256(repr(rows).encode()).hexdigest()
    return len(rows), digest


def test_sync_fixtures_is_idempotent(clean_db: str, pseudonym_salt: str) -> None:
    """Deux exécutions successives produisent le MÊME état final (compte + checksum)."""
    result1 = run_sync("demo", clean_db, fixtures=True)
    count1, checksum1 = _table_state(clean_db)

    assert result1.status == "ok"
    assert result1.rows_ingested > 0
    assert count1 == result1.rows_ingested

    result2 = run_sync("demo", clean_db, fixtures=True)
    count2, checksum2 = _table_state(clean_db)

    # snapshot_ts déterministe : dérivé des fixtures, identique entre les runs.
    assert result2.snapshot_ts == result1.snapshot_ts
    # Deuxième run : tout est déjà là, rien n'est ré-inséré.
    assert result2.rows_ingested == 0
    assert (count2, checksum2) == (count1, checksum1)


def test_sync_records_runs_and_window(clean_db: str, pseudonym_salt: str) -> None:
    """Chaque run laisse une trace dans sync_runs, avec la fenêtre J-30 (règle n°6)."""
    result = run_sync("demo", clean_db, fixtures=True)
    run_sync("demo", clean_db, fixtures=True)

    assert (result.window_end - result.window_start).days == 30

    engine = create_engine(clean_db)
    with engine.connect() as conn:
        runs = conn.execute(
            text(
                "SELECT status, rows_ingested, window_start, window_end, "
                "started_at, finished_at FROM sync_runs ORDER BY id"
            )
        ).all()
        dates = conn.execute(
            text("SELECT min(date), max(date) FROM usage_daily")
        ).one()
    engine.dispose()

    assert len(runs) == 2
    assert all(r.status == "ok" for r in runs)
    assert all(r.finished_at >= r.started_at for r in runs)
    assert runs[0].rows_ingested > 0
    assert runs[1].rows_ingested == 0
    # Aucune ligne ingérée hors de la fenêtre J-30.
    assert dates[0] >= result.window_start
    assert dates[1] <= result.window_end
