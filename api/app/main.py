"""Point d'entrée de l'API Sobrio (Lot B — squelette).

L'API stub est le MOCK OFFICIEL du Lot A : réponses conformes à
contracts/openapi.yaml (source de vérité, figée en v1.0 — règle n°7).

Aucun log du corps des requêtes n'est activé, nulle part (règle n°1).
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .logging_conf import setup_logging
from .routes import router

setup_logging()

app = FastAPI(
    title="Sobrio API",
    version="1.0",
    description=(
        "API Sobrio Phase 1 : recommandation de modèle, télémétrie, "
        "configuration de l'extension. Contrat : contracts/openapi.yaml."
    ),
)

# CORS : le content script de l'extension (Lot A) appelle l'API depuis
# l'origine https://claude.ai (pas de host_permissions). Sans ces en-têtes,
# le préflight OPTIONS échoue et l'extension dégrade silencieusement.
# TODO(LotB) : restreindre par org / durcir en prod (Lot F).
_cors_origins = [
    o.strip()
    for o in os.environ.get(
        "SOBRIO_CORS_ORIGINS", "https://claude.ai,http://localhost:3000"
    ).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=600,
)

app.include_router(router)
