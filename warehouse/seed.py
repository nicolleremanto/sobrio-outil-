"""Seed DÉTERMINISTE et IDEMPOTENT de l'entrepôt Sobrio (Lot D).

Génère les données de démonstration :
- l'organisation ``demo`` (token haché SHA-256, politique par défaut) ;
- 60 jours d'usage quotidien du 2026-05-12 au 2026-07-10 (usage_daily) ;
- ~300 événements de recommandation répartis sur juin 2026 (events_reco).

Règles non négociables encodées ici :
- n°1 : AUCUN contenu de prompt — ``features_json`` ne contient que les
  mesures/indicateurs du contrat (schéma ``Features`` de contracts/openapi.yaml)
  et ``user_pseudonym`` est un hash salé, jamais un e-mail en clair.
- n°3 : toute fourchette d'impact vient de ``sobrio_impact.estimate`` (Range),
  jamais un scalaire, jamais d'équivalents grand public.
- n°6 : pas de temps réel — ``snapshot_ts`` FIXE (2026-07-11T03:00:00Z),
  versionnage par snapshot.

Déterminisme : ``random.Random(42)`` + UUID dérivés du même générateur.
Idempotence : ``ON CONFLICT DO NOTHING`` partout (relancer ne change rien).

Usage (depuis la racine du repo) :
    .venv/bin/python warehouse/seed.py --org demo [--database-url URL]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import sqlalchemy as sa
import yaml

from sobrio_impact import estimate

_REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_DATABASE_URL = "postgresql+psycopg://sobrio:sobrio_dev_password@localhost:5432/sobrio"

# TODO(LotB) : brancher une vraie source de taux de change (ex. BCE) au lieu
# d'une constante de développement.
EUR_PER_USD = 0.92

# Fenêtre du seed : 60 jours inclus (2026-05-12 → 2026-07-10), mois de démo
# canonique 2026-06 entièrement couvert.
SEED_START = date(2026, 5, 12)
SEED_END = date(2026, 7, 10)

# Règle n°6 : snapshot FIXE — l'usage n'est jamais « temps réel ».
SNAPSHOT_TS = datetime(2026, 7, 11, 3, 0, 0, tzinfo=timezone.utc)

EVENTS_MONTH_START = datetime(2026, 6, 1, tzinfo=timezone.utc)
EVENTS_MONTH_SECONDS = 30 * 24 * 3600  # juin 2026 = 30 jours
N_EVENTS = 300

# Topologie de démonstration : 2 workspaces, 4 clés API, 3 produits.
API_KEYS = [
    {"api_key_id": "apikey_01", "workspace_id": "wrkspc_alpha", "product": "api"},
    {"api_key_id": "apikey_02", "workspace_id": "wrkspc_alpha", "product": "claude_code"},
    {"api_key_id": "apikey_03", "workspace_id": "wrkspc_beta", "product": "claude_ai"},
    {"api_key_id": "apikey_04", "workspace_id": "wrkspc_beta", "product": "api"},
]

# Volumes de sortie plausibles par modèle (tokens/jour/clé) — ids du CATALOGUE.
TOKENS_OUT_RANGES = {
    "haiku-4-5": (20_000, 120_000),
    "sonnet-4-6": (10_000, 80_000),
    "opus-4-8": (2_000, 30_000),
}

# Routeur v0 (heuristiques explicables) : scénario -> (modèle recommandé,
# poids de tirage, bornes de confiance, tokens de sortie estimés par appel).
SCENARIOS = [
    ("short_simple", "haiku-4-5", 0.5, (0.75, 0.95), (150, 400)),
    ("code_task", "sonnet-4-6", 0.3, (0.65, 0.90), (300, 1500)),
    ("complex_task", "opus-4-8", 0.2, (0.60, 0.85), (500, 2500)),
]

# Politique d'organisation par défaut — cohérente avec ExtensionConfig
# (contracts/openapi.yaml) : envoi du texte de prompt DÉSACTIVÉ par défaut.
POLICY_JSON_DEFAULT = {
    "mode": "equilibre",
    "send_prompt_text": False,
    "models_visible": ["haiku-4-5", "sonnet-4-6", "opus-4-8"],
}

_USAGE_INSERT_SQL = sa.text(
    """
    INSERT INTO usage_daily (
        org_id, date, source, workspace_id, api_key_id, user_pseudonym, product,
        model, tokens_in_uncached, tokens_in_cached, tokens_cache_write,
        tokens_out, cost_usd, snapshot_ts
    ) VALUES (
        :org_id, :date, :source, :workspace_id, :api_key_id, :user_pseudonym,
        :product, :model, :tokens_in_uncached, :tokens_in_cached,
        :tokens_cache_write, :tokens_out, :cost_usd, :snapshot_ts
    )
    ON CONFLICT (org_id, date, source, workspace_id, api_key_id, user_pseudonym,
                 product, model, snapshot_ts)
    DO NOTHING
    """
)

_EVENT_INSERT_SQL = sa.text(
    """
    INSERT INTO events_reco (
        reco_id, org_id, ts, surface, features_json, recommended_model,
        final_model, followed, confidence, rule,
        impact_wh_min, impact_wh_max, cost_eur_min, cost_eur_max
    ) VALUES (
        :reco_id, :org_id, :ts, :surface, :features_json, :recommended_model,
        :final_model, :followed, :confidence, :rule,
        :impact_wh_min, :impact_wh_max, :cost_eur_min, :cost_eur_max
    )
    ON CONFLICT (reco_id) DO NOTHING
    """
)


def _load_prices() -> dict[str, tuple[float, float]]:
    """Prix USD/Mtok (entrée, sortie) par modèle, depuis le catalogue (source de vérité)."""
    path = os.environ.get(
        "MODEL_CATALOG_PATH", str(_REPO_ROOT / "contracts" / "model_catalog.yaml")
    )
    with open(path, encoding="utf-8") as fh:
        catalog = yaml.safe_load(fh)
    return {
        m["id"]: (float(m["price_in_usd_mtok"]), float(m["price_out_usd_mtok"]))
        for m in catalog["models"]
    }


def _pseudonym(label: str) -> str:
    """Hash salé d'un identifiant interne (règle n°1 : jamais d'identité en clair)."""
    salt = os.environ.get("PSEUDONYM_SALT", "dev-salt-change-me")
    return hashlib.sha256(f"{salt}:{label}".encode()).hexdigest()[:16]


def seed_org(conn: sa.Connection, org_id: str) -> None:
    """Insère l'organisation de démo (idempotent)."""
    token = os.environ.get("DEMO_ORG_TOKEN", "demo-token-not-a-secret")
    conn.execute(
        sa.text(
            """
            INSERT INTO orgs (org_id, name, api_token_hash, policy_json)
            VALUES (:org_id, :name, :api_token_hash, :policy_json)
            ON CONFLICT (org_id) DO NOTHING
            """
        ),
        {
            "org_id": org_id,
            "name": "Organisation de démonstration Sobrio",
            "api_token_hash": hashlib.sha256(token.encode()).hexdigest(),
            "policy_json": json.dumps(POLICY_JSON_DEFAULT),
        },
    )


