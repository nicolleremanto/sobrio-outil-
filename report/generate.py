"""Génération du rapport mensuel PDF Sobrio — Lot E (squelette Lot 0).

CLI : ``python report/generate.py --org demo --month 2026-06``
(options ``--database-url`` et ``--out`` facultatives).

Principes encodés ici (pas seulement documentés) :
- chaque chiffre du rapport provient d'une requête SQL versionnée dans
  ``report/queries/`` — AUCUN SQL inline dans ce fichier (garde-fou testé
  par ``report/tests/test_report_no_inline_sql.py``) ;
- règle n°3 : tout chiffre d'impact est une fourchette min–max avec
  périmètre — jamais d'équivalents grand public, ni ici ni dans le gabarit ;
- règle n°4 : empreinte totale MESURÉE (connecteur, 100 % de l'usage) et
  économies/empreinte évitée OBTENUES (extension, chat navigateur) restent
  deux blocs distincts dans le gabarit — jamais fusionnés ni comparés ;
- règle n°6 : pas de temps réel — rapport produit à J+10 du mois suivant,
  données réconciliées jusqu'à J+30 (rappelé en pied de page et en annexe).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import UTC, date, datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from sobrio_impact import catalog_version
from sqlalchemy import create_engine, text
from weasyprint import HTML

# Version du code tracée dans le rapport (pied de page + annexe).
# TODO(LotE) : remplacer par `git describe --tags --dirty` au build.
CODE_VERSION = "lot0-bootstrap"

# Conversion indicative USD -> EUR (les prix du catalogue sont en USD).
# TODO(LotE) : brancher une vraie source de taux de change (BCE), datée.
EUR_PER_USD = 0.92

REPORT_DIR = Path(__file__).resolve().parent
QUERIES_DIR = REPORT_DIR / "queries"
TEMPLATES_DIR = REPORT_DIR / "templates"
OUT_DIR = REPORT_DIR / "out"

DEFAULT_DATABASE_URL = "postgresql+psycopg://sobrio:sobrio_dev_password@localhost:5432/sobrio"

_MOIS_FR = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]

# Repère les paramètres nommés SQLAlchemy (":org_id") sans confondre les
# doubles deux-points des casts PostgreSQL ("::jsonb").
_PARAM_RE = re.compile(r"(?<![:\w]):([a-z_]+)")


# ---------------------------------------------------------------------------
# Chargement des requêtes versionnées
# ---------------------------------------------------------------------------

def load_queries() -> dict[str, str]:
    """Charge toutes les requêtes de ``report/queries/`` (nom de fichier -> SQL).

    C'est la SEULE source de SQL du rapport : chaque chiffre affiché doit
    provenir d'un de ces fichiers, avec son en-tête (mesure, périmètre,
    limites).
    """
    queries: dict[str, str] = {}
    for chemin in sorted(QUERIES_DIR.glob("*.sql")):
        queries[chemin.stem] = chemin.read_text(encoding="utf-8")
    if not queries:
        raise SystemExit(f"Aucune requête trouvée dans {QUERIES_DIR}")
    return queries


def _bornes_mois(month: str) -> tuple[date, date]:
    """Convertit « AAAA-MM » en bornes [1er du mois, 1er du mois suivant)."""
    try:
        annee, mois = month.split("-")
        debut = date(int(annee), int(mois), 1)
    except (ValueError, AttributeError) as exc:
        raise SystemExit(
            f"Mois invalide : {month!r} — format attendu AAAA-MM, ex. 2026-06"
        ) from exc
    if debut.month == 12:
        fin = date(debut.year + 1, 1, 1)
    else:
        fin = date(debut.year, debut.month + 1, 1)
    return debut, fin


def _params_pour(sql: str, params: dict) -> dict:
    """Ne transmet à chaque requête que les paramètres qu'elle déclare."""
    noms = set(_PARAM_RE.findall(sql))
    return {cle: valeur for cle, valeur in params.items() if cle in noms}


def run_queries(engine, org_id: str, month: str) -> dict[str, list[dict]]:
    """Exécute toutes les requêtes versionnées et retourne leurs lignes."""
    debut, fin = _bornes_mois(month)
    params = {"org_id": org_id, "month": debut, "month_next": fin}
    resultats: dict[str, list[dict]] = {}
    with engine.connect() as conn:
        for nom, sql in load_queries().items():
            lignes = conn.execute(text(sql), _params_pour(sql, params))
            resultats[nom] = [dict(ligne) for ligne in lignes.mappings()]
    return resultats


# ---------------------------------------------------------------------------
# Construction du contexte de rendu
# ---------------------------------------------------------------------------

def _libelle_mois(month: str) -> str:
    debut, _ = _bornes_mois(month)
    return f"{_MOIS_FR[debut.month - 1]} {debut.year}"


def _f(valeur, defaut: float = 0.0) -> float:
    """Décimal/None -> float, pour un rendu homogène dans le gabarit."""
    return float(valeur) if valeur is not None else defaut


