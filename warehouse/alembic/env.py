"""Environnement Alembic de l'entrepôt Sobrio (Lot D).

L'URL de connexion est lue depuis la variable d'environnement DATABASE_URL
(défaut : convention de développement locale). Elle n'est JAMAIS écrite dans
alembic.ini ni loggée (règle n°5 : aucun identifiant commité).
"""

from __future__ import annotations

import os

from sqlalchemy import create_engine

from alembic import context

DEFAULT_DATABASE_URL = "postgresql+psycopg://sobrio:sobrio_dev_password@localhost:5432/sobrio"


def _database_url() -> str:
    """URL Postgres : env DATABASE_URL, sinon défaut de développement."""
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


# Pas d'autogénération : le schéma vient VERBATIM de contracts/db_schema.sql
# (source de vérité — tout changement passe par une RFC, règle n°7).
target_metadata = None


def run_migrations_offline() -> None:
    """Mode « offline » : émet le SQL sans se connecter."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Mode « online » : applique les migrations sur la base."""
    connectable = create_engine(_database_url())

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
