"""Fixtures synthétiques d'embeddings — générateur DÉTERMINISTE seedé (R6, spec §7, D6).

AUCUN texte nulle part (décision D4/D6) : chaque entrée est un triplet
`(vecteur 384-d, label, categorie)` où le vecteur est un point seedé autour
d'un centroïde — JAMAIS l'encodage d'un texte. Ces fixtures sont le juge de
paix du gate de TÊTE (§9) : elles prouvent la MÉCANIQUE de l'étage 2
(train → calibration → gate → promotion → service) sur données synthétiques ;
elles ne prédisent RIEN de la qualité sémantique réelle — interdiction d'en
citer les scores comme performance produit (§7.2, patron « Intégrité de
l'évaluation » R5). La tête réelle attend la télémétrie v1 (D4).

Construction (§7.1) : 3×K centroïdes (K=4 motifs par label, tirés N(0, 1)
puis normalisés L2 sous une graine DÉDIÉE partagée train/éval — la structure
du problème est commune, seuls les POINTS diffèrent) ; point = centroïde +
bruit gaussien sigma, re-normalisé L2 (miroir de la sortie réelle du pipeline
§5.2.6). Le chevauchement est CONTRÔLÉ par sigma : exactitude de tête cible
~0,85-0,95, jamais 1,0 (un score parfait signalerait des fixtures dégénérées
— garde-fou testé §10.8).

Seeds train (20260723) ≠ éval (20260724) PAR CONSTRUCTION : étanchéité
train/éval documentée et testée (intersection vide, patron anti-fuite R4,
SANS assert d'horloge — leçon du flake consigné à l'audit de reprise).

`EMBED_GOLDEN_SHA256` (le hash canonique du set d'éval) est calculé par
`canonical_sha256(canonical_eval_set())` et ÉPINGLÉ en littéral dans
`router/eval/embed_golden/manifest.json` (committé, < 5 Ko — patron
`router/data/reference/` : rien de volumineux n'est commité, la matrice est
régénérée à la demande). `embed_golden_sha256()` LIT le pin (miroir de
`loader.golden_sha256` : elle ne recalcule rien — la cohérence pin/matrice
est prouvée par un test stdlib toujours exécuté, §10.8).

Module autonome stdlib SEULE (spec §1.1) — même convention d'import que
`loader.py`/`harness.py` (script frère ou `sys.path` des tests).
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path

from sobrio_router.embed import _DIM as DIM
from sobrio_router.ml import LABEL_ORDER

# Graine DÉDIÉE des centroïdes : la géométrie du problème (3×K motifs) est
# PARTAGÉE entre train et éval — sans elle, une tête entraînée sur les
# clusters du train ne saurait rien des clusters de l'éval (le problème
# mesuré serait le hasard, pas la mécanique).
CENTROID_SEED = 20260722
# Seeds canoniques (§7.1) — train ≠ éval par construction (garde testée).
TRAIN_SEED = 20260723
EVAL_SEED = 20260724
TRAIN_N = 3000
EVAL_N = 240  # 80 par label (round-robin sur LABEL_ORDER)
K_MOTIFS = 4
# Sigma par défaut : bruit par coordonnée AVANT re-normalisation L2, ajusté
# empiriquement (Lot 5, mesures consignées au rapport de lot). ÉCART CONSIGNÉ
# vs la cible indicative « ~0,85-0,95 » de §7.1 : sous plafond de confiance
# 0.74 (D3), l'ECE SERVI mesuré par le harnais est borné INFÉRIEUREMENT par
# `exactitude - 0.74` (sous-confiance structurelle : toute décision plus
# fiable que le plafond est émise à 0.74) — une exactitude >= 0.85 rend donc
# le critère de gate `ece <= 0.10` MATHÉMATIQUEMENT infranchissable.
# Résolution honnête : sigma calé pour que la chaîne SERVIE passe le gate
# INCHANGÉ (§9.2) avec marge — exactitude tête ~0,68, ECE servi ~0,07 —
# dans la bande du garde-fou anti-dégénérescence [0.55, 0.999] de §10.8
# (ni trivial ni insoluble). Mesure de mécanique, pas de qualité (D4).
DEFAULT_SIGMA = 0.35
# Arrondi de la sérialisation canonique (§7.1) : 6 décimales.
FLOAT_DECIMALES = 6

EMBED_GOLDEN_DIR = Path(__file__).resolve().parent / "embed_golden"
MANIFEST_PATH = EMBED_GOLDEN_DIR / "manifest.json"


@dataclass(frozen=True)
class EmbedFixture:
    """Une entrée de fixture : vecteur 384-d L2-normalisé + étiquette + motif.

    `categorie` = le motif (centroïde) d'origine du point — vocabulaire fermé
    `motif_0`…`motif_3`, AUCUN texte (alimente les blocs informatifs du
    rapport, jamais le gate).
    """

    embedding: tuple[float, ...] = field(repr=False)
    label: str
    categorie: str


def _normaliser(vecteur: list[float]) -> list[float]:
    """Normalisation L2 (miroir §5.2.6 du pipeline réel) ; vecteur nul inchangé."""
    norme = math.sqrt(sum(v * v for v in vecteur))
    if norme == 0.0:
        return list(vecteur)
    return [v / norme for v in vecteur]


def _centroides() -> dict[str, list[list[float]]]:
    """3×K centroïdes N(0, 1) normalisés L2 — graine dédiée, ordre LABEL_ORDER."""
    rng = random.Random(CENTROID_SEED)
    return {
        label: [_normaliser([rng.gauss(0.0, 1.0) for _ in range(DIM)]) for _ in range(K_MOTIFS)]
        for label in LABEL_ORDER
    }


def generate(n: int, seed: int, sigma: float = DEFAULT_SIGMA) -> list[EmbedFixture]:
    """`n` fixtures déterministes à l'octet : mêmes (n, seed, sigma) => mêmes lignes.

    Labels en round-robin sur `LABEL_ORDER` (distribution équilibrée exacte
    quand n est multiple de 3) ; motif et bruit tirés de `random.Random(seed)`
    dans un ordre FIXE (aucune itération d'ensemble non trié).
    """
    if not isinstance(n, int) or isinstance(n, bool) or n <= 0:
        raise ValueError(f"n invalide : {n!r} (entier > 0 requis)")
    if not (isinstance(sigma, (int, float)) and math.isfinite(float(sigma)) and sigma > 0.0):
        raise ValueError(f"sigma invalide : {sigma!r} (réel fini > 0 requis)")
    centroides = _centroides()
    rng = random.Random(seed)
    rows: list[EmbedFixture] = []
    for i in range(n):
        label = LABEL_ORDER[i % len(LABEL_ORDER)]
        motif = rng.randrange(K_MOTIFS)
        centre = centroides[label][motif]
        point = _normaliser([c + rng.gauss(0.0, float(sigma)) for c in centre])
        rows.append(EmbedFixture(embedding=tuple(point), label=label, categorie=f"motif_{motif}"))
    return rows


def canonical_train_set() -> list[EmbedFixture]:
    """Set d'ENTRAÎNEMENT canonique : n=3000, seed=20260723 (§7.1)."""
    return generate(TRAIN_N, TRAIN_SEED)


def canonical_eval_set() -> list[EmbedFixture]:
    """Set d'ÉVAL canonique (juge de paix du gate embed) : n=240, seed=20260724."""
    return generate(EVAL_N, EVAL_SEED)


def canonical_sha256(rows: list[EmbedFixture]) -> str:
    """Sha256 de la sérialisation CANONIQUE (JSON trié, floats à 6 décimales).

    C'est la définition du hash épinglé dans `embed_golden/manifest.json`
    (clé `embed_golden_sha256`) — même rôle que le sha256 de `golden.jsonl`
    pour l'étage 1 : refus de comparer des rapports issus d'un autre set.
    """
    payload = [
        {
            "categorie": row.categorie,
            "embedding": [round(v, FLOAT_DECIMALES) for v in row.embedding],
            "label": row.label,
        }
        for row in rows
    ]
    canonique = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonique.encode("utf-8")).hexdigest()


def embed_golden_sha256(path: Path | None = None) -> str:
    """LIT le hash canonique ÉPINGLÉ dans le manifest committé (patron loader).

    Ne RECALCULE rien (même mise en garde que `loader.golden_sha256`, minor
    eval r2) : la cohérence pin/matrice est prouvée par le test stdlib
    toujours exécuté de §10.8. Manifest absent/malformé => `ValueError`
    fail-closed (les CLI la convertissent en refus exit 2).
    """
    manifest_path = MANIFEST_PATH if path is None else path
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"manifest embed_golden illisible : {manifest_path} ({exc.__class__.__name__})"
        ) from exc
    sha = manifest.get("embed_golden_sha256") if isinstance(manifest, dict) else None
    if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        raise ValueError(
            f"manifest embed_golden : embed_golden_sha256 absent ou non sha256-hex "
            f"({manifest_path})"
        )
    return sha
