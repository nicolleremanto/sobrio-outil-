"""Connecteur de facturation Sobrio — LECTURE SEULE vers l'API d'administration Anthropic.

Lot C (squelette Lot 0) :
- `client`     : clients HTTP (réel, stub) avec pagination générique ;
- `normalize`  : passage des réponses Anthropic aux lignes `usage_daily` du schéma ;
- `sync`       : fenêtre J-30 glissante versionnée par `snapshot_ts`, ingestion idempotente.

Règles non négociables encodées ici :
- n°1 : jamais d'email en clair — pseudonymisation salée obligatoire (normalize) ;
- n°5 : `ANTHROPIC_ADMIN_KEY` lue depuis l'environnement uniquement, jamais loggée (client) ;
- n°6 : pas de temps réel — fenêtre J-30 re-tirée à chaque run, snapshots versionnés (sync).
"""

from connector.client import AnthropicAdminClient, FixturesClient, MissingAdminKeyError
from connector.normalize import (
    MissingSaltError,
    UnknownModelError,
    map_model,
    normalize_analytics_rows,
    normalize_usage_buckets,
    pseudonymize,
)

__all__ = [
    "AnthropicAdminClient",
    "FixturesClient",
    "MissingAdminKeyError",
    "MissingSaltError",
    "UnknownModelError",
    "map_model",
    "normalize_analytics_rows",
    "normalize_usage_buckets",
    "pseudonymize",
]
