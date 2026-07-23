"""Harnais d'éval de la TÊTE de l'étage 2 sur les fixtures synthétiques (R6, spec §9.1).

Registre : `prior` (tête dégénérée déterministe, baseline du gate — D13),
`head_candidate` / `head_promoted` (les MÊMES objets `EmbedHead` que ceux
servis par `EmbedRouter`). Chaque décision est obtenue via
`EmbedHead.predict(embedding)` (§5.2bis), JAMAIS via un softmax local : ce
que mesure ce harnais, ce sont les confiances SERVIES — calibrées
(`min(brut, iso)`) ET plafonnées (`confidence_cap` du metadata) — sur des
embeddings pré-calculés (fixtures). Conséquences assumées (correction
MAJOR-1, 2026-07-23) : l'`ece` du rapport est l'ECE CALIBRÉ du service
réel ; `calibration_bande_auto` est calculée sur ces mêmes confiances
servies (donc structurellement vide sous plafond 0.74, §9.2) ; seul le p95
reste partiel (`latence_perimetre: "head_only"` — la preuve du budget 30 ms
du pipeline COMPLET est le bench §11, exigé à la promotion §9.3).

MÊME SCHÉMA de rapport que `harness.py` : la boucle de mesure et TOUTES les
métriques sont `harness.evaluate_router` RÉUTILISÉ TEL QUEL (zéro
réimplémentation — gardes défensives comprises : modèle hors catalogue,
confiance invalide => refus bruyant), via un adaptateur `Router` minimal
dont `decide(embedding)` appelle `predict`. `evaluate_gate` reste 100 % pur
et réutilisé tel quel (`--suite embed`, §9.2).

INTÉGRITÉ DE L'ÉVALUATION (§7.2, patron R5) : ce harnais mesure la MÉCANIQUE
de la tête sur données synthétiques seedées — il ne prédit RIEN de la
qualité sémantique réelle ; interdiction d'en citer les scores comme
performance produit. La tête réelle attend la télémétrie v1 (D4).

Écrit `router/artifacts/eval/embed-<nom>-latest.json` (versionné, convention
clôture R5 : régénéré/commité aux promotions uniquement). Module autonome
(convention harness.py) — stdlib + `EmbedHead` (stdlib pure) : AUCUNE
dépendance embed requise.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime

from embed_fixtures import canonical_eval_set, canonical_sha256
from harness import _ARTIFACTS_DIR, _git_sha, evaluate_router

from sobrio_router.embed import CANDIDATE_HEAD_DIR, PROMOTED_HEAD_DIR, EmbedHead, EmbedLoadError
from sobrio_router.interface import Router
from sobrio_router.types import Decision

# Chemins des têtes — module-level (monkeypatchables par les tests, lus À
# L'APPEL par les lambdas du registre, patron des constantes de train_v05).
CANDIDATE_DIR = CANDIDATE_HEAD_DIR
PROMOTED_DIR = PROMOTED_HEAD_DIR

# Baseline « prior » (D13) : tête dégénérée déterministe — toujours le
# palier médian sûr, à confiance 0.5. Donne au gate un plancher réel à
# battre sur les fixtures, sans inventer une baseline sémantique fictive.
PRIOR_MODEL = "claude-sonnet-5"
PRIOR_CONFIDENCE = 0.5
PRIOR_RULE = "embed:prior"
HEAD_RULE = "embed:v0"

# Limite consignée DANS le rapport (§9.1) : les fixtures étant des
# embeddings déjà calculés, le p95 mesuré ne couvre que la tête.
LATENCE_PERIMETRE = "head_only"
# Note d'intégrité écrite dans chaque rapport (§7.2 — constante EXACTE,
# vérifiée par le test « aucun champ texte libre » du lot).
NOTE_INTEGRITE = (
    "fixtures synthétiques seedées — mesure la MÉCANIQUE de la tête, "
    "ne prédit rien de la qualité sémantique réelle (D4/D6)"
)


class PriorHead:
    """Tête-prior constante (D13) : `predict` ignore l'embedding, par design."""

    def predict(self, embedding: object) -> tuple[str, float]:
        return (PRIOR_MODEL, PRIOR_CONFIDENCE)


