"""Agrégation mensuelle usage_daily -> monthly_agg (STUB propre, Lot 0).

Pour un (org, mois) donné :
1. déduplication « dernier snapshot par clé logique » (versionnage par
   snapshot_ts, règle n°6) — TODO(LotD) : réconciliation complète jusqu'à J+30 ;
2. agrégats par dimension : total, model, workspace, api_key, user ;
3. fourchettes d'énergie via ``sobrio_impact.estimate`` sur les tokens de
   sortie, par modèle puis sommées (règle n°3 : jamais un scalaire) ;
4. ``catalog_version()`` tracée dans chaque ligne.

Idempotent : DELETE du couple (org, mois) puis INSERT.

La dimension ``total`` utilise la valeur sentinelle ``*`` pour ``dim_value``
(colonne membre de la clé primaire : NULL interdit).

Usage (depuis la racine du repo) :
    .venv/bin/python warehouse/aggregate.py --org demo --month 2026-06
"""

from __future__ import annotations

import argparse
import os
from collections import defaultdict
from datetime import date, datetime

import sqlalchemy as sa

from sobrio_impact import catalog_version, estimate

DEFAULT_DATABASE_URL = "postgresql+psycopg://sobrio:sobrio_dev_password@localhost:5432/sobrio"

# Sentinelle de la dimension « total » (dim_value fait partie de la PK).
DIM_TOTAL_SENTINEL = "*"

# Valeur affichable quand la dimension est absente de la ligne source
# (ex. usage sans workspace) — dim_value ne peut pas être NULL (PK).
DIM_UNKNOWN = "(inconnu)"

# Déduplication simple : pour chaque clé logique, on garde la ligne au
# snapshot_ts le plus récent. TODO(LotD) : réconciliation complète J+30
# (fenêtre glissante J-30, corrections rétroactives, historisation).
_DEDUP_AGG_SQL = sa.text(
    """
    WITH dernier_snapshot AS (
        SELECT DISTINCT ON (date, source, workspace_id, api_key_id,
                            user_pseudonym, product, model)
            workspace_id, api_key_id, user_pseudonym, model,
            tokens_in_uncached, tokens_in_cached, tokens_cache_write,
            tokens_out, cost_usd
        FROM usage_daily
        WHERE org_id = :org AND date >= :month_start AND date < :month_end
        ORDER BY date, source, workspace_id, api_key_id, user_pseudonym,
                 product, model, snapshot_ts DESC
    )
    SELECT workspace_id, api_key_id, user_pseudonym, model,
           SUM(tokens_in_uncached + tokens_in_cached
               + tokens_cache_write + tokens_out) AS tokens_total,
           SUM(tokens_out) AS tokens_out,
           COALESCE(SUM(cost_usd), 0) AS cost_usd
    FROM dernier_snapshot
    GROUP BY workspace_id, api_key_id, user_pseudonym, model
    """
)

_INSERT_SQL = sa.text(
    """
    INSERT INTO monthly_agg (
        org_id, month, dimension, dim_value, tokens_total, cost_usd,
        energy_wh_min, energy_wh_max, catalog_version
    ) VALUES (
        :org_id, :month, :dimension, :dim_value, :tokens_total, :cost_usd,
        :energy_wh_min, :energy_wh_max, :catalog_version
    )
    """
)


def _parse_month(value: str) -> tuple[date, date]:
    """'2026-06' -> (premier jour du mois, premier jour du mois suivant)."""
    parsed = datetime.strptime(value, "%Y-%m")
    start = date(parsed.year, parsed.month, 1)
    if start.month == 12:
        end = date(start.year + 1, 1, 1)
    else:
        end = date(start.year, start.month + 1, 1)
    return start, end


def _dim_value_of(dimension: str, row: sa.Row) -> str:
    """Valeur de dimension d'une ligne source (sentinelles : '*' et '(inconnu)')."""
    if dimension == "total":
        return DIM_TOTAL_SENTINEL
    value = {
        "model": row.model,
        "workspace": row.workspace_id,
        "api_key": row.api_key_id,
        "user": row.user_pseudonym,
    }[dimension]
    return value if value is not None else DIM_UNKNOWN


def _build_agg_rows(org_id: str, month_start: date, rows: list[sa.Row]) -> list[dict]:
    """Construit les lignes monthly_agg pour les 5 dimensions."""
    version = catalog_version()
    out_rows: list[dict] = []
    for dimension in ("total", "model", "workspace", "api_key", "user"):
        # Accumulateurs par valeur de dimension ; les tokens de sortie restent
        # ventilés PAR MODÈLE car les facteurs d'énergie sont par modèle.
        tokens_total: dict[str, int] = defaultdict(int)
        cost_usd: dict[str, float] = defaultdict(float)
        tokens_out_by_model: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for row in rows:
            dim_value = _dim_value_of(dimension, row)
            tokens_total[dim_value] += int(row.tokens_total)
            cost_usd[dim_value] += float(row.cost_usd)
            tokens_out_by_model[dim_value][row.model] += int(row.tokens_out)

        for dim_value in sorted(tokens_total):
            # Règle n°3 : l'énergie est une fourchette min-max issue du module
            # d'impact (Range), estimée par modèle puis sommée.
            energy_min = 0.0
            energy_max = 0.0
            for model, tok_out in tokens_out_by_model[dim_value].items():
                impact = estimate(model, tok_out)
                energy_min += impact.min
                energy_max += impact.max
            out_rows.append(
                {
                    "org_id": org_id,
                    "month": month_start,
                    "dimension": dimension,
                    "dim_value": dim_value,
                    "tokens_total": tokens_total[dim_value],
                    "cost_usd": round(cost_usd[dim_value], 4),
                    "energy_wh_min": round(energy_min, 2),
                    "energy_wh_max": round(energy_max, 2),
                    "catalog_version": version,
                }
            )
    return out_rows


def aggregate_month(engine: sa.Engine, org_id: str, month: str) -> int:
    """Recalcule monthly_agg pour (org, mois). Retourne le nombre de lignes écrites."""
    month_start, month_end = _parse_month(month)
    with engine.begin() as conn:
        rows = conn.execute(
            _DEDUP_AGG_SQL,
            {"org": org_id, "month_start": month_start, "month_end": month_end},
        ).fetchall()
        agg_rows = _build_agg_rows(org_id, month_start, rows)
        # Idempotence : on remplace intégralement le couple (org, mois).
        conn.execute(
            sa.text("DELETE FROM monthly_agg WHERE org_id = :org AND month = :month"),
            {"org": org_id, "month": month_start},
        )
        if agg_rows:
            conn.execute(_INSERT_SQL, agg_rows)
    return len(agg_rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Agrégation mensuelle usage_daily -> monthly_agg (stub Lot 0)."
    )
    parser.add_argument("--org", default="demo", help="Identifiant de l'organisation")
    parser.add_argument("--month", required=True, help="Mois au format AAAA-MM (ex. 2026-06)")
    parser.add_argument(
        "--database-url",
        default=None,
        help="URL Postgres (défaut : env DATABASE_URL, sinon convention locale)",
    )
    args = parser.parse_args(argv)

    url = args.database_url or os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
    engine = sa.create_engine(url)
    written = aggregate_month(engine, args.org, args.month)
    engine.dispose()

    print(
        f"Agrégation terminée pour org={args.org}, mois={args.month} : "
        f"{written} lignes monthly_agg (catalogue {catalog_version()})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
