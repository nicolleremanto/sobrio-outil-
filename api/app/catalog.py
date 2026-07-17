"""Lecture du catalogue de modèles (contracts/model_catalog.yaml).

Source de vérité pour les ids de modèles et les prix. Le chemin est
surchargeable via MODEL_CATALOG_PATH (cf. docker-compose.dev.yml).
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

# api/app/catalog.py -> app -> api -> racine du repo
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CATALOG = _REPO_ROOT / "contracts" / "model_catalog.yaml"

# Conversion coût : prix catalogue en USD.
# TODO(LotB) : brancher une vraie source de taux de change (BCE), figée par mois.
EUR_PER_USD = 0.92


def _catalog_path() -> str:
    return os.environ.get("MODEL_CATALOG_PATH", str(_DEFAULT_CATALOG))


@lru_cache(maxsize=4)
def _load_catalog(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def model_ids() -> list[str]:
    """Ids des modèles du catalogue, dans l'ordre du fichier (chiffrage/impact)."""
    return [m["id"] for m in _load_catalog(_catalog_path())["models"]]


def visible_model_ids() -> list[str]:
    """Ids proposés à l'utilisateur (dérogation) — exclut `visible: false`
    (ex. Claude Fable 5, gardé pour le chiffrage mais non exposé par sobriété)."""
    return [m["id"] for m in _load_catalog(_catalog_path())["models"] if m.get("visible", True)]


def model_prices(model_id: str) -> tuple[float, float]:
    """(prix entrée, prix sortie) en USD par Mtok pour `model_id`."""
    for model in _load_catalog(_catalog_path())["models"]:
        if model["id"] == model_id:
            return float(model["price_in_usd_mtok"]), float(model["price_out_usd_mtok"])
    raise KeyError(f"Modèle inconnu du catalogue : {model_id}")
