# type: ignore
"""${message}

Identifiant : ${up_revision}
Précédente : ${down_revision | comma,n}
Date : ${create_date}
"""
from __future__ import annotations

${imports if imports else ""}

# Identifiants de révision utilisés par Alembic.
revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
