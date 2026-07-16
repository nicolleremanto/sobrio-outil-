"""Estimation d'énergie par modèle, lue depuis contracts/model_catalog.yaml.

TODO(LotD) : recalibrer les facteurs (EcoLogits + littérature publique) et
étendre aux tokens d'entrée si une source fiable existe.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

from .models import Range

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CATALOG = _REPO_ROOT / "contracts" / "model_catalog.yaml"


def _catalog_path() -> str:
    return os.environ.get("MODEL_CATALOG_PATH", str(_DEFAULT_CATALOG))


@lru_cache(maxsize=4)
def _load_catalog(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def catalog_version() -> str:
    """Version du catalogue — à tracer dans monthly_agg et le rapport."""
    return str(_load_catalog(_catalog_path())["version"])


def estimate(model_id: str, tokens_out: int) -> Range:
    """Énergie estimée (Wh) pour `tokens_out` tokens de sortie du modèle donné.

    Retourne TOUJOURS un `Range` (min–max, périmètre, source) — jamais un
    scalaire (règle n°3, test structurel dédié).
    """
    catalog = _load_catalog(_catalog_path())
    for model in catalog["models"]:
        if model["id"] == model_id:
            wh = model["impact"]["wh_per_ktok_out"]
            ktok = tokens_out / 1000.0
            return Range(
                min=wh["min"] * ktok,
                max=wh["max"] * ktok,
                scope=model["impact"]["scope"],
                source=model["impact"]["source"],
            )
    raise KeyError(f"Modèle inconnu du catalogue : {model_id}")
