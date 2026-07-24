"""Bench du pipeline COMPLET de l'étage 2 (tokenise → encode → poole → tête) — R6 Lot 6, §11.

Preuve des budgets §7 : p95 ≤ 30 ms CPU (borne INCLUSIVE, convention R5) et
RSS < 1 Go, consignée dans `router/artifacts/bench/embed-latest.json`
(patron bench.py). C'est la preuve de latence RÉELLE exigée par la garde D8
de `promote_embed` (§9.3.4) : le harnais sur fixtures ne mesure que la tête
(`latence_perimetre: "head_only"`), ce bench mesure `EmbedRouter.decide`
de bout en bout sur l'encodeur réel.

RECADRAGE (ledger, décision 2026-07-23 — premier fetch = GESTE FONDATEUR) :
aucune source d'encodeur n'est approuvée à ce jour, dépendances embed et
modèle ABSENTS — le bench RÉEL est impossible. Toute construction de
l'étage 2 échoue en `EmbedLoadError` : ce CLI REFUSE alors proprement
(exit 2, message renvoyant au geste fondateur — patron promote_embed/fetch,
JAMAIS un traceback nu). Écart assumé du « skip exit 0 » de §11, qui
supposait le geste fondateur advenu ; la logique de MESURE est prouvée par
tests avec un encodeur factice (§10.5).

Textes de mesure : 500 SOUPES DE MOTS-VIDES seedées (convention §10.1 —
vocabulaire fermé, JAMAIS de texte type prompt), générées EN MÉMOIRE,
longueurs 10–4000 caractères, mélange fr/en. Jamais écrites sur disque,
jamais dans le rapport ni dans une exception : le rapport ne porte que des
nombres, hash, identifiants système et dates (règle n°1).

`ru_maxrss` (précision §11, MINOR-4 2026-07-23) : la valeur est en OCTETS
sur darwin et en KILO-OCTETS sur Linux — la conversion est EXPLICITE par
plateforme (`rss_peak_mb`), le rapport consigne `platform`, et la machine
de référence est darwin. Sans cette conversion le verdict < 1024 Mo serait
faux d'un facteur 1024 selon l'OS.
"""

from __future__ import annotations

import hashlib
import json
import random
import resource
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from bench import _git_sha, _percentile
from sobrio_router import ConversationSignals, PromptSignals, Signals
from sobrio_router.embed import (
    CANDIDATE_HEAD_DIR,
    ENCODER_DIR,
    PROMOTED_HEAD_DIR,
    EmbedLoadError,
    EmbedRouter,
    expected_embed_spec,
)

_SEED = 42  # parité bench.py — reproductibilité des soupes ET des longueurs
_N_TEXTES = 500
_N_WARMUP = 50
_LONGUEUR_MIN = 10
_LONGUEUR_MAX = 4000  # = borne D11 : couvre le pire cas de troncature §5.2.2

# Budgets §7/§11 — mêmes valeurs que la garde D8 de promote_embed (testé).
P95_BUDGET_MS = 30.0  # borne INCLUSIVE (convention harmonisée R5)
RSS_MAX_MB = 1024.0  # borne STRICTE (< 1 Go)

# Chemins module-level (monkeypatchables par les tests, patron promote_embed).
ENCODEUR_DIR = ENCODER_DIR
CANDIDATE_DIR = CANDIDATE_HEAD_DIR
PROMOTED_DIR = PROMOTED_HEAD_DIR
_ARTIFACT_PATH = Path(__file__).resolve().parent / "artifacts" / "bench" / "embed-latest.json"

_FICHIERS_TETE = ("head.json", "calibrator.json", "metadata.json")

# Soupes de mots-vides (convention §10.1) : vocabulaire FERMÉ de mots
# grammaticaux — aucune séquence ne peut former un texte type prompt.
_MOTS_VIDES = {
    "fr": (
        "le",
        "la",
        "les",
        "de",
        "des",
        "un",
        "une",
        "et",
        "ou",
        "dans",
        "sur",
        "par",
        "pour",
        "avec",
        "sans",
        "sous",
        "vers",
        "chez",
        "donc",
        "or",
        "ni",
        "car",
        "mais",
        "si",
        "que",
        "qui",
        "ne",
        "pas",
        "plus",
        "en",
        "au",
        "aux",
        "du",
        "se",
        "sa",
        "son",
        "ses",
    ),
    "en": (
        "the",
        "a",
        "an",
        "of",
        "and",
        "or",
        "in",
        "on",
        "at",
        "by",
        "for",
        "with",
        "without",
        "under",
        "over",
        "to",
        "from",
        "but",
        "if",
        "that",
        "which",
        "who",
        "not",
        "no",
        "so",
        "as",
        "than",
        "then",
        "this",
        "these",
        "those",
        "its",
        "their",
        "our",
        "is",
        "are",
    ),
}


