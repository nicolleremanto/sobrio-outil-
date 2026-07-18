"""Pipeline de distillation R4 — DRY-RUN PAR DÉFAUT (§5.4 ROUTEUR_CLASSIFIEUR.md).

Motif : le corpus synthétique (`generate_corpus.py`) sert au démarrage à
froid ; une future amélioration consisterait à faire ÉTIQUETER (« distiller »)
des lignes par un modèle professeur via l'API payante Anthropic — une
DÉPENSE RÉELLE, jamais engagée sans décision explicite des fondateurs
(`docs/decisions.md`, entrée 2026-07-18).

Ce module NE FAIT DONC JAMAIS d'appel réseau, avec ou sans les gates d'env
activées :

- `dry_run(...)` (chemin par défaut) produit des étiquettes « professeur »
  SIMULÉES — un stub DÉTERMINISTE (hash de `id`+`catégorie`), marqué
  `"mode": "dry_run"` et un avertissement explicite dans le rapport. Cette
  simulation ne prétend imiter QUE la FORME du pipeline (déterminisme,
  absence de texte, structure du rapport), jamais un JUGEMENT réel.
- `run_real(...)` (chemin payant) vérifie dans l'ordre : (1)
  `SOBRIO_ALLOW_PAID_CALLS == "1"` (sinon refus explicite), (2) le coût
  ESTIMÉ (nb de lignes × prix catalogue, AUCUN appel réseau) reste sous le
  cap `SOBRIO_MAX_SPEND_USD` (défaut 20 $, sinon refus explicite), puis
  **S'ARRÊTE TOUJOURS AVANT TOUT APPEL** avec le message : « run réel =
  décision fondateurs (docs/decisions.md) — l'intégration du client API sera
  livrée avec cette décision. » Ce chemin n'a — et n'aura jamais dans ce
  module — d'implémentation d'appel réseau : c'est une DÉCISION
  D'ORCHESTRATION (voir CLAUDE.md / ROUTEUR_CLASSIFIEUR.md §5.4) : **AUCUN
  import de SDK payant (`anthropic`) ni de client HTTP (`httpx`, `requests`,
  `urllib.request`, `socket`, …) nulle part dans `router/`** — invariant
  cost-guard « zéro motif réseau dans router/ », prouvable par un grep sur
  les imports de ce fichier (et testé, `test_router_data_distill.py`).

**Note CGU** : même une fois la décision fondateurs actée et le cap de coût
validé, une distillation réelle utiliserait des SORTIES de l'API Anthropic
pour entraîner un AUTRE modèle (le classifieur étage 1). Les conditions
d'utilisation d'Anthropic restreignent usuellement l'usage des sorties de
l'API pour entraîner des modèles concurrents ou dérivés — un classifieur de
routage interne à faible capacité est probablement hors du périmètre visé
par ce type de clause, mais ce point N'A PAS été vérifié formellement ici
(aucun appel réseau, donc aucune lecture des CGU à jour) : **une revue
explicite des CGU en vigueur au moment de l'activation reste un préalable
obligatoire**, indépendant du cap de dépense.

**Compteur d'arrêt** : `get_stop_counter()` expose combien de fois
`run_real(...)` a franchi les deux gates (env + cap) et s'est arrêté au
point d'arrêt volontaire — utile en audit pour distinguer « jamais tenté »
de « tenté et stoppé correctement ». Remis à zéro à chaque import du module
(processus court-vécu par construction : CLI ou test).
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from collections import Counter
from pathlib import Path

from sobrio_router import VISIBLE_MODELS

CATALOG_PATH = Path(__file__).resolve().parents[2] / "contracts" / "model_catalog.yaml"
ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
DEFAULT_CORPUS = ARTIFACTS_DIR / "corpus-v1.jsonl.gz"
DEFAULT_OUT = ARTIFACTS_DIR / "distill-dry-run-latest.json"

# Modèle professeur HYPOTHÉTIQUE pour l'estimation de coût — le plus capable
# du catalogue VISIBLE (`claude-fable-5` est `visible: false`, RFC-0002, hors
# périmètre même pour une distillation professeur/élève).
_DEFAULT_TEACHER_MODEL = "claude-opus-4-8"
# Hypothèse DOCUMENTÉE (pas mesurée) : une étiquette + une courte
# justification tient dans peu de tokens de sortie.
_ASSUMED_OUTPUT_TOKENS = 20
_SAMPLE_SIZE = 20

_ENV_ALLOW = "SOBRIO_ALLOW_PAID_CALLS"
_ENV_CAP = "SOBRIO_MAX_SPEND_USD"
_DEFAULT_MAX_SPEND_USD = 20.0

_NOTE_CGU = (
    "Une distillation réelle utiliserait des sorties de l'API Anthropic pour "
    "entraîner un autre modèle (le classifieur étage 1) — les CGU Anthropic "
    "restreignent usuellement cet usage pour des modèles concurrents/dérivés ; "
    "revue CGU explicite requise avant toute activation, INDÉPENDAMMENT du cap "
    "de dépense (non vérifiée ici : aucun appel réseau, cf. docstring du module)."
)

_stop_counter = 0


def get_stop_counter() -> int:
    """Nombre de fois où `run_real(...)` a franchi les gates et s'est arrêté volontairement."""
    return _stop_counter


