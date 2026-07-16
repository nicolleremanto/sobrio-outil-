"""Accès base de données : engine SQLAlchemy + session par requête.

DATABASE_URL est lu depuis l'environnement (convention partagée). Aucun
secret en dur hors valeur de développement local (règle n°5).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_DATABASE_URL = "postgresql+psycopg://sobrio:sobrio_dev_password@localhost:5432/sobrio"


def database_url() -> str:
    """URL de la base, depuis l'environnement (défaut : dev local)."""
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Engine paresseux (créé au premier usage, après lecture de l'env)."""
    return create_engine(database_url(), pool_pre_ping=True)


@lru_cache(maxsize=1)
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """Dépendance FastAPI : une session par requête, fermée en fin de requête."""
    session = _session_factory()()
    try:
        yield session
    finally:
        session.close()
