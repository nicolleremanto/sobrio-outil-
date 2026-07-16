"""Synchronisation usage/coût Anthropic -> entrepôt Postgres (fenêtre J-30 glissante).

Règle n°6 encodée ici : PAS de temps réel. Les chiffres Anthropic se stabilisent
en ~4-24 h et peuvent être réconciliés jusqu'à J+30 ; on re-tire donc
SYSTÉMATIQUEMENT une fenêtre J-30 glissante, versionnée par `snapshot_ts` :
- mode réel : `snapshot_ts` = début du run (chaque run = un nouveau snapshot) ;
- mode --fixtures : `snapshot_ts` DÉTERMINISTE, dérivé des données (max des
  `ending_at` du usage report), pour que deux exécutions produisent le MÊME
  état final (idempotence testée).

L'ingestion est idempotente : `INSERT ... ON CONFLICT DO NOTHING` sur la
contrainte UNIQUE de `usage_daily`.

Règle n°5 : ce module ne logge JAMAIS la clé d'administration (il ne la
manipule d'ailleurs pas : elle reste confinée dans `connector.client`).
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection

from connector.client import AnthropicAdminClient, FixturesClient
from connector.normalize import (
    apply_cost_buckets,
    normalize_analytics_rows,
    normalize_usage_buckets,
)

logger = logging.getLogger("connector.sync")

# Convention partagée du monorepo (voir .env.example).
DEFAULT_DATABASE_URL = "postgresql+psycopg://sobrio:sobrio_dev_password@localhost:5432/sobrio"

# Fenêtre glissante : J-30 -> J (31 jours couverts), re-tirée à chaque run.
WINDOW_DAYS = 30

_INSERT_USAGE_SQL = text(
    """
    INSERT INTO usage_daily (
      org_id, date, source, workspace_id, api_key_id, user_pseudonym, product,
      model, tokens_in_uncached, tokens_in_cached, tokens_cache_write,
      tokens_out, cost_usd, snapshot_ts
    ) VALUES (
      :org_id, :date, :source, :workspace_id, :api_key_id, :user_pseudonym, :product,
      :model, :tokens_in_uncached, :tokens_in_cached, :tokens_cache_write,
      :tokens_out, :cost_usd, :snapshot_ts
    )
    ON CONFLICT DO NOTHING
    """
)


@dataclass(frozen=True)
class SyncResult:
    """Bilan d'un run de synchronisation (reflété dans `sync_runs`)."""

    org_id: str
    snapshot_ts: datetime
    window_start: date
    window_end: date
    rows_seen: int
    rows_ingested: int
    status: str


def _ensure_org(conn: Connection, org_id: str, *, fixtures: bool) -> None:
    """Vérifie que l'organisation existe ; en mode fixtures, crée l'org de démo.

    L'org `demo` est normalement créée par le seed du Lot D. Si elle est
    absente (base de test vierge), on la crée avec le hash du token de
    convention (`DEMO_ORG_TOKEN`, valeur factice de dev — pas un secret).
    """
    exists = conn.execute(
        text("SELECT 1 FROM orgs WHERE org_id = :org_id"), {"org_id": org_id}
    ).first()
    if exists:
        return
    if not fixtures:
        raise RuntimeError(
            f"Organisation inconnue : {org_id!r}. La créer avant de lancer le sync."
        )
    token = os.environ.get("DEMO_ORG_TOKEN", "demo-token-not-a-secret")
    conn.execute(
        text(
            "INSERT INTO orgs (org_id, name, api_token_hash) "
            "VALUES (:org_id, :name, :token_hash)"
        ),
        {
            "org_id": org_id,
            "name": "Organisation de démonstration (créée par connector.sync --fixtures)",
            "token_hash": hashlib.sha256(token.encode()).hexdigest(),
        },
    )
    logger.info("Org %r absente : créée avec le token de convention (mode fixtures).", org_id)


def _fixture_snapshot_ts(usage_buckets: list[dict[str, Any]]) -> datetime:
    """Snapshot déterministe en mode fixtures : max des `ending_at` du usage report.

    Deux exécutions sur les mêmes fixtures produisent ainsi le même
    `snapshot_ts`, donc le même état final (la contrainte UNIQUE absorbe les
    ré-insertions).
    """
    if not usage_buckets:
        raise ValueError("Fixtures d'usage vides : impossible de dériver snapshot_ts.")
    return max(
        datetime.fromisoformat(str(b["ending_at"]).replace("Z", "+00:00"))
        for b in usage_buckets
    )


