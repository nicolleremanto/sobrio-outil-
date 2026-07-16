"""Normalisation des réponses Anthropic vers les lignes `usage_daily` du schéma.

Source de vérité : `contracts/db_schema.sql`. Aucun champ hors schéma.

Règle n°1 encodée ici : les emails de l'API Analytics ne sortent JAMAIS de ce
module en clair — `pseudonymize()` produit un hash salé, et refuse de tourner
sans sel (`PSEUDONYM_SALT`).

Note d'implémentation (idempotence) : la contrainte UNIQUE de `usage_daily`
inclut des colonnes optionnelles (workspace_id, api_key_id, user_pseudonym,
product). Or Postgres considère les NULL comme distincts dans un index UNIQUE :
des NULL y casseraient `ON CONFLICT DO NOTHING`, donc l'idempotence du sync.
On émet donc la sentinelle '' (« non applicable ») au lieu de NULL pour ces
colonnes.
"""

from __future__ import annotations

import hashlib
import os
from datetime import date, datetime
from typing import Any

# Sources autorisées par le schéma (commentaire de usage_daily.source).
SOURCE_ADMIN = "anthropic_admin"
SOURCE_ANALYTICS = "anthropic_analytics"

# Mapping noms de modèles Anthropic -> ids du catalogue (contracts/model_catalog.yaml).
# TODO(LotC) : table de mapping complète (alias datés type claude-sonnet-4-6-20260115,
# snapshots, modèles legacy) + stratégie pour les modèles inconnus (quarantaine ?).
MODEL_NAME_MAP: dict[str, str] = {
    "claude-haiku-4-5": "haiku-4-5",
    "claude-sonnet-4-6": "sonnet-4-6",
    "claude-opus-4-8": "opus-4-8",
}


class UnknownModelError(KeyError):
    """Nom de modèle Anthropic absent de la table de mapping."""


class MissingSaltError(RuntimeError):
    """`PSEUDONYM_SALT` absent : refus de manipuler des emails (règle n°1)."""


def map_model(anthropic_name: str) -> str:
    """Traduit un nom de modèle Anthropic vers l'id du catalogue Sobrio."""
    try:
        return MODEL_NAME_MAP[anthropic_name]
    except KeyError:
        raise UnknownModelError(
            f"Modèle Anthropic inconnu du mapping : {anthropic_name!r}. "
            "Compléter MODEL_NAME_MAP (TODO(LotC))."
        ) from None


def pseudonymize(email: str) -> str:
    """Hash salé d'un email — seule forme autorisée à quitter ce module.

    `sha256(sel + email)` tronqué à 16 hexdigits. Le sel vient de
    `PSEUDONYM_SALT` (environnement) ; en son absence on REFUSE de traiter :
    jamais d'email en clair, ni stocké, ni loggé (règle n°1).
    """
    salt = os.environ.get("PSEUDONYM_SALT", "")
    if not salt:
        raise MissingSaltError(
            "PSEUDONYM_SALT absent de l'environnement : refus de traiter des "
            "emails (règle n°1 — jamais d'identifiant en clair). "
            "Définir la variable (voir .env.example) puis relancer."
        )
    return hashlib.sha256((salt + email).encode()).hexdigest()[:16]


def _bucket_date(bucket: dict[str, Any]) -> date:
    """Date couverte par un bucket journalier (son `starting_at`)."""
    return date.fromisoformat(str(bucket["starting_at"])[:10])