class RefusError(RuntimeError):
    """Refus fail-closed du CLI (exit 2) — patron promote_embed/fetch_embed_model."""


def generer_soupes(n: int, seed: int) -> list[str]:
    """`n` soupes de mots-vides seedées, longueurs 10–4000 caractères, mélange fr/en.

    Déterministe à l'octet (double appel bit-identique, testé). EN MÉMOIRE
    SEULEMENT : jamais écrites sur disque, jamais consignées dans le rapport.
    """
    rng = random.Random(seed)
    soupes: list[str] = []
    for index in range(n):
        langue = "fr" if index % 2 == 0 else "en"  # alternance : mélange garanti
        cible = rng.randint(_LONGUEUR_MIN, _LONGUEUR_MAX)
        mots: list[str] = []
        longueur = -1  # longueur de la future jointure " ".join(mots)
        while longueur < cible:
            mot = rng.choice(_MOTS_VIDES[langue])
            mots.append(mot)
            longueur += len(mot) + 1
        soupes.append(" ".join(mots)[:cible])  # exactement `cible` caractères
    return soupes


def _signals_bench(texte: str) -> Signals:
    """Signaux neutres porteurs du texte : seul `prompt_text` compte pour l'étage 2."""
    return Signals(
        prompt=PromptSignals(
            char_len=len(texte),
            token_est=len(texte) // 4,
            lang="fr",
            has_code=False,
            has_math=False,
            keyword_flags=(),
            prompt_text=texte,
        ),
        conversation=ConversationSignals(),
    )


def _sha256_fichier(chemin: Path) -> str:
    h = hashlib.sha256()
    with chemin.open("rb") as flux:
        for bloc in iter(lambda: flux.read(1024 * 1024), b""):
            h.update(bloc)
    return h.hexdigest()


def _tete_dir_selectionnee() -> Path | None:
    """§11 : candidate si présente, sinon promoted, sinon None (tête neutre jetable)."""
    for directory in (CANDIDATE_DIR, PROMOTED_DIR):
        if all((directory / nom).is_file() for nom in _FICHIERS_TETE):
            return directory
    return None