def _usage_rows(
    org_id: str, rng: random.Random, prices: dict[str, tuple[float, float]]
) -> list[dict]:
    """60 jours × 4 clés × 3 modèles d'usage quotidien plausible."""
    rows: list[dict] = []
    day = SEED_START
    while day <= SEED_END:
        for key in API_KEYS:
            for model, (lo, hi) in TOKENS_OUT_RANGES.items():
                tokens_out = rng.randint(lo, hi)
                tokens_in_uncached = int(tokens_out * rng.uniform(1.5, 4.0))
                tokens_in_cached = int(tokens_in_uncached * rng.uniform(0.0, 2.0))
                tokens_cache_write = int(tokens_in_cached * rng.uniform(0.0, 0.3))
                price_in, price_out = prices[model]
                # Coût depuis les prix du catalogue (entrée non cachée + sortie).
                # TODO(LotC) : tarification réelle du cache (lecture/écriture)
                # côté connecteur Usage & Cost.
                cost_usd = round(
                    (tokens_in_uncached * price_in + tokens_out * price_out) / 1e6, 4
                )
                rows.append(
                    {
                        "org_id": org_id,
                        "date": day,
                        "source": "anthropic_admin",
                        "workspace_id": key["workspace_id"],
                        "api_key_id": key["api_key_id"],
                        "user_pseudonym": _pseudonym(f"seed-user-{key['api_key_id']}"),
                        "product": key["product"],
                        "model": model,
                        "tokens_in_uncached": tokens_in_uncached,
                        "tokens_in_cached": tokens_in_cached,
                        "tokens_cache_write": tokens_cache_write,
                        "tokens_out": tokens_out,
                        "cost_usd": cost_usd,
                        "snapshot_ts": SNAPSHOT_TS,
                    }
                )
        day += timedelta(days=1)
    return rows


