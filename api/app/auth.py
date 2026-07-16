"""Authentification Bearer par token d'organisation.

Le token présenté est haché (sha256) et comparé à `orgs.api_token_hash` :
le token en clair n'est jamais stocké ni loggé. 401 si absent ou inconnu.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.orm import Session

from .db import get_session

# auto_error=False pour renvoyer 401 (et non 403) quand le header est absent,
# conformément au contrat.
_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Org:
    """Organisation authentifiée (identité + politique)."""

    org_id: str
    policy_json: dict[str, Any]


def get_current_org(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: Annotated[Session, Depends(get_session)],
) -> Org:
    """Dépendance FastAPI : résout l'org depuis le token Bearer, sinon 401."""
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=401, detail="Token absent ou invalide")

    token_hash = hashlib.sha256(credentials.credentials.encode()).hexdigest()
    row = session.execute(
        text("SELECT org_id, policy_json FROM orgs WHERE api_token_hash = :h"),
        {"h": token_hash},
    ).first()
    if row is None:
        raise HTTPException(status_code=401, detail="Token absent ou invalide")

    return Org(org_id=row.org_id, policy_json=row.policy_json or {})