def build_context(
    org_id: str,
    month: str,
    resultats: dict[str, list[dict]],
    generated_at: datetime | None = None,
) -> dict:
    """Assemble le contexte Jinja2 à partir des résultats des requêtes.

    Chaque valeur numérique provient d'un fichier de ``report/queries/`` ;
    ici on ne fait que convertir les types et calculer des présentations
    dérivées (conversion EUR indicative).
    """
    lignes_total = resultats.get("monthly_total") or []
    if not lignes_total:
        raise SystemExit(
            f"monthly_agg est vide pour org='{org_id}' et mois='{month}' : "
            "impossible de produire le rapport. Lancer d'abord l'agrégation "
            "mensuelle (Lot D) — le rapport se produit à J+10 du mois suivant."
        )
    total = lignes_total[0]

    def _premiere(nom: str) -> dict:
        lignes = resultats.get(nom) or []
        return lignes[0] if lignes else {}

    adoption = _premiere("reco_adoption")
    savings = _premiere("reco_savings")
    avoided = _premiere("footprint_avoided")

    cost_usd = _f(total.get("cost_usd"))
    taux = adoption.get("adoption_rate_pct")
    quand = generated_at or datetime.now(UTC)

    return {
        "org_id": org_id,
        "month": month,
        "month_label": _libelle_mois(month),
        "total": {
            "tokens_total": int(total.get("tokens_total") or 0),
            "cost_usd": cost_usd,
            "cost_eur_indicatif": cost_usd * EUR_PER_USD,
            "energy_wh_min": _f(total.get("energy_wh_min")),
            "energy_wh_max": _f(total.get("energy_wh_max")),
        },
        "by_model": [
            {
                "model": ligne.get("model"),
                "tokens_total": int(ligne.get("tokens_total") or 0),
                "cost_usd": _f(ligne.get("cost_usd")),
                "energy_wh_min": _f(ligne.get("energy_wh_min")),
                "energy_wh_max": _f(ligne.get("energy_wh_max")),
            }
            for ligne in resultats.get("by_model") or []
        ],
        "by_workspace": [
            {
                "workspace": ligne.get("workspace"),
                "tokens_total": int(ligne.get("tokens_total") or 0),
                "cost_usd": _f(ligne.get("cost_usd")),
                "energy_wh_min": _f(ligne.get("energy_wh_min")),
                "energy_wh_max": _f(ligne.get("energy_wh_max")),
            }
            for ligne in resultats.get("by_workspace") or []
        ],
        "adoption": {
            "n_events": int(adoption.get("n_events") or 0),
            "n_followed": int(adoption.get("n_followed") or 0),
            "n_decided": int(adoption.get("n_decided") or 0),
            "rate_pct": _f(taux) if taux is not None else None,
        },
        "savings": {
            "n_followed": int(savings.get("n_followed") or 0),
            "eur_min": _f(savings.get("savings_eur_min")),
            "eur_max": _f(savings.get("savings_eur_max")),
        },
        "avoided": {
            "n_followed": int(avoided.get("n_followed") or 0),
            "wh_min": _f(avoided.get("avoided_wh_min")),
            "wh_max": _f(avoided.get("avoided_wh_max")),
        },
        "meta": {
            # Version du catalogue tracée par l'agrégation (monthly_agg)…
            "catalog_version_agg": total.get("catalog_version") or "inconnue",
            # …et version du catalogue courant (sobrio_impact), pour détecter un écart.
            "catalog_version_courante": catalog_version(),
            "code_version": CODE_VERSION,
            "generated_at": quand.strftime("%Y-%m-%d %H:%M UTC"),
            "eur_per_usd": EUR_PER_USD,
        },
    }


# ---------------------------------------------------------------------------
# Rendu HTML + PDF
# ---------------------------------------------------------------------------

def _filtre_nombre(valeur, decimales: int = 0) -> str:
    """Format numérique à la française : 12 345,67 (— si absent)."""
    if valeur is None:
        return "—"
    texte = f"{float(valeur):,.{decimales}f}"
    # Virgule anglo-saxonne -> espace fine insécable ; point -> virgule.
    return texte.replace(",", " ").replace(".", ",")


def render_html(context: dict) -> str:
    """Rend le gabarit ``templates/report.html.j2`` avec le contexte donné."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=True,
        undefined=StrictUndefined,
    )
    env.filters["nombre"] = _filtre_nombre
    return env.get_template("report.html.j2").render(**context)


def html_to_pdf(html: str, out_path: Path) -> Path:
    """Écrit le PDF A4 via WeasyPrint."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html, base_url=str(TEMPLATES_DIR)).write_pdf(str(out_path))
    return out_path


def run(
    org: str,
    month: str,
    database_url: str | None = None,
    out: str | Path | None = None,
) -> Path:
    """Pipeline complet : requêtes -> contexte -> HTML -> PDF. Retourne le chemin."""
    url = database_url or os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
    engine = create_engine(url)
    try:
        resultats = run_queries(engine, org, month)
    finally:
        engine.dispose()
    contexte = build_context(org, month, resultats)
    html = render_html(contexte)
    chemin = Path(out) if out else OUT_DIR / f"rapport_{org}_{month}.pdf"
    return html_to_pdf(html, chemin)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Génère le rapport mensuel PDF Sobrio (deux volets : économique et "
            "environnemental). Chaque chiffre provient d'une requête versionnée "
            "dans report/queries/."
        )
    )
    parser.add_argument("--org", default="demo", help="Identifiant de l'organisation")
    parser.add_argument("--month", required=True, help="Mois au format AAAA-MM, ex. 2026-06")
    parser.add_argument(
        "--database-url",
        default=None,
        help="URL SQLAlchemy (défaut : env DATABASE_URL, puis base de dev locale)",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Chemin du PDF (défaut : report/out/rapport_<org>_<month>.pdf)",
    )
    args = parser.parse_args(argv)
    chemin = run(args.org, args.month, args.database_url, args.out)
    print(f"Rapport généré : {chemin}", file=sys.stderr)


if __name__ == "__main__":
    main()