def _ecrire_tete_neutre(directory: Path) -> Path:
    """Tête neutre JETABLE (§11) : poids nuls générés en mémoire, nombres uniquement.

    Déposée dans un répertoire ÉPHÉMÈRE pour emprunter le chargement
    fail-closed RÉEL d'`EmbedRouter` (gardes §5.1 comprises), supprimée
    sitôt le routeur construit. `confidence_cap` 1.0 : tête de MESURE — le
    plafond D3 réel vit dans les artefacts entraînés, ici seul le COÛT de
    la chaîne compte, pas la valeur émise.
    """
    directory.mkdir(parents=True, exist_ok=True)
    spec = expected_embed_spec()
    labels = list(spec["labels"])  # type: ignore[arg-type] — liste par construction §6.1
    dim = int(spec["dim"])  # type: ignore[arg-type] — entier par construction §6.1
    head = {"w": [[0.0] * dim for _ in labels], "b": [0.0] * len(labels)}
    head_octets = json.dumps(head).encode("utf-8")
    (directory / "head.json").write_bytes(head_octets)
    calib_octets = json.dumps({"x": [0.0, 1.0], "y": [0.0, 1.0]}).encode("utf-8")
    (directory / "calibrator.json").write_bytes(calib_octets)
    metadata = {
        "artefact": "embed_head_bench_neutre",
        "label_mapping": {label: index for index, label in enumerate(labels)},
        "embed_spec": spec,
        "confidence_cap": 1.0,
        "sha256_head_json": hashlib.sha256(head_octets).hexdigest(),
        "sha256_calibrator_json": hashlib.sha256(calib_octets).hexdigest(),
    }
    (directory / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    return directory


def _construire_routeur() -> tuple[EmbedRouter, str]:
    """Assemble l'étage 2 RÉEL à bencher ; retourne `(routeur, sha256 du head.json)`.

    Toute impossibilité (dépendances embed absentes, encodeur absent ou non
    approuvé — littéraux sha None avant le geste fondateur —, tête invalide)
    remonte en `EmbedLoadError`, re-typée `RefusError` par `main()`.
    """
    tete_dir = _tete_dir_selectionnee()
    if tete_dir is not None:
        routeur = EmbedRouter(encoder_dir=ENCODEUR_DIR, head_dir=tete_dir)
        return routeur, _sha256_fichier(tete_dir / "head.json")
    with tempfile.TemporaryDirectory(prefix="sobrio-bench-tete-neutre-") as tmp:
        tete_neutre_dir = _ecrire_tete_neutre(Path(tmp))
        routeur = EmbedRouter(encoder_dir=ENCODEUR_DIR, head_dir=tete_neutre_dir)
        head_sha = _sha256_fichier(tete_neutre_dir / "head.json")
    return routeur, head_sha


def rss_peak_mb(ru_maxrss: int, plateforme: str) -> float:
    """Conversion EXPLICITE de `ru_maxrss` en Mo (§11, MINOR-4 2026-07-23).

    darwin : OCTETS → /(1024*1024) ; Linux (et autres) : KILO-OCTETS →
    /1024. Testée sur les DEUX branches (plateforme injectée).
    """
    if plateforme == "darwin":
        return ru_maxrss / (1024 * 1024)
    return ru_maxrss / 1024


def code_sortie(p95_ms: float, rss_mb: float) -> int:
    """Verdicts §11 : p95 ≤ 30.0 ms INCLUSIF ET RSS < 1024 Mo STRICT, sinon 1."""
    if p95_ms > P95_BUDGET_MS:
        return 1
    if rss_mb >= RSS_MAX_MB:
        return 1
    return 0


def main() -> int:
    try:
        routeur, head_sha = _construire_routeur()
    except EmbedLoadError as exc:
        # RECADRAGE ledger 2026-07-23 : cas NOMINAL aujourd'hui — refus
        # propre exit 2, message = cause (chemins/hash/comptes) + renvoi au
        # geste fondateur. Rien n'est écrit.
        print(
            f"REFUS : bench réel impossible — {exc} ; encodeur et dépendances embed requis "
            "localement. Le premier fetch du modèle est un GESTE FONDATEUR (recadrage ledger "
            "2026-07-23) : source à approuver par le fondateur, puis make router-embed-model.",
            file=sys.stderr,
        )
        return 2

    pool = [_signals_bench(texte) for texte in generer_soupes(_N_TEXTES, _SEED)]

    # Warmup (hors mesure) : stabilise session ORT et tokenizer.
    for signals in pool[:_N_WARMUP]:
        routeur.decide(signals)

    latences_ms: list[float] = []
    for signals in pool:
        debut = time.perf_counter()
        routeur.decide(signals)  # étage 2 SEUL (§11) — pipeline complet
        latences_ms.append((time.perf_counter() - debut) * 1000)
    latences_ms.sort()

    ru_maxrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    report = {
        "n": len(latences_ms),
        "p50_ms": round(_percentile(latences_ms, 0.50), 4),
        "p95_ms": round(_percentile(latences_ms, 0.95), 4),
        "rss_peak_mb": round(rss_peak_mb(ru_maxrss, sys.platform), 2),
        "platform": sys.platform,
        "encoder_sha256": _sha256_fichier(ENCODEUR_DIR / "model.onnx"),
        "head_sha256": head_sha,
        "date": datetime.now(tz=UTC).isoformat(),
        "git_sha": _git_sha(),
    }

    _ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _ARTIFACT_PATH.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))

    code = code_sortie(float(report["p95_ms"]), float(report["rss_peak_mb"]))
    if code:
        print(
            f"ÉCHEC : p95={report['p95_ms']} ms (budget INCLUSIF {P95_BUDGET_MS} ms) "
            f"et/ou RSS={report['rss_peak_mb']} Mo (plafond STRICT {RSS_MAX_MB} Mo) — §7/§11. "
            "Repli tardif documenté §11 : réduire max_tokens (256→192→128) = bump "
            "EMBED_SPEC_VERSION + retrain + re-gate, consigné au ledger.",
            file=sys.stderr,
        )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