@dataclass(frozen=True)
class _FixtureEntry:
    """Adaptateur d'entrée pour `evaluate_router` : (embedding, label, categorie).

    `signals` porte l'EMBEDDING (liste de floats) — pas des `Signals` : le
    harnais embed évalue la tête seule, en aval de l'encodeur (§9.1).
    """

    category: str
    label: str
    signals: list[float] = field(repr=False)


class _HeadRouter(Router):
    """Adaptateur `Router` minimal : `decide(embedding)` -> `predict` (§9.1).

    La chaîne de confiance vit INTÉGRALEMENT dans `EmbedHead.predict`
    (§5.2bis) : cet adaptateur ne recalcule, ne re-calibre et ne re-plafonne
    RIEN — les confiances mesurées sont les confiances SERVIES (test
    d'iso-confiance §10.4).
    """

    def __init__(self, head: object, rule: str) -> None:
        self._head = head
        self._rule = rule

    def decide(self, signals: object) -> Decision:  # type: ignore[override]
        label, confiance = self._head.predict(signals)  # type: ignore[attr-defined]
        return Decision(model=label, confidence=confiance, rule=self._rule)


# Registre des têtes évaluables (§9.1). Les lambdas ne construisent qu'À LA
# SÉLECTION et lisent les chemins module-level À L'APPEL ; une tête absente
# ou corrompue à l'éval est un ÉCHEC BRUYANT (`EmbedLoadError` -> REFUS
# exit 2 dans `main()`), jamais un repli silencieux (leçon R4).
_REGISTRY = {
    "prior": lambda: (PriorHead(), PRIOR_RULE),
    "head_candidate": lambda: (EmbedHead.load(CANDIDATE_DIR), HEAD_RULE),
    "head_promoted": lambda: (EmbedHead.load(PROMOTED_DIR), HEAD_RULE),
}


def run(head_name: str) -> dict:
    """Construit la tête `head_name`, l'évalue sur le set canonique, ajoute les métadonnées.

    `golden_sha` = sha CANONIQUE calculé sur le set RÉELLEMENT évalué
    (`canonical_sha256`) — le gate `--suite embed` le confronte au pin
    committé du manifest (`embed_golden_sha256()`), refusant toute éval
    faite sur un autre set (épinglage §9.2, patron ronde 0 R3).
    """
    if head_name not in _REGISTRY:
        raise ValueError(
            f"tête inconnue : {head_name!r} — registre disponible : {sorted(_REGISTRY)}"
        )
    head, rule = _REGISTRY[head_name]()
    rows = canonical_eval_set()
    entries = [
        _FixtureEntry(category=row.categorie, label=row.label, signals=list(row.embedding))
        for row in rows
    ]
    report = evaluate_router(_HeadRouter(head, rule), entries)
    report["router_name"] = head_name
    report["golden_sha"] = canonical_sha256(rows)
    report["date"] = datetime.now(tz=UTC).isoformat()
    report["git_sha"] = _git_sha()
    report["latence_perimetre"] = LATENCE_PERIMETRE
    report["integrite_evaluation"] = NOTE_INTEGRITE
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Évalue une tête de l'étage 2 sur les fixtures synthétiques figées (chantier R6)."
        )
    )
    parser.add_argument(
        "--router",
        default="prior",
        choices=sorted(_REGISTRY),
        help="tête du registre à évaluer (défaut : prior — baseline du gate, D13)",
    )
    args = parser.parse_args(argv)

    # Tête absente/corrompue à l'éval : ÉCHEC BRUYANT, pas de repli (patron
    # harness R5 §9) — le repli §5.2 est un invariant de PRODUCTION.
    try:
        report = run(args.router)
    except EmbedLoadError as exc:
        print(
            f"REFUS : tête {args.router} absente ou invalide — rien à évaluer ({exc})",
            file=sys.stderr,
        )
        return 2

    _ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _ARTIFACTS_DIR / f"embed-{args.router}-latest.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nrapport écrit : {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