def _read_rows(path: Path) -> list[dict]:
    if path.suffix == ".gz":
        raw = gzip.decompress(path.read_bytes()).decode("utf-8")
    else:
        raw = path.read_text(encoding="utf-8")
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def _catalog_prices(path: Path = CATALOG_PATH) -> dict[str, dict[str, float]]:
    """Extrait `id`/`price_in_usd_mtok`/`price_out_usd_mtok` de `model_catalog.yaml`.

    Parseur volontairement MINIMAL, ligne à ligne, SANS dépendance YAML :
    `router` reste stdlib-only (`router/pyproject.toml`) ; le catalogue a un
    format stable (une entrée `- id: ...` par modèle, champs `clé: valeur`
    simples, commentaires `#` optionnels en fin de ligne).
    """
    prices: dict[str, dict[str, float]] = {}
    current_id: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("- id:"):
            current_id = stripped.split(":", 1)[1].split("#")[0].strip()
            prices[current_id] = {}
        elif current_id and stripped.startswith("price_in_usd_mtok:"):
            prices[current_id]["price_in_usd_mtok"] = float(
                stripped.split(":", 1)[1].split("#")[0].strip()
            )
        elif current_id and stripped.startswith("price_out_usd_mtok:"):
            prices[current_id]["price_out_usd_mtok"] = float(
                stripped.split(":", 1)[1].split("#")[0].strip()
            )
    return prices


def estimate_cost(corpus_path: Path, teacher_model: str = _DEFAULT_TEACHER_MODEL) -> dict:
    """Estime le coût d'un run réel : nb de lignes × prix catalogue. AUCUN appel réseau."""
    rows = _read_rows(corpus_path)
    n = len(rows)
    avg_input_tokens = sum(r["signals"]["prompt"]["token_est"] for r in rows) / n if n else 0.0
    prices = _catalog_prices()
    if teacher_model not in prices:
        raise ValueError(f"modèle professeur inconnu du catalogue : {teacher_model!r}")
    price_in = prices[teacher_model]["price_in_usd_mtok"]
    price_out = prices[teacher_model]["price_out_usd_mtok"]
    cost = n * (
        (avg_input_tokens / 1_000_000) * price_in + (_ASSUMED_OUTPUT_TOKENS / 1_000_000) * price_out
    )
    return {
        "n_lignes": n,
        "teacher_model_hypothese": teacher_model,
        "avg_input_tokens_est": round(avg_input_tokens, 2),
        "assumed_output_tokens": _ASSUMED_OUTPUT_TOKENS,
        "prix_catalogue_usd_mtok": {"in": price_in, "out": price_out},
        "cout_estime_usd": round(cost, 4),
    }