def run_sync(
    org_id: str,
    database_url: str,
    *,
    fixtures: bool,
    fixtures_dir: str | None = None,
) -> SyncResult:
    """Exécute un run complet : lecture, normalisation, fenêtrage J-30, ingestion.

    Retourne le bilan du run, également enregistré dans `sync_runs`.
    """
    started_at = datetime.now(UTC)
    client = (
        FixturesClient(fixtures_dir) if fixtures else AnthropicAdminClient()
    )
    engine = create_engine(database_url)
    status, error = "ok", None
    rows: list[dict[str, Any]] = []
    ingested = 0
    try:
        # 1. Lecture (pagination absorbée par le client).
        # TODO(LotC) : en mode réel, passer starting_at/ending_at = fenêtre J-30
        # aux endpoints plutôt que de tout lire puis filtrer.
        usage_buckets = list(client.usage_report_messages())
        cost_buckets = list(client.cost_report())
        analytics_items = list(client.analytics_by_user())

        # 2. Versionnage (règle n°6).
        snapshot_ts = _fixture_snapshot_ts(usage_buckets) if fixtures else started_at
        window_end = (snapshot_ts - timedelta(seconds=1)).date()
        window_start = window_end - timedelta(days=WINDOW_DAYS)
        logger.info(
            "Fenêtre J-%d : %s -> %s (snapshot_ts=%s, mode=%s)",
            WINDOW_DAYS,
            window_start,
            window_end,
            snapshot_ts.isoformat(),
            "fixtures" if fixtures else "réel",
        )

        # 3. Normalisation (pseudonymisation incluse — règle n°1) puis fenêtrage.
        rows = normalize_usage_buckets(usage_buckets, org_id=org_id, snapshot_ts=snapshot_ts)
        apply_cost_buckets(rows, cost_buckets)
        rows += normalize_analytics_rows(
            analytics_items, org_id=org_id, snapshot_ts=snapshot_ts
        )
        rows = [r for r in rows if window_start <= r["date"] <= window_end]

        # 4. Ingestion idempotente.
        with engine.begin() as conn:
            _ensure_org(conn, org_id, fixtures=fixtures)
            for row in rows:
                result = conn.execute(_INSERT_USAGE_SQL, row)
                ingested += result.rowcount
        logger.info(
            "%d lignes dans la fenêtre, %d insérées, %d déjà présentes (idempotence).",
            len(rows),
            ingested,
            len(rows) - ingested,
        )
    except Exception as exc:
        status = "error"
        # Prudence règle n°5 : on n'enregistre que le type et le message de
        # l'exception, jamais de contenu de requête/en-têtes.
        error = f"{type(exc).__name__}: {exc}"
        snapshot_ts = started_at
        window_start = window_end = started_at.date()
        raise
    finally:
        finished_at = datetime.now(UTC)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO sync_runs (org_id, started_at, finished_at, "
                    "window_start, window_end, rows_ingested, status, error) "
                    "VALUES (:org_id, :started_at, :finished_at, "
                    ":window_start, :window_end, :rows_ingested, :status, :error)"
                ),
                {
                    "org_id": org_id,
                    "started_at": started_at,
                    "finished_at": finished_at,
                    "window_start": window_start,
                    "window_end": window_end,
                    "rows_ingested": ingested,
                    "status": status,
                    "error": error,
                },
            )
        client.close()
        engine.dispose()

    return SyncResult(
        org_id=org_id,
        snapshot_ts=snapshot_ts,
        window_start=window_start,
        window_end=window_end,
        rows_seen=len(rows),
        rows_ingested=ingested,
        status=status,
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m connector.sync",
        description=(
            "Synchronise l'usage/coût Anthropic vers l'entrepôt (fenêtre J-30 "
            "glissante, idempotent). Mode --fixtures : sans réseau, sans clé."
        ),
    )
    parser.add_argument("--org", default="demo", help="identifiant d'organisation (défaut : demo)")
    parser.add_argument(
        "--fixtures",
        action="store_true",
        help="rejoue fixtures/anthropic/*.json au lieu d'appeler l'API réelle",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL),
        help="URL SQLAlchemy de l'entrepôt (défaut : env DATABASE_URL)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    result = run_sync(args.org, args.database_url, fixtures=args.fixtures)
    print(
        f"[{result.status}] org={result.org_id} "
        f"fenêtre={result.window_start}..{result.window_end} "
        f"snapshot_ts={result.snapshot_ts.isoformat()} "
        f"lignes_vues={result.rows_seen} lignes_ingérées={result.rows_ingested}"
    )
