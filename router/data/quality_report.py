"""Rapport data-quality du corpus synthétique R4 (`generate_corpus.py`).

Module autonome (même convention que `router/eval/loader.py` /
`router/data/generate_corpus.py`) : importé par script direct ou par les
tests via `sys.path.insert(0, "router/data")`.

`analyze(rows)` est une fonction PURE (aucune I/O) qui consomme une liste de
lignes DÉJÀ chargées (dicts `{"id", "category", "label", "signals"}`) et
retourne un rapport JSON-sérialisable :

- **doublons** : taux de lignes dont la signature de SIGNAUX (JSON canonique
  de `signals`, triée) est un doublon exact d'une autre ligne — alerte au-delà
  de 5 %.
- **équilibre catégorie×label** : sur les 24 cellules (8 catégories ×
  `VISIBLE_MODELS`), alerte si une cellule attendue est VIDE, ou si le ratio
  max/min des cellules non vides dépasse 20.
- **plages hors bornes** : les signaux numériques doivent rester dans des
  bornes cohérentes avec `sobrio_router.types` (le schéma lui-même
  n'impose pas de bornes — on vérifie ici des invariants métier raisonnables,
  cf. `_BOUNDS`) ; `recos_followed` ne peut jamais dépasser `recos_shown`
  (même invariant que `generate_golden.py`/`generate_corpus.py`) ; `lang`
  doit rester dans l'énumération du contrat (`contracts/openapi.yaml`,
  `fr`/`en`/`other`) ; `label` doit rester dans `VISIBLE_MODELS`.
- **langue** : part de `fr` attendue MAJORITAIRE (> 50 %, entreprise française).

Le verdict `{"ok": bool, "alertes": [...]}` est INFORMATIF : `main()` ne fait
jamais échouer le processus appelant (utilisé par `make router-corpus-check`
sur de petits corpus où quelques cellules rares peuvent légitimement
approcher les seuils par simple effet de taille d'échantillon) — c'est au
lecteur humain/CI amont de décider quoi faire d'un verdict `ok: false`.
"""

from __future__ import annotations

import argparse
import gzip
import json
from collections import Counter
from pathlib import Path

from sobrio_router import VISIBLE_MODELS

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
DEFAULT_CORPUS = ARTIFACTS_DIR / "corpus-v1.jsonl.gz"
DEFAULT_OUT = ARTIFACTS_DIR / "corpus-v1.quality.json"

_DUP_ALERT_THRESHOLD = 0.05
_BALANCE_RATIO_ALERT = 20.0
_FR_MIN_SHARE = 0.5

# Bornes métier raisonnables (pas imposées par `sobrio_router.types`, qui
# n'a aucune contrainte de plage — dérivées de la distribution effective du
# générateur, avec marge : cf. `corpus-v1.stats.json` d'un run de référence,
# `router/data/reference/`).
_BOUNDS = {
    "char_len": (1, 20_000),
    "token_est": (1, 6_000),
    "msg_count": (0, 90),
    "context_token_est": (0, 40_000),
    "recos_shown": (0, 20),
    "recos_followed": (0, 20),
    "derogations_up": (0, 15),
}
_ALLOWED_LANGS = frozenset({"fr", "en", "other"})


def _read_rows(path: Path) -> list[dict]:
    """Lit un corpus JSONL, gzippé (`.gz`) ou non (fixtures de test)."""
    if path.suffix == ".gz":
        raw = gzip.decompress(path.read_bytes()).decode("utf-8")
    else:
        raw = path.read_text(encoding="utf-8")
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def _duplicate_rate(rows: list[dict]) -> float:
    signatures = Counter(json.dumps(r["signals"], sort_keys=True) for r in rows)
    n_dup = sum(count - 1 for count in signatures.values() if count > 1)
    return n_dup / len(rows)


