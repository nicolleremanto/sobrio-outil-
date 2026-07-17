"""Modèles pydantic v2 FIDÈLES au contrat contracts/openapi.yaml (v1.0, figé).

Tout changement ici exige une RFC (docs/rfc/) + entrée dans
contracts/CHANGELOG.md (règle n°7).

`extra="forbid"` PARTOUT : le contrat déclare `additionalProperties: false`
sur chaque schéma — tout champ inconnu ⇒ 422.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Features(BaseModel):
    """Caractéristiques du prompt calculées LOCALEMENT par l'extension.

    Aucun contenu textuel — uniquement des mesures et des indicateurs
    (règle n°1 : jamais de contenu de prompt stocké ni loggé).
    """

    model_config = ConfigDict(extra="forbid")

    char_len: int = Field(ge=0)
    token_est: int = Field(ge=0)
    lang: Literal["fr", "en", "other"]
    has_code: bool
    has_attachment_hint: bool
    keyword_flags: list[Literal["contrat", "analyse", "code", "resume", "traduction"]]


class RecommendRequest(BaseModel):
    """Requête de recommandation (POST /v1/recommend)."""

    model_config = ConfigDict(extra="forbid")

    org_id: str
    surface: Literal["claude_web"]
    features: Features
    # OPTIONNEL (v1 uniquement), si la politique de l'org l'autorise
    # (`send_prompt_text`). Traité en mémoire, JAMAIS stocké ni loggé (règle n°1).
    prompt_text: str | None = None


class Alternative(BaseModel):
    """Modèle alternatif avec delta de coût en fourchette (EUR/appel)."""

    model_config = ConfigDict(extra="forbid")

    model: str
    delta_cost_eur_per_call_min: float
    delta_cost_eur_per_call_max: float


class ImpactEstimate(BaseModel):
    """Fourchettes uniquement — jamais de valeur unique (règle n°3)."""

    model_config = ConfigDict(extra="forbid")

    energy_wh_min: float
    energy_wh_max: float
    cost_eur_min: float
    cost_eur_max: float


class Budget(BaseModel):
    """Budget d'équipe (nullable dans la réponse)."""

    model_config = ConfigDict(extra="forbid")

    team_label: str
    pct_used: float = Field(ge=0)


class RecommendResponse(BaseModel):
    """Réponse de recommandation — explicable (`rule`) et chiffrée en fourchettes."""

    model_config = ConfigDict(extra="forbid")

    reco_id: UUID
    recommended_model: str
    confidence: float = Field(ge=0, le=1)
    rule: str
    alternatives: list[Alternative]
    impact_estimate: ImpactEstimate
    budget: Budget | None


class RecoEvent(BaseModel):
    """Télémétrie de suite donnée à une recommandation (POST /v1/telemetry/reco_event).

    Schéma STRICT : `extra="forbid"` ⇒ tout champ supplémentaire (ex. un
    `prompt_text` qui s'y glisserait) est rejeté en 422. C'est le GARDE-FOU
    ANTI-FUITE de contenu (règle n°1) — aucun texte de prompt ne peut
    transiter par cet endpoint.
    """

    model_config = ConfigDict(extra="forbid")

    reco_id: UUID
    followed: bool
    overridden_to: str | None
    ts: datetime


class Messages(BaseModel):
    """Libellés localisés de l'extension. `fr` est requis par le contrat."""

    model_config = ConfigDict(extra="forbid")

    fr: dict[str, str]


class ExtensionConfig(BaseModel):
    """Configuration à distance de l'extension (kill-switch inclus)."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool
    mode: Literal["eco", "equilibre", "qualite"]
    models_visible: list[str]
    # RFC-0003 : niveau d'assistance à la bascule (optionnels, compat ascendante).
    # guide = aucun contact page (repli / kill-switch prudence CGU).
    assist_mode: Literal["auto", "one_click", "guide"] = "one_click"
    auto_confidence_threshold: float = Field(default=0.75, ge=0, le=1)
    # false PAR CONTRAT : l'envoi du texte est un opt-in explicite de l'org.
    send_prompt_text: bool = False
    messages: Messages
    min_extension_version: str
