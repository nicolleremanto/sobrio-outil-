"""Clients de l'API d'administration Anthropic — LECTURE SEULE.

Deux implémentations de la MÊME interface :
- `AnthropicAdminClient` : client réel (httpx), clé lue depuis `ANTHROPIC_ADMIN_KEY`
  (environnement UNIQUEMENT — règle n°5 : jamais commitée, jamais loggée) ;
- `FixturesClient` : rejoue les réponses JSON de `fixtures/anthropic/` (pagination
  incluse), pour développer et tester SANS réseau et SANS clé.

Chaque méthode publique retourne un itérateur sur les éléments de `data` de toutes
les pages, la pagination `has_more`/`next_page` étant absorbée par le client.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx

_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURES_DIR = _REPO_ROOT / "fixtures" / "anthropic"

# TODO(LotC) : vérifier la version d'API exigée par les endpoints d'administration.
ANTHROPIC_VERSION = "2023-06-01"
ANTHROPIC_BASE_URL = "https://api.anthropic.com"


class MissingAdminKeyError(RuntimeError):
    """`ANTHROPIC_ADMIN_KEY` absente de l'environnement (règle n°5)."""


class AnthropicAdminClient:
    """Client HTTP réel, strictement en lecture (uniquement des GET).

    La clé d'administration est un ACTIF CRITIQUE : Anthropic n'offre pas de
    permission fine, cette clé lit TOUT le compte. Elle est lue depuis
    l'environnement au moment de la construction, gardée en attribut « privé »
    et jamais exposée : ni dans `__repr__`, ni dans les logs, ni dans les
    messages d'erreur. Procédure de rotation : voir `connector/README.md`.
    """

    def __init__(
        self,
        *,
        base_url: str = ANTHROPIC_BASE_URL,
        timeout: float = 30.0,
    ) -> None:
        api_key = os.environ.get("ANTHROPIC_ADMIN_KEY", "")
        if not api_key:
            raise MissingAdminKeyError(
                "ANTHROPIC_ADMIN_KEY absente de l'environnement. "
                "En développement, utiliser FixturesClient (mode --fixtures) : "
                "aucun réseau, aucune clé requise."
            )
        self._base_url = base_url
        self._http = httpx.Client(
            base_url=base_url,
            headers={
                "x-api-key": api_key,
                "anthropic-version": ANTHROPIC_VERSION,
            },
            timeout=timeout,
        )

    def __repr__(self) -> str:
        # Règle n°5 : la clé n'apparaît JAMAIS, même masquée partiellement.
        return f"AnthropicAdminClient(base_url={self._base_url!r}, api_key='***')"

    def close(self) -> None:
        self._http.close()

    # -- Pagination générique ------------------------------------------------

    def _paginate(self, path: str, params: dict[str, Any]) -> Iterator[dict[str, Any]]:
        """Itère sur les éléments de `data` de toutes les pages (`has_more`/`next_page`).

        TODO(LotC) : retry/backoff exponentiel (429, 5xx), respect des en-têtes
        de rate-limit, journalisation des pages SANS jamais logger les en-têtes.
        """
        page_token: str | None = None
        while True:
            query = dict(params)
            if page_token is not None:
                query["page"] = page_token
            response = self._http.get(path, params=query)
            response.raise_for_status()
            payload = response.json()
            yield from payload.get("data", [])
            if not payload.get("has_more"):
                return
            page_token = payload.get("next_page")
            if not page_token:
                return

    # -- Endpoints (lecture seule) --------------------------------------------

    def usage_report_messages(self, **params: Any) -> Iterator[dict[str, Any]]:
        """Buckets d'usage Messages (GET /v1/organizations/usage_report/messages).

        TODO(LotC) : paramètres exacts (starting_at, ending_at, bucket_width=1d,
        group_by=[model, workspace_id, api_key_id]) et validation de la réponse.
        """
        return self._paginate("/v1/organizations/usage_report/messages", params)

    def cost_report(self, **params: Any) -> Iterator[dict[str, Any]]:
        """Buckets de coût (GET /v1/organizations/cost_report).

        TODO(LotC) : paramètres exacts (fenêtre, group_by) et devises multiples.
        """
        return self._paginate("/v1/organizations/cost_report", params)

    def analytics_by_user(self, **params: Any) -> Iterator[dict[str, Any]]:
        """Lignes journalières par utilisateur — API Analytics (plan Enterprise).

        TODO(LotC) : endpoint et paramètres exacts de l'API Analytics ; dégrader
        proprement (message clair) si le plan de l'organisation ne l'inclut pas.
        """
        return self._paginate("/v1/organizations/usage_report/claude_analytics", params)


class FixturesClient:
    """Même interface que `AnthropicAdminClient`, sans réseau ni clé.

    Lit `fixtures/anthropic/<prefixe>_pN.json` et REJOUE la pagination : la
    page suivante n'est lue que si la page courante annonce `has_more=true`
    avec un `next_page` non nul — le même contrat que le client réel.
    """

    def __init__(self, fixtures_dir: Path | str | None = None) -> None:
        self._dir = Path(fixtures_dir) if fixtures_dir is not None else DEFAULT_FIXTURES_DIR

    def __repr__(self) -> str:
        return f"FixturesClient(fixtures_dir={str(self._dir)!r})"

    def close(self) -> None:  # symétrie d'interface avec le client réel
        return None

    def _paginate(self, prefix: str) -> Iterator[dict[str, Any]]:
        page_num = 1
        while True:
            path = self._dir / f"{prefix}_p{page_num}.json"
            if not path.is_file():
                if page_num == 1:
                    raise FileNotFoundError(f"Fixture absente : {path}")
                raise FileNotFoundError(
                    f"Pagination incohérente : has_more=true mais {path} est absente"
                )
            payload = json.loads(path.read_text(encoding="utf-8"))
            yield from payload.get("data", [])
            if not payload.get("has_more"):
                return
            if not payload.get("next_page"):
                raise ValueError(
                    f"Fixture invalide : has_more=true sans next_page dans {path.name}"
                )
            page_num += 1

    def usage_report_messages(self, **_params: Any) -> Iterator[dict[str, Any]]:
        return self._paginate("usage_report_messages")

    def cost_report(self, **_params: Any) -> Iterator[dict[str, Any]]:
        return self._paginate("cost_report")

    def analytics_by_user(self, **_params: Any) -> Iterator[dict[str, Any]]:
        return self._paginate("analytics_by_user")