def normalize_usage_buckets(
    buckets: list[dict[str, Any]],
    *,
    org_id: str,
    snapshot_ts: datetime,
) -> list[dict[str, Any]]:
    """Buckets du usage report Messages -> lignes `usage_daily` (source admin).

    Une ligne par résultat (modèle × workspace × clé API × jour). `cost_usd`
    reste None ici — il est enrichi ensuite par `apply_cost_buckets()`.
    """
    rows: list[dict[str, Any]] = []
    for bucket in buckets:
        day = _bucket_date(bucket)
        for result in bucket.get("results", []):
            rows.append(
                {
                    "org_id": org_id,
                    "date": day,
                    "source": SOURCE_ADMIN,
                    "workspace_id": result.get("workspace_id") or "",
                    "api_key_id": result.get("api_key_id") or "",
                    "user_pseudonym": "",  # sentinelle : pas de dimension utilisateur ici
                    "product": "api",
                    "model": map_model(result["model"]),
                    "tokens_in_uncached": int(result.get("uncached_input_tokens", 0)),
                    "tokens_in_cached": int(result.get("cached_input_tokens", 0)),
                    "tokens_cache_write": int(result.get("cache_creation_input_tokens", 0)),
                    "tokens_out": int(result.get("output_tokens", 0)),
                    "cost_usd": None,
                    "snapshot_ts": snapshot_ts,
                }
            )
    return rows


def apply_cost_buckets(
    usage_rows: list[dict[str, Any]],
    cost_buckets: list[dict[str, Any]],
) -> None:
    """Enrichit `cost_usd` des lignes admin depuis le cost report (en place).

    Le cost report est agrégé par (jour, workspace, modèle) ; les lignes d'usage
    sont plus fines (× clé API). Le montant est réparti au prorata du total de
    tokens de chaque ligne. TODO(LotC) : répartition au prorata du coût réel
    (les tokens cache ne coûtent pas le même prix que l'entrée sèche) et
    réconciliation des arrondis avec le total facturé.
    """
    amounts: dict[tuple[date, str, str], float] = {}
    for bucket in cost_buckets:
        day = _bucket_date(bucket)
        for result in bucket.get("results", []):
            if result.get("currency") != "USD":
                # TODO(LotC) : gérer les devises non-USD si Anthropic en émet.
                continue
            key = (day, result.get("workspace_id") or "", map_model(result["model"]))
            amounts[key] = amounts.get(key, 0.0) + float(result["amount"])

    groups: dict[tuple[date, str, str], list[dict[str, Any]]] = {}
    for row in usage_rows:
        if row["source"] != SOURCE_ADMIN:
            continue
        key = (row["date"], row["workspace_id"], row["model"])
        groups.setdefault(key, []).append(row)

    def _weight(row: dict[str, Any]) -> int:
        return (
            row["tokens_in_uncached"]
            + row["tokens_in_cached"]
            + row["tokens_cache_write"]
            + row["tokens_out"]
        )

    for key, rows in groups.items():
        amount = amounts.get(key)
        if amount is None:
            continue
        total_weight = sum(_weight(r) for r in rows)
        if total_weight <= 0:
            continue
        for row in rows:
            row["cost_usd"] = round(amount * _weight(row) / total_weight, 4)


def normalize_analytics_rows(
    analytics_rows: list[dict[str, Any]],
    *,
    org_id: str,
    snapshot_ts: datetime,
) -> list[dict[str, Any]]:
    """Lignes Analytics (par utilisateur) -> lignes `usage_daily` (source analytics).

    L'email est pseudonymisé AVANT toute autre chose et n'est jamais copié dans
    la ligne de sortie (règle n°1).
    """
    rows: list[dict[str, Any]] = []
    for item in analytics_rows:
        pseudonym = pseudonymize(item["user_email"])
        rows.append(
            {
                "org_id": org_id,
                "date": date.fromisoformat(str(item["date"])[:10]),
                "source": SOURCE_ANALYTICS,
                "workspace_id": "",  # sentinelle : pas de dimension workspace ici
                "api_key_id": "",  # sentinelle : pas de clé API côté Analytics
                "user_pseudonym": pseudonym,
                "product": item["product"],
                "model": map_model(item["model"]),
                "tokens_in_uncached": int(item.get("input_tokens", 0)),
                "tokens_in_cached": 0,
                "tokens_cache_write": 0,
                "tokens_out": int(item.get("output_tokens", 0)),
                "cost_usd": None,
                "snapshot_ts": snapshot_ts,
            }
        )
    return rows