def _balance_report(rows: list[dict]) -> dict:
    cells: dict[str, dict[str, int]] = {}
    categories: set[str] = set()
    for r in rows:
        categories.add(r["category"])
        cells.setdefault(r["category"], {})
        cells[r["category"]][r["label"]] = cells[r["category"]].get(r["label"], 0) + 1

    empty_cells: list[str] = []
    counts: list[int] = []
    for cat in sorted(categories):
        for label in sorted(VISIBLE_MODELS):
            n_cell = cells.get(cat, {}).get(label, 0)
            counts.append(n_cell)
            if n_cell == 0:
                empty_cells.append(f"{cat}×{label}")

    positive = [c for c in counts if c > 0]
    ratio = (max(positive) / min(positive)) if positive else None

    return {
        "cellules_vides": empty_cells,
        "ratio_max_min": round(ratio, 2) if ratio is not None else None,
        "seuil_alerte_ratio": _BALANCE_RATIO_ALERT,
        "cellules": {
            cat: dict(sorted(by_label.items())) for cat, by_label in sorted(cells.items())
        },
    }


def _bounds_violations(rows: list[dict]) -> dict[str, int]:
    violations: dict[str, int] = {}
    for r in rows:
        p, c = r["signals"]["prompt"], r["signals"]["conversation"]
        flat = {
            "char_len": p["char_len"],
            "token_est": p["token_est"],
            "msg_count": c["msg_count"],
            "context_token_est": c["context_token_est"],
            "recos_shown": c["recos_shown"],
            "recos_followed": c["recos_followed"],
            "derogations_up": c["derogations_up"],
        }
        for key, (lo, hi) in _BOUNDS.items():
            if not (lo <= flat[key] <= hi):
                violations[key] = violations.get(key, 0) + 1
        if c["recos_followed"] > c["recos_shown"]:
            violations["recos_followed_gt_shown"] = violations.get("recos_followed_gt_shown", 0) + 1
        if p["lang"] not in _ALLOWED_LANGS:
            violations["lang_hors_enum"] = violations.get("lang_hors_enum", 0) + 1
        if r["label"] not in VISIBLE_MODELS:
            violations["label_hors_catalogue"] = violations.get("label_hors_catalogue", 0) + 1
    return violations


def analyze(rows: list[dict]) -> dict:
    """Calcule le rapport data-quality complet sur des lignes DÉJÀ chargées."""
    alertes: list[str] = []
    n = len(rows)
    if n == 0:
        return {"n": 0, "verdict": {"ok": False, "alertes": ["corpus vide"]}}

    taux_doublons = _duplicate_rate(rows)
    if taux_doublons > _DUP_ALERT_THRESHOLD:
        alertes.append(
            f"taux de doublons de signature {taux_doublons:.2%} > seuil {_DUP_ALERT_THRESHOLD:.0%}"
        )

    balance = _balance_report(rows)
    if balance["cellules_vides"]:
        alertes.append(f"cellules catégorie×label vides : {balance['cellules_vides']}")
    if balance["ratio_max_min"] is not None and balance["ratio_max_min"] > _BALANCE_RATIO_ALERT:
        alertes.append(
            f"déséquilibre catégorie×label : ratio max/min = {balance['ratio_max_min']} "
            f"> {_BALANCE_RATIO_ALERT}"
        )

    violations = _bounds_violations(rows)
    if violations:
        alertes.append(f"valeurs hors bornes/invariants : {violations}")

    n_fr = sum(1 for r in rows if r["signals"]["prompt"]["lang"] == "fr")
    fr_share = n_fr / n
    if fr_share <= _FR_MIN_SHARE:
        alertes.append(f"part FR {fr_share:.1%} <= {_FR_MIN_SHARE:.0%} (attendue majoritaire)")

    return {
        "n": n,
        "taux_doublons_signature": round(taux_doublons, 4),
        "seuil_alerte_doublons": _DUP_ALERT_THRESHOLD,
        "equilibre_categorie_x_label": balance,
        "violations_bornes": violations,
        "fr_share": round(fr_share, 4),
        "seuil_fr_min": _FR_MIN_SHARE,
        "verdict": {"ok": not alertes, "alertes": alertes},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rapport data-quality du corpus R4.")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    rows = _read_rows(args.corpus)
    report = analyze(rows)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    verdict = report["verdict"]
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nverdict : {'OK' if verdict['ok'] else 'ALERTES'} -> {args.out}")
    # INFORMATIF : ne fait jamais échouer le processus (cf. docstring du module).
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