def _simulate_teacher_label(row_id: str, category: str) -> str:
    """Étiquette « professeur » SIMULÉE — stub DÉTERMINISTE, PAS un jugement réel.

    Hash sha256 de `id|catégorie` -> position dans `VISIBLE_MODELS` trié.
    Ne lit AUCUN signal (ne simule que la FORME du pipeline : déterminisme,
    absence de texte — jamais son jugement, qui exigerait un vrai appel).
    """
    digest = hashlib.sha256(f"{row_id}|{category}".encode()).hexdigest()
    order = sorted(VISIBLE_MODELS)
    return order[int(digest[:8], 16) % len(order)]


def dry_run(
    corpus_path: Path = DEFAULT_CORPUS, teacher_model: str = _DEFAULT_TEACHER_MODEL
) -> dict:
    """Chemin PAR DÉFAUT : étiquettes simulées + estimation de coût. AUCUN appel réseau."""
    rows = _read_rows(corpus_path)
    cost = estimate_cost(corpus_path, teacher_model)
    labels = [_simulate_teacher_label(r["id"], r["category"]) for r in rows]
    distribution = dict(sorted(Counter(labels).items()))
    echantillon = [
        {"id": r["id"], "label_simule": label}
        for r, label in list(zip(rows, labels, strict=True))[:_SAMPLE_SIZE]
    ]
    return {
        "mode": "dry_run",
        "avertissement": (
            "SIMULATION — étiquettes stub déterministes (hash id+catégorie), AUCUN "
            "jugement réel, AUCUN appel réseau. Ne PAS utiliser comme vérité terrain."
        ),
        "corpus_path": str(corpus_path),
        **cost,
        "distribution_labels_simules": distribution,
        "echantillon_labels_simules": echantillon,
        "note_cgu": _NOTE_CGU,
    }


def run_real(
    corpus_path: Path = DEFAULT_CORPUS, teacher_model: str = _DEFAULT_TEACHER_MODEL
) -> None:
    """Chemin PAYANT — lève TOUJOURS avant tout appel (voir docstring du module).

    Gates, DANS L'ORDRE : (1) `SOBRIO_ALLOW_PAID_CALLS == "1"`, (2) coût
    estimé <= `SOBRIO_MAX_SPEND_USD` (défaut 20 $). Les deux franchies, la
    fonction lève quand même — le franchissement est compté
    (`get_stop_counter()`) mais AUCUN appel n'a jamais lieu dans ce module.
    """
    global _stop_counter
    if os.environ.get(_ENV_ALLOW) != "1":
        raise RuntimeError(
            f"run réel refusé : {_ENV_ALLOW} doit valoir '1' (défaut : dry-run, aucune "
            "dépense) — voir docs/decisions/ROUTEUR_CLASSIFIEUR.md §5.4"
        )
    try:
        cap = float(os.environ.get(_ENV_CAP, _DEFAULT_MAX_SPEND_USD))
    except ValueError as exc:
        raise RuntimeError(f"{_ENV_CAP} invalide (nombre attendu) : {exc}") from exc

    estimate = estimate_cost(corpus_path, teacher_model)
    if estimate["cout_estime_usd"] > cap:
        raise RuntimeError(
            f"run réel refusé : coût estimé {estimate['cout_estime_usd']:.2f} $ dépasse "
            f"le cap {_ENV_CAP}={cap:.2f} $"
        )

    _stop_counter += 1
    raise RuntimeError(
        "run réel = décision fondateurs (docs/decisions.md) — l'intégration du client API "
        "sera livrée avec cette décision. Aucun appel n'a été effectué (invariant cost-guard, "
        "zéro motif réseau dans router/)."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Pipeline de distillation R4 — dry-run par défaut (§5.4)."
    )
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--teacher-model", default=_DEFAULT_TEACHER_MODEL)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--real",
        action="store_true",
        help="tente le chemin payant (s'arrête TOUJOURS avant tout appel, cf. docstring)",
    )
    args = parser.parse_args(argv)

    if args.real:
        run_real(args.corpus, args.teacher_model)  # lève toujours
        return 1  # inatteignable

    report = dry_run(args.corpus, args.teacher_model)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nrapport écrit : {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
