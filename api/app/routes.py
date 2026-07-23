"""Les trois routes du contrat contracts/openapi.yaml (v1.1).

v1.1 (RFC-0003) : ExtensionConfig porte assist_mode + auto_confidence_threshold
(optionnels, compat ascendante). Toute évolution passe par une RFC (docs/rfc/) +
contracts/CHANGELOG.md (règle n°7).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import ValidationError
from sobrio_router import features_to_signals
from sqlalchemy import text
from sqlalchemy.orm import Session

from .auth import Org, get_current_org
from .catalog import visible_model_ids
from .db import get_session
from .router import build_alternatives, build_impact_estimate
from .router_bridge import _stage2_unlocked, router_for_org
from .schemas import (
    ExtensionConfig,
    RecoEvent,
    RecommendRequest,
    RecommendResponse,
)

logger = logging.getLogger("sobrio.api")

router = APIRouter(prefix="/v1")

# Libellés par défaut de l'extension (français d'abord).
_DEFAULT_MESSAGES_FR = {
    "reco_title": "Modèle conseillé",
    "reco_hint": "Sobrio conseille, vous décidez — rien n'est automatisé.",
    "impact_note": "Estimations en fourchettes (min–max), périmètre inférence.",
    "override_label": "J'utilise un autre modèle",
}


@router.post("/recommend", response_model=RecommendResponse)
def recommend(
    body: RecommendRequest,
    org: Annotated[Org, Depends(get_current_org)],
    session: Annotated[Session, Depends(get_session)],
) -> RecommendResponse:
    """Recommande un modèle à partir des features — le texte n'est traité
    qu'EN MÉMOIRE, et seulement triple verrou ouvert (R6, spec §3).

    RÈGLE n°1 : `prompt_text`, s'il est fourni, n'est JAMAIS stocké ni loggé.
    TRIPLE VERROU (§3) : il n'atteint le routeur que si l'environnement
    (`SOBRIO_EMBED_STAGE2="1"`), la politique de l'org (`router_version ==
    "embed_v0"` ET `send_prompt_text == true`) ET la requête (texte présent)
    l'ouvrent SIMULTANÉMENT. Sinon, il est DÉTRUIT dès la première ligne —
    « REFUS de traiter le texte » silencieux : l'étage 1 seul répond,
    réponse 200 contractuelle normale.
    """
    # TRIPLE VERROU (§3.3) : extraction gardée, puis destruction immédiate —
    # `body.prompt_text` n'est plus JAMAIS relu ensuite (chemin « verrous
    # fermés » = le `del` inconditionnel historique).
    prompt_text = body.prompt_text if _stage2_unlocked(org.policy_json) else None
    del body.prompt_text

    # Adaptateur transitoire features -> signals (RFC-0001) ; routeur
    # effectif résolu par org (policy_json.router_version — chantier R1).
    # Le texte, s'il subsiste, transite par les signaux EN MÉMOIRE SEULEMENT
    # (verrou de sérialisation `PromptSignals.__reduce__`, R6 Lot 1).
    signals = features_to_signals(body.features, prompt_text=prompt_text)
    decision = router_for_org(org.policy_json).decide(signals)
    del prompt_text
    alternatives = build_alternatives(decision.model, body.features)
    impact = build_impact_estimate(decision.model, body.features)
    reco_id = uuid4()

    # INSERT réel : features_json = UNIQUEMENT les features du contrat —
    # JAMAIS prompt_text ni aucun texte libre (règle n°1).
    # final_model / followed restent NULL jusqu'à la télémétrie.
    session.execute(
        text(
            """
            INSERT INTO events_reco (
              reco_id, org_id, ts, surface, features_json, recommended_model,
              final_model, followed, confidence, rule,
              impact_wh_min, impact_wh_max, cost_eur_min, cost_eur_max
            ) VALUES (
              :reco_id, :org_id, :ts, :surface, CAST(:features AS jsonb), :model,
              NULL, NULL, :confidence, :rule,
              :wh_min, :wh_max, :ceur_min, :ceur_max
            )
            """
        ),
        {
            "reco_id": str(reco_id),
            "org_id": org.org_id,
            "ts": datetime.now(tz=UTC),
            "surface": body.surface,
            "features": json.dumps(body.features.model_dump()),
            "model": decision.model,
            "confidence": decision.confidence,
            "rule": decision.rule,
            "wh_min": impact.energy_wh_min,
            "wh_max": impact.energy_wh_max,
            "ceur_min": impact.cost_eur_min,
            "ceur_max": impact.cost_eur_max,
        },
    )
    session.commit()

    # Log structuré SANS contenu : identifiants et décision uniquement.
    logger.info(
        "recommandation émise",
        extra={"org_id": org.org_id, "reco_id": str(reco_id), "rule": decision.rule},
    )

    return RecommendResponse(
        reco_id=reco_id,
        recommended_model=decision.model,
        confidence=decision.confidence,
        rule=decision.rule,
        alternatives=alternatives,
        impact_estimate=impact,
        budget=None,  # TODO(LotB) : budgets d'équipe depuis policy_json + agrégats.
    )


@router.post("/telemetry/reco_event", status_code=204)
def record_reco_event(
    body: RecoEvent,
    org: Annotated[Org, Depends(get_current_org)],
    session: Annotated[Session, Depends(get_session)],
) -> Response:
    """Enregistre la suite donnée à une recommandation (schéma STRICT).

    Tout champ inattendu ⇒ 422 via `RecoEvent` (extra="forbid") : garde-fou
    anti-fuite, règle n°1. final_model = overridden_to si dérogation, sinon
    le modèle recommandé.
    """
    result = session.execute(
        text(
            """
            UPDATE events_reco
            SET followed = :followed,
                final_model = COALESCE(:overridden_to, recommended_model)
            WHERE reco_id = :reco_id AND org_id = :org_id
            """
        ),
        {
            "followed": body.followed,
            "overridden_to": body.overridden_to,
            "reco_id": str(body.reco_id),
            "org_id": org.org_id,
        },
    )
    if result.rowcount == 0:
        session.rollback()
        raise HTTPException(status_code=404, detail="reco_id inconnu")
    session.commit()
    return Response(status_code=204)


@router.get("/extension/config", response_model=ExtensionConfig)
def get_extension_config(
    org_param: Annotated[str, Query(alias="org")],
    org: Annotated[Org, Depends(get_current_org)],
) -> ExtensionConfig:
    """Configuration de l'extension : défauts sûrs fusionnés avec policy_json.

    404 si l'org demandée n'est pas celle du token (pas d'énumération
    d'organisations). `send_prompt_text` est false PAR CONTRAT : l'envoi du
    texte est un opt-in explicite de l'organisation.
    """
    if org_param != org.org_id:
        raise HTTPException(status_code=404, detail="Organisation inconnue")

    defaults: dict = {
        "enabled": True,
        "mode": "equilibre",
        "models_visible": visible_model_ids(),
        # RFC-0003 : défauts sûrs (one_click, seuil 0,75) — surchargables par
        # policy_json (ex. assist_mode=guide comme kill-switch prudence CGU).
        "assist_mode": "one_click",
        "auto_confidence_threshold": 0.75,
        "send_prompt_text": False,  # défaut PAR CONTRAT — opt-in explicite.
        "messages": {"fr": _DEFAULT_MESSAGES_FR},
        "min_extension_version": "0.1.0",
    }
    # Fusion superficielle : policy_json prime sur les défauts, mais seules
    # les clés du contrat sont retenues (le schéma strict rejetterait le reste).
    # TODO(LotB) : fusion fine (messages par langue, politique par équipe).
    # policy_json est censé être un objet JSON, mais on ne suppose rien (règle 3) :
    # un tableau/scalaire mal saisi ne doit pas lever AttributeError → 500.
    policy = org.policy_json if isinstance(org.policy_json, dict) else {}
    overrides = {key: value for key, value in policy.items() if key in ExtensionConfig.model_fields}
    # Robustesse (règle 3) : un policy_json mal formé ne doit JAMAIS produire un
    # 500. On assainit CLÉ PAR CLÉ — chaque override valide est retenu, seule la
    # valeur fautive est écartée. Ainsi un assist_mode=guide (kill-switch
    # prudence CGU) est PRÉSERVÉ même si un auto_confidence_threshold voisin est
    # hors bornes (sinon tout jeter réactiverait silencieusement la bascule).
    safe: dict = {}
    for key, value in overrides.items():
        try:
            ExtensionConfig(**{**defaults, **safe, key: value})
        except ValidationError:
            continue  # override fautif ignoré, les autres conservés
        safe[key] = value
    return ExtensionConfig(**{**defaults, **safe})
