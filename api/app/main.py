"""Point d'entrée de l'API Sobrio (Lot B — squelette).

L'API stub est le MOCK OFFICIEL du Lot A : réponses conformes à
contracts/openapi.yaml (source de vérité, v1.1 / RFC-0003 — règle n°7).

Aucun log du corps des requêtes n'est activé, nulle part (règle n°1).

R6 (MAJOR-2, 2026-07-23) : handler `RequestValidationError` GLOBAL qui
caviarde `input`/`ctx` de chaque détail 422 avant sérialisation — mesure
STRUCTURELLE anti-écho du texte (spec R6 §10.1) : pydantic v2 embarque la
VALEUR fautive dans `input` (ex. un `prompt_text` envoyé sous un nom de
champ erroné, rejeté par `extra="forbid"`, serait sinon RENVOYÉ au client
et potentiellement loggé). `loc`/`msg`/`type` suffisent au débogage
contractuel.
"""

from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .logging_conf import setup_logging
from .routes import router

setup_logging()

app = FastAPI(
    title="Sobrio API",
    version="1.1",  # RFC-0003 : ExtensionConfig += assist_mode (aligné sur openapi.yaml)
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
    for o in os.environ.get("SOBRIO_CORS_ORIGINS", "https://claude.ai,http://localhost:3000").split(
        ","
    )
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

# Marqueur de caviardage des détails 422 (MAJOR-2) — valeur fixe, jamais
# dérivée du contenu reçu.
_REDACTED = "<redacted>"


def _caviarder_details_validation(erreurs: list[dict]) -> list[dict]:
    """Caviarde CHAQUE détail d'erreur de validation avant sérialisation.

    Politique en LISTE BLANCHE (aucune clé future de pydantic ne peut
    ré-échoïser du contenu) : seuls `loc`/`msg`/`type` sont conservés tels
    quels ; `input` et `ctx`, s'ils sont présents, sont REMPLACÉS par le
    marqueur `<redacted>` (leur présence reste visible, leur valeur jamais) ;
    toute autre clé (ex. `url`) est simplement omise.

    Pure et testée unitairement (spec §10.1 — mutation : retirer le
    caviardage fait échouer le cas « sentinelle dans un champ extra »).
    """
    details: list[dict] = []
    for erreur in erreurs:
        detail: dict = {}
        if "loc" in erreur:
            # tuple (str | int, ...) chez pydantic — listifié pour le JSON.
            detail["loc"] = list(erreur["loc"])
        for cle in ("msg", "type"):
            if cle in erreur:
                detail[cle] = str(erreur[cle])
        for cle in ("input", "ctx"):
            if cle in erreur:
                detail[cle] = _REDACTED
        details.append(detail)
    return details


@app.exception_handler(RequestValidationError)
async def _handler_validation_caviarde(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """422 contractuel SANS écho du corps reçu (règle n°1, MAJOR-2).

    Remplace le handler FastAPI par défaut, qui sérialise `exc.errors()`
    verbatim — `input` compris. Aucun log ici : le détail caviardé part au
    client, rien d'autre ne sort.
    """
    return JSONResponse(
        status_code=422,
        content={"detail": _caviarder_details_validation(exc.errors())},
    )
