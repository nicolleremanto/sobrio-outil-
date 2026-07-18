"""Générateur DÉTERMINISTE du corpus synthétique « entreprise française » (chantier R4).

Objectif : démarrage à froid de l'étage 1 (classifieur gradient boosting,
`docs/decisions/ROUTEUR_CLASSIFIEUR.md`) — un corpus de 20 000 à 50 000
lignes de SIGNAUX BRUTS (défaut 30 000, `--n`), aucun texte de prompt nulle
part (règle n°1, CLAUDE.md), format EXACT du schéma `Signals`
(`sobrio_router.types`).

Module autonome (pas de paquet installé) : importé soit en script direct
(`python router/data/generate_corpus.py`), soit par les tests
(`router/tests/test_router_data_corpus.py`), qui ajoutent `router/data/` à
`sys.path` — même convention que `router/eval/loader.py`.

── Seed (4242) ──────────────────────────────────────────────────────────────
Le seed par défaut (4242) est DÉLIBÉRÉMENT DIFFÉRENT du seed du golden set
(2026, `router/eval/golden/generate_golden.py`). Motif : même si aucun
chevauchement direct n'est possible par construction (gabarits distincts,
espace d'ids disjoint `corp-*` / préfixe du golden (`router/eval/golden/`),
catégories reprises mais scénarios
reformulés — jamais copiés ni paraphrasés), partager un seed avec le juge de
paix créerait une CORRÉLATION D'ÉCHANTILLONNAGE inutile et risquée entre les
données d'entraînement et l'ensemble qui départage les candidats (gate R3) :
un biais de génération commun aux deux (même tirage de jitter, mêmes
coïncidences numériques) pourrait artificiellement gonfler l'accord
entraînement↔évaluation sans rapport avec la qualité réelle du classifieur.
Deux flux indépendants, deux seeds indépendants.

── Principes d'étiquetage (PRINCIPES DE FOND, PAS des entrées reprises) ─────
Comme le golden (même mandat, cf. `generate_golden.py` et
`docs/decisions/ROUTEUR_CLASSIFIEUR.md`) : le champ `label` de chaque gabarit
est le modèle LE MOINS CHER qui SUFFIT RÉELLEMENT à la nature de la tâche
décrite (sobriété), jugé au fond — jamais le résultat de `HeuristicRouter`.
Principes réutilisés (reformulés ici, aucune entrée du golden n'est copiée
ni paraphrasée) :

- **Rédaction** : brève, factuelle, sans contrainte de ton/style → haiku.
  Contrainte de ton/voix de marque précise, ou longueur significative →
  sonnet. Enjeu institutionnel majeur exigeant une stratégie rhétorique fine
  (crise, changement stratégique) → opus (rare).
- **Résumé / traduction** (« transformations légères », guides fournisseurs) :
  courts et à faible risque → haiku ; longs → PLAFOND sonnet, jamais un
  palier supérieur simplement pour le volume. Un très petit nombre de cas
  limites dépasse la transformation légère au fond (synthèse stratégique
  exigeant un jugement expert et des recommandations argumentées ;
  localisation créative d'une campagne à fort enjeu de marque, qui n'est
  plus une traduction littérale) → opus, gardé RARE et documenté.
- **Extraction** : mécanique (même sur un contexte volumineux — le volume
  seul ne fait jamais monter de palier) → haiku ; avec interprétation
  d'informations ambiguës → sonnet ; qualification de signaux à fort enjeu
  dans un document dense (contrat, audit) → opus.
- **Code** : question triviale → haiku ; débogage/génération de complexité
  moyenne → sonnet ; conception d'architecture multi-contraintes ou
  diagnostic causal profond (concurrence, bug intermittent) → opus.
- **Maths/raisonnement** : conversion/calcul trivial → haiku ; calcul ou
  exercice à plusieurs étapes → sonnet ; démonstration profonde et
  originale → opus.
- **Juridique/contrat** : vérification mécanique d'une clause → haiku ;
  relecture/rédaction standard → sonnet ; analyse fine à fort enjeu ou
  multi-juridictions, négociation complexe → opus.
- **Multi-tours** : dérive des signaux de CONVERSATION (contexte vu, modèle
  courant, dérogations) — même principe qu'au fond : le VOLUME de contexte
  seul ne fait jamais monter de palier ; seule la NATURE de la tâche
  poursuivie (preuve profonde continuée, risques juridiques croisés) le fait.

**Divergence assumée vis-à-vis du golden** : le golden laisse VOLONTAIREMENT
vides certaines cellules catégorie×label par principe de sobriété
(`redaction_simple`/opus, `resume`/opus, `traduction`/opus — voir
`coverage_report.json`, `limites_statistiques.cellules_vides_par_design`).
Ce corpus, lui, VISE une couverture catégorie×label complète (données
d'ENTRAÎNEMENT : un classifieur a besoin d'exemples, même rares, dans
chaque cellule pour apprendre la frontière) : les quelques gabarits opus des
catégories « légères » ci-dessus sont documentés, tenus RARES (poids
minimes), et restent des jugements de fond honnêtes sur un scénario qui
dépasse réellement le périmètre nominal de sa catégorie — jamais un
remplissage artificiel.

── Bruit d'étiquetage (`--bruit`) ───────────────────────────────────────────
Réalisme : ~2-4 % des lignes reçoivent une étiquette VOLONTAIREMENT erronée
(un autre modèle visible, tiré uniformément parmi les deux restants), pour
simuler l'imperfection d'un étiquetage réel (erreur humaine, ambiguïté de
bord). Flux ALÉATOIRE DÉDIÉ (`random.Random(seed + _BRUIT_SEED_OFFSET)`),
indépendant du flux qui tire les signaux eux-mêmes : changer `--bruit` ne
change JAMAIS les signaux générés, seulement quelles lignes voient leur
étiquette basculée — propriété volontaire (isolation des deux sources de
variation).

── Registres d'entreprise ───────────────────────────────────────────────────
`_REGISTERS` module des tailles d'organisation × intensités d'usage
(TPE/PME occasionnelle → grand groupe intensif) : multiplie les signaux de
CONVERSATION (nombre de messages, contexte, recommandations, dérogations) —
jamais les signaux de PROMPT (la longueur d'une tâche dépend de sa nature,
pas de la taille de l'organisation qui la pose). Ce registre n'apparaît PAS
dans les signaux de sortie (il n'existe pas dans le schéma `Signals`) : c'est
un paramètre de génération interne, pas un champ du corpus.

Aucune dépendance externe (stdlib seule, cf. `router/pyproject.toml`) :
gzip+json only, décision disque (pas de pandas/pyarrow).
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import random
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sobrio_router import VISIBLE_MODELS

__version__ = "1.0.0"

DEFAULT_N = 30_000
DEFAULT_SEED = 4242
DEFAULT_BRUIT_RATE = 0.03
# Décalage du flux de bruit — voir note de module ci-dessus (isolation des
# deux sources de variation : signaux vs. bascule d'étiquette).
_BRUIT_SEED_OFFSET = 1_000_003

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"

_ALLOWED_FLAGS = frozenset({"contrat", "analyse", "code", "resume", "traduction", "demonstration"})
_ALLOWED_LANGS = frozenset({"fr", "en", "other"})

# Poids RELATIFS des 8 catégories (reprises du golden, cf. note de module) —
# proportions plausibles de trafic « entreprise française » : multi_tours et
# code dominent (conversations en cours, développement), maths_raisonnement
# et juridique_contrat sont plus rares en usage quotidien moyen. Normalisés
# à 1.0 mais l'allocation (`_allocate`) fonctionne avec n'importe quels poids
# positifs (pas besoin d'une somme exacte à 1.0).
CATEGORY_WEIGHTS: dict[str, float] = {
    "redaction_simple": 0.16,
    "resume": 0.12,
    "extraction": 0.12,
    "traduction": 0.10,
    "code": 0.14,
    "maths_raisonnement": 0.08,
    "juridique_contrat": 0.10,
    "multi_tours": 0.18,
}


@dataclass(frozen=True)
class _Register:
    """Un registre d'entreprise : taille d'organisation × intensité d'usage.

    Multiplie les BORNES des signaux de conversation d'un gabarit (jamais
    les signaux de prompt) — voir note de module.
    """

    name: str
    weight: float
    msg_mult: tuple[float, float]
    context_mult: tuple[float, float]
    recos_mult: tuple[float, float]
    derog_mult: tuple[float, float]


_REGISTERS: tuple[_Register, ...] = (
    _Register("tpe_pme_occasionnel", 0.32, (0.5, 0.9), (0.5, 0.9), (0.4, 0.8), (0.3, 0.8)),
    _Register("pme_regulier", 0.33, (0.8, 1.15), (0.8, 1.15), (0.8, 1.2), (0.7, 1.2)),
    _Register("eti_intensif", 0.22, (1.0, 1.35), (1.0, 1.4), (1.0, 1.5), (0.9, 1.5)),
    _Register("grand_groupe_intensif", 0.13, (1.1, 1.6), (1.1, 1.7), (1.1, 1.8), (1.0, 1.8)),
)


def _cm(dominant: str | None, other_weight: float = 0.15) -> tuple[tuple[str | None, float], ...]:
    """Distribution de `current_model` : `dominant` majoritaire, ou fil vierge (`None`)."""
    if dominant is None:
        return ((None, 1.0),)
    others = [m for m in sorted(VISIBLE_MODELS) if m != dominant]
    return ((dominant, 1.0 - other_weight * len(others)), *((m, other_weight) for m in others))


_LANG_FR_MAJ = (("fr", 0.80), ("en", 0.16), ("other", 0.04))
_LANG_EN_FIXED = (("en", 1.0),)


@dataclass(frozen=True)
class _Template:
    """Un gabarit de scénario : engendre des lignes par jitter seedé + registre d'entreprise.

    `weight` est RELATIF au sein de sa catégorie (pas un pourcentage absolu,
    normalisé par `_allocate`). `note` décrit la CLASSE de scénario de façon
    abstraite (aucun texte de prompt, règle n°1) — jamais une entrée reprise
    du golden.
    """

    category: str
    label: str
    weight: float
    note: str
    token_est: tuple[int, int]
    char_len_factor: tuple[float, float] = (3.4, 4.6)
    has_code: bool = False
    has_math: bool = False
    keyword_flags: tuple[str, ...] = ()
    lang_weights: tuple[tuple[str, float], ...] = _LANG_FR_MAJ
    msg_count: tuple[int, int] = (0, 0)
    tok_per_msg: tuple[int, int] = (0, 0)
    seen_code: bool = False
    seen_math: bool = False
    seen_reasoning: bool = False
    current_model_weights: tuple[tuple[str | None, float], ...] = ((None, 1.0),)
    recos_shown: tuple[int, int] = (0, 0)
    recos_followed_ratio: tuple[float, float] = (0.0, 0.0)
    derogations_up: tuple[int, int] = (0, 0)


# ---------------------------------------------------------------------------
# Gabarits, groupés par catégorie (mêmes 8 catégories que le golden set).
# ---------------------------------------------------------------------------
TEMPLATES: tuple[_Template, ...] = (
    # === redaction_simple =====================================================
    _Template(
        "redaction_simple",
        "claude-haiku-4-5",
        18,
        "e-mail interne bref à un collègue, ton neutre, sujet routinier (congés, logistique).",
        token_est=(20, 80),
    ),
    _Template(
        "redaction_simple",
        "claude-haiku-4-5",
        14,
        "message client court de confirmation (rendez-vous, commande), factuel.",
        token_est=(20, 70),
    ),
    _Template(
        "redaction_simple",
        "claude-haiku-4-5",
        8,
        "short informal status update to a colleague, routine subject, English.",
        token_est=(15, 50),
        lang_weights=_LANG_EN_FIXED,
    ),
    _Template(
        "redaction_simple",
        "claude-sonnet-5",
        18,
        "note de service à diffusion large, ton institutionnel précis à respecter.",
        token_est=(150, 350),
    ),
    _Template(
        "redaction_simple",
        "claude-sonnet-5",
        16,
        "offre d'emploi rédigée avec la voix de marque de l'entreprise, contrainte stylistique "
        "explicite.",
        token_est=(300, 550),
    ),
    _Template(
        "redaction_simple",
        "claude-sonnet-5",
        8,
        "product landing copy with a specific brand-voice constraint, English.",
        token_est=(80, 200),
        lang_weights=_LANG_EN_FIXED,
    ),
    _Template(
        "redaction_simple",
        "claude-opus-4-8",
        5,
        "discours institutionnel à très fort enjeu (crise, changement stratégique majeur), "
        "stratégie rhétorique fine et anticipation des réactions parties prenantes requises.",
        token_est=(200, 450),
    ),
    # === resume ================================================================
    _Template(
        "resume",
        "claude-haiku-4-5",
        20,
        "résumé bref d'un compte-rendu de réunion interne standard.",
        token_est=(100, 300),
        keyword_flags=("resume",),
    ),
    _Template(
        "resume",
        "claude-haiku-4-5",
        16,
        "résumé court d'une revue de presse sectorielle courante.",
        token_est=(120, 320),
        keyword_flags=("resume",),
    ),
    _Template(
        "resume",
        "claude-haiku-4-5",
        8,
        "brief summary of a routine status report, English.",
        token_est=(100, 260),
        keyword_flags=("resume",),
        lang_weights=_LANG_EN_FIXED,
    ),
    _Template(
        "resume",
        "claude-sonnet-5",
        20,
        "résumé long d'un rapport d'audit dense, au-delà du seuil de longueur.",
        token_est=(900, 1400),
        keyword_flags=("resume",),
    ),
    _Template(
        "resume",
        "claude-sonnet-5",
        18,
        "résumé exigeant une interprétation nuancée d'un document de veille concurrentielle.",
        token_est=(200, 500),
        keyword_flags=("resume",),
    ),
    _Template(
        "resume",
        "claude-sonnet-5",
        12,
        "résumé d'une note technique moyenne, fil déjà engagé mais léger.",
        token_est=(300, 600),
        keyword_flags=("resume",),
        msg_count=(5, 9),
        tok_per_msg=(40, 90),
        current_model_weights=_cm("claude-haiku-4-5"),
    ),
    _Template(
        "resume",
        "claude-opus-4-8",
        6,
        "synthèse stratégique multi-sources exigeant une mise en perspective experte et des "
        "recommandations argumentées — dépasse le simple résumé.",
        token_est=(400, 700),
        keyword_flags=("resume",),
    ),
    # === extraction =============================================================
    _Template(
        "extraction",
        "claude-haiku-4-5",
        22,
        "extraction de champs structurés (dates, montants, références) depuis un document court.",
        token_est=(70, 220),
    ),
    _Template(
        "extraction",
        "claude-haiku-4-5",
        16,
        "extraction mécanique d'une liste d'éléments dans un fil de discussion déjà volumineux "
        "— tâche simple malgré le volume de contexte.",
        token_est=(60, 150),
        msg_count=(16, 28),
        tok_per_msg=(220, 340),
        current_model_weights=_cm("claude-sonnet-5"),
    ),
    _Template(
        "extraction",
        "claude-haiku-4-5",
        8,
        "structured extraction of contact details from a short block of text, English.",
        token_est=(60, 180),
        lang_weights=_LANG_EN_FIXED,
    ),
    _Template(
        "extraction",
        "claude-sonnet-5",
        22,
        "extraction avec interprétation d'informations ambiguës ou implicites, texte de longueur "
        "moyenne.",
        token_est=(150, 300),
    ),
    _Template(
        "extraction",
        "claude-sonnet-5",
        14,
        "extraction de tendances chiffrées depuis un rapport financier moyen, discernement requis.",
        token_est=(250, 450),
    ),
    _Template(
        "extraction",
        "claude-opus-4-8",
        10,
        "extraction et qualification de clauses à risque dans un contrat dense à fort enjeu.",
        token_est=(400, 700),
        keyword_flags=("contrat",),
    ),
    _Template(
        "extraction",
        "claude-opus-4-8",
        4,
        "extraction de signaux faibles dans un dossier d'audit interne multi-documents, "
        "jugement expert requis.",
        token_est=(500, 800),
        keyword_flags=("analyse",),
    ),
    # === traduction ==============================================================
    _Template(
        "traduction",
        "claude-haiku-4-5",
        22,
        "traduction courte et standard d'un texte simple, sans exigence stylistique.",
        token_est=(80, 300),
        keyword_flags=("traduction",),
    ),
    _Template(
        "traduction",
        "claude-haiku-4-5",
        10,
        "short routine translation of a simple sentence, English source.",
        token_est=(60, 250),
        keyword_flags=("traduction",),
        lang_weights=_LANG_EN_FIXED,
    ),
    _Template(
        "traduction",
        "claude-sonnet-5",
        20,
        "traduction longue d'un document technique, au-delà du seuil de longueur.",
        token_est=(900, 1300),
        keyword_flags=("traduction",),
    ),
    _Template(
        "traduction",
        "claude-sonnet-5",
        18,
        "traduction courte mais littéraire, préservation du ton et des jeux de mots.",
        token_est=(80, 200),
        keyword_flags=("traduction",),
    ),
    _Template(
        "traduction",
        "claude-sonnet-5",
        14,
        "traduction administrative de longueur moyenne, fil déjà présent mais léger.",
        token_est=(300, 600),
        keyword_flags=("traduction",),
        msg_count=(4, 7),
        tok_per_msg=(60, 120),
        current_model_weights=_cm("claude-haiku-4-5"),
    ),
    _Template(
        "traduction",
        "claude-sonnet-5",
        10,
        "official terminology-sensitive translation of moderate length, English — reste une "
        "traduction (transformation à faible risque) : le modèle intermédiaire suffit.",
        token_est=(300, 600),
        keyword_flags=("traduction", "contrat"),
        lang_weights=_LANG_EN_FIXED,
    ),
    _Template(
        "traduction",
        "claude-opus-4-8",
        6,
        "localisation intégrale d'une campagne multilingue à fort enjeu de marque — dépasse la "
        "traduction littérale, réinvention créative et stratégique du message.",
        token_est=(200, 450),
        keyword_flags=("traduction",),
    ),
    # === code ====================================================================
    _Template(
        "code",
        "claude-haiku-4-5",
        16,
        "question de code triviale, syntaxe d'une ligne.",
        token_est=(10, 40),
        has_code=True,
        keyword_flags=("code",),
    ),
    _Template(
        "code",
        "claude-haiku-4-5",
        4,
        "trivial one-line syntax question, English.",
        token_est=(10, 35),
        has_code=True,
        keyword_flags=("code",),
        lang_weights=_LANG_EN_FIXED,
    ),
    _Template(
        "code",
        "claude-sonnet-5",
        22,
        "débogage d'une fonction de taille moyenne avec erreur logique non triviale.",
        token_est=(150, 400),
        has_code=True,
        keyword_flags=("code",),
    ),
    _Template(
        "code",
        "claude-sonnet-5",
        10,
        "moderate debugging of a medium-sized function, English.",
        token_est=(150, 350),
        has_code=True,
        keyword_flags=("code",),
        lang_weights=_LANG_EN_FIXED,
    ),
    _Template(
        "code",
        "claude-sonnet-5",
        16,
        "génération d'un script utilitaire de complexité moyenne avec gestion d'erreurs.",
        token_est=(150, 350),
        has_code=True,
        keyword_flags=("code",),
    ),
    _Template(
        "code",
        "claude-sonnet-5",
        12,
        "revue de code standard sur un fichier de taille moyenne.",
        token_est=(300, 600),
        has_code=True,
        keyword_flags=("code",),
    ),
    _Template(
        "code",
        "claude-opus-4-8",
        12,
        "conception d'une architecture logicielle complexe multi-contraintes, fil déjà engagé "
        "avec du code vu précédemment.",
        token_est=(400, 900),
        has_code=True,
        keyword_flags=("code",),
        msg_count=(10, 18),
        tok_per_msg=(150, 300),
        seen_code=True,
        current_model_weights=_cm("claude-sonnet-5"),
    ),
    _Template(
        "code",
        "claude-opus-4-8",
        8,
        "diagnostic d'un bug de concurrence subtil et intermittent en système distribué, "
        "raisonnement causal profond requis.",
        token_est=(250, 550),
        has_code=True,
        keyword_flags=("code",),
    ),
    # === maths_raisonnement ======================================================
    _Template(
        "maths_raisonnement",
        "claude-haiku-4-5",
        18,
        "conversion d'unité ou calcul trivial.",
        token_est=(15, 50),
        has_math=True,
    ),
    _Template(
        "maths_raisonnement",
        "claude-haiku-4-5",
        6,
        "trivial unit conversion, English.",
        token_est=(15, 45),
        has_math=True,
        lang_weights=_LANG_EN_FIXED,
    ),
    _Template(
        "maths_raisonnement",
        "claude-sonnet-5",
        20,
        "calcul à plusieurs étapes avec risque réel d'erreur de calcul.",
        token_est=(120, 300),
        has_math=True,
    ),
    _Template(
        "maths_raisonnement",
        "claude-sonnet-5",
        16,
        "exercice de mathématiques de niveau lycée à plusieurs étapes.",
        token_est=(150, 350),
        has_math=True,
    ),
    _Template(
        "maths_raisonnement",
        "claude-sonnet-5",
        10,
        "multi-step reasoning problem requiring careful logic, English.",
        token_est=(150, 300),
        has_math=True,
        lang_weights=_LANG_EN_FIXED,
    ),
    _Template(
        "maths_raisonnement",
        "claude-sonnet-5",
        14,
        "problème de logique métier de difficulté moyenne (planification, optimisation simple).",
        token_est=(100, 250),
        has_math=True,
    ),
    _Template(
        "maths_raisonnement",
        "claude-opus-4-8",
        16,
        "démonstration mathématique profonde et originale, plusieurs étapes de preuve rigoureuse.",
        token_est=(150, 400),
        has_math=True,
    ),
    # === juridique_contrat =======================================================
    _Template(
        "juridique_contrat",
        "claude-haiku-4-5",
        16,
        "vérification mécanique de la présence d'une clause précise dans un contrat court.",
        token_est=(80, 200),
        keyword_flags=("contrat",),
    ),
    _Template(
        "juridique_contrat",
        "claude-haiku-4-5",
        4,
        "contrôle de conformité RGPD basique sur une clause standard de traitement de données.",
        token_est=(100, 250),
        keyword_flags=("contrat",),
    ),
    _Template(
        "juridique_contrat",
        "claude-sonnet-5",
        22,
        "relecture standard d'un contrat type sans clause inhabituelle, longueur moyenne.",
        token_est=(320, 550),
    ),
    _Template(
        "juridique_contrat",
        "claude-sonnet-5",
        18,
        "rédaction d'une clause contractuelle standard à partir d'un modèle connu.",
        token_est=(350, 600),
    ),
    _Template(
        "juridique_contrat",
        "claude-opus-4-8",
        20,
        "analyse fine de clauses contractuelles ambiguës à fort enjeu, longueur importante.",
        token_est=(500, 900),
        keyword_flags=("contrat", "analyse"),
    ),
    _Template(
        "juridique_contrat",
        "claude-opus-4-8",
        10,
        "cross-jurisdiction contract risk analysis at high stakes, English, fil déjà engagé.",
        token_est=(600, 900),
        keyword_flags=("contrat", "analyse"),
        lang_weights=_LANG_EN_FIXED,
        msg_count=(10, 16),
        tok_per_msg=(200, 350),
        seen_reasoning=True,
        current_model_weights=_cm("claude-opus-4-8"),
    ),
    _Template(
        "juridique_contrat",
        "claude-opus-4-8",
        10,
        "négociation contractuelle complexe multi-parties, analyse juridique poussée, fil "
        "déjà engagé.",
        token_est=(700, 950),
        keyword_flags=("contrat", "analyse"),
        msg_count=(15, 25),
        tok_per_msg=(200, 350),
        seen_reasoning=True,
        current_model_weights=_cm("claude-opus-4-8"),
    ),
    # === multi_tours (signaux de conversation VARIÉS) ============================
    _Template(
        "multi_tours",
        "claude-sonnet-5",
        14,
        "prompt très bref demandant le détail des étapes du raisonnement, fil déjà engagé sur "
        "une démonstration mathématique.",
        token_est=(5, 15),
        keyword_flags=("demonstration",),
        msg_count=(4, 10),
        tok_per_msg=(60, 150),
        seen_math=True,
        seen_reasoning=True,
        current_model_weights=_cm("claude-haiku-4-5"),
        recos_shown=(1, 3),
        recos_followed_ratio=(0.3, 0.7),
        derogations_up=(0, 1),
    ),
    _Template(
        "multi_tours",
        "claude-sonnet-5",
        14,
        "fil déjà engagé sur du code, nouvelle demande de correction ponctuelle et brève.",
        token_est=(10, 40),
        msg_count=(4, 9),
        tok_per_msg=(80, 180),
        seen_code=True,
        current_model_weights=_cm("claude-sonnet-5"),
        recos_shown=(1, 3),
        recos_followed_ratio=(0.5, 0.9),
        derogations_up=(0, 1),
    ),
    _Template(
        "multi_tours",
        "claude-sonnet-5",
        12,
        "fil déjà très long et dense, nouvelle demande de synthèse générale recoupant "
        "l'ensemble des échanges — la synthèse dense reste du ressort du modèle intermédiaire, "
        "le volume seul ne fait pas monter de palier.",
        token_est=(150, 400),
        msg_count=(25, 45),
        tok_per_msg=(200, 320),
        current_model_weights=_cm("claude-sonnet-5"),
        recos_shown=(2, 5),
        recos_followed_ratio=(0.4, 0.8),
        derogations_up=(0, 2),
    ),
    _Template(
        "multi_tours",
        "claude-sonnet-5",
        10,
        "nouvelle question de synthèse argumentée après plusieurs dérogations utilisateur vers "
        "un modèle plus capable que la recommandation précédente.",
        token_est=(200, 400),
        msg_count=(8, 14),
        tok_per_msg=(80, 150),
        current_model_weights=_cm("claude-haiku-4-5"),
        recos_shown=(6, 10),
        recos_followed_ratio=(0.15, 0.4),
        derogations_up=(3, 6),
    ),
    _Template(
        "multi_tours",
        "claude-haiku-4-5",
        14,
        "fil informel et déjà long, échanges courts et légers, nouvelle question factuelle "
        "brève et anodine.",
        token_est=(15, 45),
        msg_count=(16, 26),
        tok_per_msg=(15, 40),
        current_model_weights=_cm("claude-haiku-4-5"),
        recos_shown=(3, 7),
        recos_followed_ratio=(0.3, 0.6),
        derogations_up=(0, 2),
    ),
    _Template(
        "multi_tours",
        "claude-sonnet-5",
        10,
        "fil où les recommandations précédentes ont été largement suivies, nouvelle demande de "
        "rédaction de longueur moyenne.",
        token_est=(200, 400),
        msg_count=(8, 14),
        tok_per_msg=(60, 120),
        current_model_weights=_cm("claude-sonnet-5"),
        recos_shown=(8, 14),
        recos_followed_ratio=(0.75, 0.95),
        derogations_up=(0, 1),
    ),
    _Template(
        "multi_tours",
        "claude-sonnet-5",
        8,
        "fil mixte déjà engagé sur code et maths, nouvelle question combinant les deux "
        "domaines de façon soutenue — prompt et contexte modestes, périmètre du modèle "
        "intermédiaire.",
        token_est=(400, 700),
        msg_count=(10, 18),
        tok_per_msg=(100, 200),
        seen_code=True,
        seen_math=True,
        current_model_weights=_cm("claude-sonnet-5"),
        recos_shown=(2, 5),
        recos_followed_ratio=(0.3, 0.7),
        derogations_up=(0, 2),
    ),
    _Template(
        "multi_tours",
        "claude-haiku-4-5",
        8,
        "fil bref déjà sur le modèle le plus capable, nouvelle question de clarification très "
        "courte et triviale.",
        token_est=(10, 35),
        msg_count=(3, 6),
        tok_per_msg=(50, 100),
        current_model_weights=_cm("claude-opus-4-8"),
        recos_shown=(1, 3),
        recos_followed_ratio=(0.5, 1.0),
        derogations_up=(0, 1),
    ),
    _Template(
        "multi_tours",
        "claude-opus-4-8",
        6,
        "fil de démonstration mathématique profonde poursuivi sur de nombreux tours, nouvelle "
        "étape décisive de la preuve exigeant un raisonnement original soutenu — le fond, pas "
        "le volume, justifie le modèle le plus capable.",
        token_est=(300, 600),
        has_math=True,
        keyword_flags=("demonstration",),
        msg_count=(15, 25),
        tok_per_msg=(150, 280),
        seen_math=True,
        seen_reasoning=True,
        current_model_weights=_cm("claude-sonnet-5"),
        recos_shown=(2, 5),
        recos_followed_ratio=(0.4, 0.8),
        derogations_up=(0, 1),
    ),
    _Template(
        "multi_tours",
        "claude-opus-4-8",
        4,
        "fil juridique déjà long et dense, nouvelle demande de synthèse des risques croisés "
        "entre clauses interdépendantes, à fort enjeu — l'interdépendance des risques, pas le "
        "volume, exige le modèle le plus capable.",
        token_est=(300, 600),
        keyword_flags=("contrat", "analyse"),
        msg_count=(14, 22),
        tok_per_msg=(200, 330),
        seen_reasoning=True,
        current_model_weights=_cm("claude-opus-4-8"),
        recos_shown=(2, 5),
        recos_followed_ratio=(0.5, 0.9),
        derogations_up=(0, 1),
    ),
)


def _valider_templates() -> None:
    """Garde-fou : lève AVANT génération si un gabarit est mal formé."""
    categories_vues: dict[str, set[str]] = {}
    for t in TEMPLATES:
        assert t.category in CATEGORY_WEIGHTS, f"catégorie hors registre : {t.category!r}"
        assert t.label in VISIBLE_MODELS, f"étiquette hors catalogue visible : {t.label!r}"
        assert t.weight > 0, f"poids non positif : {t!r}"
        assert set(t.keyword_flags) <= _ALLOWED_FLAGS, f"drapeau inconnu : {t.keyword_flags!r}"
        assert {lang for lang, _ in t.lang_weights} <= _ALLOWED_LANGS, f"langue inattendue : {t!r}"
        for model, _ in t.current_model_weights:
            assert model is None or model in VISIBLE_MODELS, f"current_model invalide : {t!r}"
        categories_vues.setdefault(t.category, set()).add(t.label)
    # Couverture catégorie×label : chaque catégorie doit pouvoir produire les
    # 3 étiquettes (garantit, en amont de `_allocate`, qu'aucune cellule
    # n'est vide PAR CONCEPTION — divergence assumée vis-à-vis du golden,
    # voir la note de module).
    for category in CATEGORY_WEIGHTS:
        labels = categories_vues.get(category, set())
        assert labels == VISIBLE_MODELS, f"couverture incomplète en {category} : {labels}"


def _allocate(total: int, weights: dict) -> dict:
    """Répartition proportionnelle DÉTERMINISTE (méthode des plus forts restes).

    Pure arithmétique (aucun aléa) : le résultat ne dépend que de `total` et
    `weights`, jamais de l'ordre d'itération du générateur aléatoire —
    l'allocation catégorie/gabarit reste stable indépendamment du seed.
    """
    keys = list(weights)
    total_weight = sum(weights.values())
    raw = {k: total * weights[k] / total_weight for k in keys}
    base = {k: int(raw[k]) for k in keys}
    remainder = total - sum(base.values())
    order = sorted(keys, key=lambda k: raw[k] - base[k], reverse=True)
    for k in order[:remainder]:
        base[k] += 1
    return base


def _weighted_choice(rng: random.Random, options):
    """Tirage pondéré déterministe (seedé par `rng`) parmi `options` = [(valeur, poids), ...]."""
    total = sum(w for _, w in options)
    r = rng.uniform(0, total)
    upto = 0.0
    for value, w in options:
        upto += w
        if r <= upto:
            return value
    return options[-1][0]


def _build_row(rng: random.Random, template: _Template) -> dict:
    """Tire les signaux d'UNE ligne (jitter seedé + registre d'entreprise seedé)."""
    register = _weighted_choice(rng, tuple((r, r.weight) for r in _REGISTERS))

    token_est = rng.randint(*template.token_est)
    factor = rng.uniform(*template.char_len_factor)
    char_len = max(1, round(token_est * factor))
    lang = _weighted_choice(rng, template.lang_weights)
    prompt = {
        "char_len": char_len,
        "token_est": token_est,
        "lang": lang,
        "has_code": template.has_code,
        "has_math": template.has_math,
        "keyword_flags": list(template.keyword_flags),
    }

    msg_lo, msg_hi = template.msg_count
    if msg_hi > 0:
        msg_count = max(0, round(rng.randint(msg_lo, msg_hi) * rng.uniform(*register.msg_mult)))
    else:
        msg_count = 0

    if msg_count > 0 and template.tok_per_msg != (0, 0):
        tok_per_msg = rng.randint(*template.tok_per_msg)
        bruit_ctx = rng.randint(-30, 30)
        context_token_est = max(
            0, round(msg_count * tok_per_msg * rng.uniform(*register.context_mult)) + bruit_ctx
        )
    else:
        context_token_est = 0

    current_model = _weighted_choice(rng, template.current_model_weights)

    # Une recommandation ne peut s'afficher qu'à un tour utilisateur (même
    # garde-fou que `generate_golden.py`) : borne à ceil(msg_count/2).
    max_user_turns = (msg_count + 1) // 2
    if template.recos_shown != (0, 0):
        raw_recos = round(rng.randint(*template.recos_shown) * rng.uniform(*register.recos_mult))
        recos_shown = max(0, min(raw_recos, max_user_turns))
    else:
        recos_shown = 0
    if recos_shown > 0:
        ratio = rng.uniform(*template.recos_followed_ratio)
        recos_followed = min(recos_shown, round(recos_shown * ratio))
    else:
        recos_followed = 0

    if template.derogations_up != (0, 0):
        derogations_up = max(
            0, round(rng.randint(*template.derogations_up) * rng.uniform(*register.derog_mult))
        )
    else:
        derogations_up = 0

    conversation = {
        "msg_count": msg_count,
        "context_token_est": context_token_est,
        "seen_code": template.seen_code,
        "seen_math": template.seen_math,
        "seen_reasoning": template.seen_reasoning,
        "current_model": current_model,
        "recos_shown": recos_shown,
        "recos_followed": recos_followed,
        "derogations_up": derogations_up,
    }
    return {
        "category": template.category,
        "label": template.label,
        "signals": {"prompt": prompt, "conversation": conversation},
    }


def generate(n: int, seed: int = DEFAULT_SEED, bruit_rate: float = DEFAULT_BRUIT_RATE):
    """Engendre `n` lignes de corpus + les statistiques associées.

    Un SEUL flux `random.Random(seed)` pour les signaux (ordre : catégories
    triées alphabétiquement, puis gabarits dans l'ordre de `TEMPLATES`, puis
    instances) + un flux DÉDIÉ `random.Random(seed + _BRUIT_SEED_OFFSET)`
    pour le bruit d'étiquetage (isolation documentée en tête de module).
    Reproductible à l'octet près : deux appels avec le même `(n, seed,
    bruit_rate)` produisent des listes STRICTEMENT identiques.
    """
    _valider_templates()
    rng = random.Random(seed)
    rng_bruit = random.Random(seed + _BRUIT_SEED_OFFSET)

    by_category: dict[str, list[_Template]] = {}
    for t in TEMPLATES:
        by_category.setdefault(t.category, []).append(t)

    cat_counts = _allocate(n, CATEGORY_WEIGHTS)

    rows: list[dict] = []
    bruit_appliques = 0
    for category in sorted(CATEGORY_WEIGHTS):
        templates = by_category[category]
        tmpl_weights = {i: t.weight for i, t in enumerate(templates)}
        tmpl_counts = _allocate(cat_counts[category], tmpl_weights)
        for i, template in enumerate(templates):
            for _ in range(tmpl_counts[i]):
                row = _build_row(rng, template)
                if rng_bruit.random() < bruit_rate:
                    # `sorted(...)` : VISIBLE_MODELS est un frozenset, son ordre
                    # d'itération dépend du hash randomization (PYTHONHASHSEED,
                    # différent par PROCESSUS) — sans tri explicite, `rng_bruit.choice`
                    # piocherait un index déterministe dans un ORDRE non déterministe,
                    # cassant la reproductibilité inter-run (§5.6). Piège découvert et
                    # corrigé pendant la vérification empirique du déterminisme.
                    autres = [m for m in sorted(VISIBLE_MODELS) if m != row["label"]]
                    row = {**row, "label": rng_bruit.choice(autres)}
                    bruit_appliques += 1
                rows.append(row)

    rng.shuffle(rows)
    final_rows = [{"id": f"corp-{i:06d}", **row} for i, row in enumerate(rows, start=1)]

    stats = _compute_stats(final_rows, seed, bruit_rate, bruit_appliques)
    return final_rows, stats


def _compute_stats(rows: list[dict], seed: int, bruit_rate: float, bruit_appliques: int) -> dict:
    n = len(rows)
    by_category: Counter = Counter(r["category"] for r in rows)
    by_label: Counter = Counter(r["label"] for r in rows)
    by_cat_label: dict[str, dict[str, int]] = {}
    by_lang: Counter = Counter()
    token_ests: list[int] = []
    char_lens: list[int] = []
    msg_counts: list[int] = []
    context_tokens: list[int] = []
    recos_shows: list[int] = []
    derogations: list[int] = []
    signatures: Counter = Counter()

    for r in rows:
        by_cat_label.setdefault(r["category"], {})
        by_cat_label[r["category"]][r["label"]] = by_cat_label[r["category"]].get(r["label"], 0) + 1
        p, c = r["signals"]["prompt"], r["signals"]["conversation"]
        by_lang[p["lang"]] += 1
        token_ests.append(p["token_est"])
        char_lens.append(p["char_len"])
        msg_counts.append(c["msg_count"])
        context_tokens.append(c["context_token_est"])
        recos_shows.append(c["recos_shown"])
        derogations.append(c["derogations_up"])
        signatures[json.dumps(r["signals"], sort_keys=True)] += 1

    n_dup = sum(count - 1 for count in signatures.values() if count > 1)

    def _plage(values: list[int]) -> dict | None:
        return {"min": min(values), "max": max(values)} if values else None

    return {
        "n": n,
        "seed": seed,
        "bruit_rate_parametre": bruit_rate,
        "bruit_rate_effectif": round(bruit_appliques / n, 4) if n else 0.0,
        "by_category": dict(sorted(by_category.items())),
        "by_label": dict(sorted(by_label.items())),
        "by_category_x_label": {
            k: dict(sorted(v.items())) for k, v in sorted(by_cat_label.items())
        },
        "by_lang": dict(sorted(by_lang.items())),
        "fr_share": round(by_lang.get("fr", 0) / n, 4) if n else 0.0,
        "plages": {
            "token_est": _plage(token_ests),
            "char_len": _plage(char_lens),
            "msg_count": _plage(msg_counts),
            "context_token_est": _plage(context_tokens),
            "recos_shown": _plage(recos_shows),
            "derogations_up": _plage(derogations),
        },
        "taux_doublons_signature": round(n_dup / n, 4) if n else 0.0,
    }


def _write_gz(path: Path, rows: list[dict]) -> str:
    """Écrit `rows` en JSONL gzippé DÉTERMINISTE (mtime=0 dans l'en-tête gzip).

    Sans `mtime=0`, `gzip.compress` embarque l'horodatage courant dans
    l'en-tête : deux exécutions du même run produiraient des fichiers .gz
    à sha256 DIFFÉRENTS malgré un contenu JSONL identique — casserait le
    test de déterminisme (§5.6, deux runs même seed → sha identique).
    """
    payload = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n"
    compressed = gzip.compress(payload.encode("utf-8"), compresslevel=9, mtime=0)
    path.write_bytes(compressed)
    return hashlib.sha256(compressed).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Génère le corpus synthétique R4 (démarrage à froid, étage 1)."
    )
    parser.add_argument(
        "--n", type=int, default=DEFAULT_N, help=f"nombre de lignes (défaut {DEFAULT_N})"
    )
    parser.add_argument(
        "--seed", type=int, default=DEFAULT_SEED, help=f"graine (défaut {DEFAULT_SEED})"
    )
    parser.add_argument(
        "--bruit",
        type=float,
        default=DEFAULT_BRUIT_RATE,
        help=f"taux de bruit d'étiquetage, 0 pour désactiver (défaut {DEFAULT_BRUIT_RATE})",
    )
    parser.add_argument("--out-dir", type=Path, default=ARTIFACTS_DIR, help="répertoire de sortie")
    args = parser.parse_args(argv)

    rows, stats = generate(args.n, args.seed, args.bruit)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    corpus_path = args.out_dir / "corpus-v1.jsonl.gz"
    metadata_path = args.out_dir / "corpus-v1.metadata.json"
    stats_path = args.out_dir / "corpus-v1.stats.json"

    sha = _write_gz(corpus_path, rows)

    metadata = {
        "seed": args.seed,
        "n": len(rows),
        "generator_version": __version__,
        "generator": "router/data/generate_corpus.py",
        "sha256_gz": sha,
        "date_generation": datetime.now(tz=UTC).isoformat(),
        "bruit_rate_parametre": args.bruit,
        "invariant_5_6": (
            "seed fixé, version épinglée (generator_version), sha256 committé pour ce run — "
            "reproductible via : python router/data/generate_corpus.py "
            f"--n {args.n} --seed {args.seed} --bruit {args.bruit}"
        ),
        "seed_different_du_golden": (
            f"seed={args.seed} volontairement DIFFÉRENT du seed=2026 du golden set "
            "(router/eval/golden/generate_golden.py) — évite toute corrélation "
            "d'échantillonnage avec le juge de paix (chantier R2/R3), cf. docstring du module."
        ),
    }
    metadata_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    stats_path.write_text(json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"corpus-v1.jsonl.gz : {stats['n']} lignes -> {corpus_path}")
    print(f"par catégorie : {stats['by_category']}")
    print(f"par étiquette : {stats['by_label']}")
    print(f"part FR : {stats['fr_share']:.1%}")
    print(f"bruit effectif : {stats['bruit_rate_effectif']:.2%}")
    print(f"doublons de signature : {stats['taux_doublons_signature']:.2%}")
    print(f"sha256 : {sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
