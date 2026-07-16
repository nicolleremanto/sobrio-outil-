"""Schéma initial de l'entrepôt Sobrio — applique contracts/db_schema.sql VERBATIM.

Le fichier SQL du contrat est la SOURCE DE VÉRITÉ (règle n°7) : cette migration
le lit tel quel et l'exécute, sans le dupliquer ni le reformuler. Tout
changement de schéma passe par une RFC (docs/rfc/) + contracts/CHANGELOG.md
puis une NOUVELLE migration.

Identifiant : 0001_schema_initial
Précédente : (aucune)
"""

from __future__ import annotations

from pathlib import Path

from alembic import op

# Identifiants de révision utilisés par Alembic.
revision = "0001_schema_initial"
down_revision = None
branch_labels = None
depends_on = None

# warehouse/alembic/versions/ -> racine du repo (parents[3]).
_REPO_ROOT = Path(__file__).resolve().parents[3]
_DB_SCHEMA_SQL = _REPO_ROOT / "contracts" / "db_schema.sql"


def upgrade() -> None:
    """Exécute contracts/db_schema.sql verbatim."""
    op.execute(_DB_SCHEMA_SQL.read_text(encoding="utf-8"))


def downgrade() -> None:
    """Supprime les 5 tables dans l'ordre inverse des dépendances (FK d'abord)."""
    op.execute("DROP TABLE monthly_agg")
    op.execute("DROP TABLE sync_runs")
    op.execute("DROP TABLE events_reco")
    op.execute("DROP TABLE usage_daily")
    op.execute("DROP TABLE orgs")