def _features(scenario: str, rng: random.Random) -> dict:
    """Features plausibles SANS AUCUN TEXTE (schéma Features du contrat, règle n°1)."""
    if scenario == "short_simple":
        char_len = rng.randint(20, 280)
        has_code = False
        has_attachment_hint = False
        keyword_flags = rng.choice([[], ["resume"], ["traduction"]])
    elif scenario == "code_task":
        char_len = rng.randint(200, 4000)
        has_code = True
        has_attachment_hint = False
        keyword_flags = ["code"]
    else:  # complex_task
        char_len = rng.randint(800, 12000)
        has_code = rng.random() < 0.2
        has_attachment_hint = rng.random() < 0.5
        keyword_flags = rng.choice([["analyse"], ["contrat"], ["contrat", "analyse"]])
    return {
        "char_len": char_len,
        "token_est": max(1, char_len // 4),
        "lang": rng.choices(["fr", "en", "other"], weights=[0.70, 0.25, 0.05])[0],
        "has_code": has_code,
        "has_attachment_hint": has_attachment_hint,
        "keyword_flags": keyword_flags,
    }


def _event_rows(
    org_id: str, rng: random.Random, prices: dict[str, tuple[float, float]]
) -> list[dict]:
    """~300 événements de recommandation répartis sur juin 2026."""
    all_models = list(TOKENS_OUT_RANGES)
    weights = [s[2] for s in SCENARIOS]
    rows: list[dict] = []
    for _ in range(N_EVENTS):
        scenario, recommended, _w, conf_bounds, out_bounds = rng.choices(
            SCENARIOS, weights=weights
        )[0]
        features = _features(scenario, rng)
        ts = EVENTS_MONTH_START + timedelta(seconds=rng.randrange(EVENTS_MONTH_SECONDS))
        followed = rng.random() < 0.70
        final_model = (
            recommended if followed else rng.choice([m for m in all_models if m != recommended])
        )
        est_out = rng.randint(*out_bounds)

        # Règle n°3 : la fourchette d'énergie vient du module d'impact (Range).
        impact = estimate(recommended, est_out)

        # Fourchette de coût par appel : incertitude sur les tokens de sortie.
        price_in, price_out = prices[recommended]
        out_lo, out_hi = int(est_out * 0.6), int(est_out * 1.6)
        tok_in = features["token_est"]
        cost_eur_min = round((tok_in * price_in + out_lo * price_out) / 1e6 * EUR_PER_USD, 6)
        cost_eur_max = round((tok_in * price_in + out_hi * price_out) / 1e6 * EUR_PER_USD, 6)

        rows.append(
            {
                # UUID dérivé du générateur seedé -> déterministe ET idempotent.
                "reco_id": str(uuid.UUID(int=rng.getrandbits(128), version=4)),
                "org_id": org_id,
                "ts": ts,
                "surface": "claude_web",
                "features_json": json.dumps(features),
                "recommended_model": recommended,
                "final_model": final_model,
                "followed": followed,
                "confidence": round(rng.uniform(*conf_bounds), 3),
                "rule": f"heuristic:{scenario}",
                "impact_wh_min": impact.min,
                "impact_wh_max": impact.max,
                "cost_eur_min": cost_eur_min,
                "cost_eur_max": cost_eur_max,
            }
        )
    return rows


def _counts(conn: sa.Connection, org_id: str) -> tuple[int, int]:
    usage = conn.execute(
        sa.text("SELECT count(*) FROM usage_daily WHERE org_id = :o"), {"o": org_id}
    ).scalar_one()
    events = conn.execute(
        sa.text("SELECT count(*) FROM events_reco WHERE org_id = :o"), {"o": org_id}
    ).scalar_one()
    return usage, events


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Seed déterministe et idempotent de l'entrepôt Sobrio (Lot D)."
    )
    parser.add_argument("--org", default="demo", help="Identifiant de l'organisation (défaut : demo)")
    parser.add_argument(
        "--database-url",
        default=None,
        help="URL Postgres (défaut : env DATABASE_URL, sinon convention locale)",
    )
    args = parser.parse_args(argv)

    url = args.database_url or os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
    engine = sa.create_engine(url)
    rng = random.Random(42)  # déterminisme total
    prices = _load_prices()

    with engine.begin() as conn:
        seed_org(conn, args.org)
        conn.execute(_USAGE_INSERT_SQL, _usage_rows(args.org, rng, prices))
        conn.execute(_EVENT_INSERT_SQL, _event_rows(args.org, rng, prices))
        usage_count, events_count = _counts(conn, args.org)
    engine.dispose()

    # Aucun secret ni contenu dans la sortie : uniquement des volumes.
    print(
        f"Seed terminé pour org={args.org} : "
        f"{usage_count} lignes usage_daily, {events_count} events_reco."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
