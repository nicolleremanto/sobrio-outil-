"""Générateur DÉTERMINISTE du corpus synthétique « entreprise française » (chantier R4).

Objectif : démarrage à froid de l'étage 1 (classifieur gradient boosting,
`docs/decisions/ROUTEUR_CLASSIFIEUR.md`) — un corpus de 20 000 à 50 000
lignes de SIGNAUX BRUTS (défaut 30 000, `--n`), aucun texte de prompt nulle
part (règle n°1, CLAUDE.md), format EXACT du schéma `Signals`
(`sobrio_router.types`).

Module autonome (pas de paquet installé) : importé soit en script direct
(`python router/data/generate_corpus.py`), soit par les tests
(`router/tests/test_router_data_corpus.py`), qui ajoutent `router/data/` à
`sys.path` — même convention que `router/eval/loader.py`. Ce module insère
lui-même `router/eval/` dans `sys.path` (voir plus bas) pour devenir
GOLDEN-AWARE (correction M1, ronde 0) : il importe `loader.golden_signatures`
pour RE-TIRER, PENDANT la génération, toute ligne dont la signature de
signaux coïnciderait avec le golden — jamais les VALEURS du golden, seule la
fonction de hachage (`loader.signal_signature`) est partagée.

── Anti-fuite ET anti-contradiction PAR CONSTRUCTION (M1 + M3) ──────────────
Deux gardes actives PENDANT la génération de chaque ligne (voir `generate()`,
`_MAX_RETIRAGE_ATTEMPTS`) :

1. **Anti-fuite (M1)** : si la signature de signaux d'une ligne candidate
   coïncide EXACTEMENT avec une entrée du golden set (`loader.golden_signatures()`),
   la ligne est RE-TIRÉE (nouveau jitter, même flux `rng` continué — flux
   DÉRIVÉ déterministe, pas un nouveau seed) jusqu'à `_MAX_RETIRAGE_ATTEMPTS`
   tentatives ; au-delà, la ligne est ABANDONNÉE (comptée, jamais silencieuse).
   Cette garde rend le docstring VRAI par construction (avant cette
   correction, l'affirmation « aucun chevauchement possible » n'était pas
   vérifiée au N livré — voir ledger R4 ronde 0).
2. **Anti-contradiction (M3)** : le générateur maintient une table
   signature → label VÉRITÉ (le label du gabarit, AVANT toute bascule de
   bruit) au fil de la génération ; toute ligne dont la signature coïnciderait
   avec une signature déjà vue mais un label VÉRITÉ différent (gabarits
   différents, parfois cross-catégorie) est également RE-TIRÉE puis, au-delà
   du plafond, ABANDONNÉE. Les SEULES contradictions qui subsistent dans le
   corpus livré sont celles introduites ENSUITE, volontairement, par le flux
   de bruit contrôlé (`--bruit`, voir plus bas) — jamais des contradictions
   structurelles entre gabarits. `quality_report.py` mesure les deux
   catégories séparément via l'annexe `corpus-v1.bruit.json`.

── Indépendance training/éval : gabarits ET re-tirage, PAS le seed seul ────
Le seed par défaut (4242) est DÉLIBÉRÉMENT DIFFÉRENT du seed du golden set
(2026, `router/eval/golden/generate_golden.py`), mais ce n'est PAS ce qui
garantit l'absence de chevauchement — un seed différent réduit la
PROBABILITÉ de collision, il ne l'élimine pas (deux flux aléatoires
indépendants peuvent, par pur hasard, produire la même signature). Ce qui
élimine RÉELLEMENT le chevauchement, c'est la conjonction de deux mécanismes
STRUCTURELS : (a) des gabarits distincts, reformulés au fond, jamais copiés
ni paraphrasés (catégories reprises, scénarios indépendants) — qui rend la
collision rare ; (b) la garde anti-fuite ci-dessus, qui RE-TIRE activement
toute collision résiduelle plutôt que de compter sur la rareté seule — qui
rend la collision impossible au N livré (garantie vérifiée par le test
`test_no_exact_signal_signature_overlap_with_golden`, régénéré AU N LIVRÉ,
30 000 lignes, pas un échantillon réduit). Le seed différent reste une
précaution SUPPLÉMENTAIRE contre une corrélation d'échantillonnage plus
subtile (biais de tirage commun aux deux flux, même sans collision exacte de
signature) entre les données d'entraînement et le juge de paix (gate R3) :
deux flux indépendants, deux seeds indépendants, ceinture ET bretelles.

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
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

# Module autonome (cf. docstring) : insère `router/eval/` en tête de
# `sys.path` pour devenir GOLDEN-AWARE (M1) — idempotent si déjà inséré par
# l'appelant (tests). Doit précéder l'import de `loader`.
_EVAL_DIR = str(Path(__file__).resolve().parents[1] / "eval")
if _EVAL_DIR not in sys.path:
    sys.path.insert(0, _EVAL_DIR)

from loader import golden_signatures, signal_signature  # noqa: E402

from sobrio_router import VISIBLE_MODELS  # noqa: E402

__version__ = "1.1.0"

DEFAULT_N = 30_000
DEFAULT_SEED = 4242
DEFAULT_BRUIT_RATE = 0.03
# Décalage du flux de bruit — voir note de module ci-dessus (isolation des
# deux sources de variation : signaux vs. bascule d'étiquette).
_BRUIT_SEED_OFFSET = 1_000_003
# Plafond de tentatives de re-tirage (M1 anti-fuite, M3 anti-contradiction) :
# au-delà, la ligne est ABANDONNÉE plutôt que de boucler indéfiniment — cf.
# docstring de module et `generate()`.
_MAX_RETIRAGE_ATTEMPTS = 50

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
#
# `note` (M2, correction ronde 0) : formulation STRUCTURELLE — paramètres,
# plages, rôle statistique du gabarit dans sa catégorie — JAMAIS une scène
# narrative façon golden (`generate_golden.py`). Vérifié par script dédié
# (`_verifier_notes_distinctes`, exécuté par les tests et en CLI) : aucune
# chaîne EXACTE en commun avec les notes du golden.
# ---------------------------------------------------------------------------
TEMPLATES: tuple[_Template, ...] = (
    # === redaction_simple ======================================================
    _Template(
        "redaction_simple",
        "claude-haiku-4-5",
        18,
        "ancre basse de la catégorie : token_est 20-80, zéro paramètre de style imposé — "
        "poids dominant (18), fixe le mode le plus fréquent de la cellule haiku.",
        token_est=(20, 80),
    ),
    _Template(
        "redaction_simple",
        "claude-haiku-4-5",
        14,
        "variante confirmation/logistique, même plage courte (20-70 tok.) que l'ancre ci-dessus "
        "mais contenu factuel figé — élargit la cellule haiku sans changer son centre.",
        token_est=(20, 70),
    ),
    _Template(
        "redaction_simple",
        "claude-haiku-4-5",
        8,
        "réplique EN de la cellule haiku (lang_weights fixé à en), plage 15-50 tok. — assure "
        "un plancher non-fr dans une catégorie majoritairement fr (poids mineur 8).",
        token_est=(15, 50),
        lang_weights=_LANG_EN_FIXED,
    ),
    _Template(
        "redaction_simple",
        "claude-sonnet-5",
        18,
        "saut de palier motivé par une contrainte de registre (précision institutionnelle "
        "imposée), token_est 150-350 : au-delà de la plage haiku sans franchir le seuil opus.",
        token_est=(150, 350),
    ),
    _Template(
        "redaction_simple",
        "claude-sonnet-5",
        16,
        "seconde variante sonnet : contrainte de style EXPLICITE (paramètre distinctif de "
        "cette cellule) plutôt qu'un simple effet de longueur, token_est 300-550.",
        token_est=(300, 550),
    ),
    _Template(
        "redaction_simple",
        "claude-sonnet-5",
        8,
        "réplique EN de la cellule sonnet (lang_weights fixé à en), token_est 80-200, même "
        "paramètre de contrainte-style que la variante fr — poids mineur symétrique.",
        token_est=(80, 200),
        lang_weights=_LANG_EN_FIXED,
    ),
    _Template(
        "redaction_simple",
        "claude-opus-4-8",
        5,
        "seule cellule opus de la catégorie, poids MINIMAL (5) par construction (plafond de "
        "sobriété) : token_est 200-450, réservée aux cas où l'enjeu institutionnel dépasse "
        "structurellement le périmètre nominal de la catégorie — jamais un remplissage.",
        token_est=(200, 450),
    ),
    # === resume =================================================================
    _Template(
        "resume",
        "claude-haiku-4-5",
        20,
        "ancre basse : token_est 100-300, poids maximal de la catégorie (20) — centre de masse "
        "de la cellule haiku, aucun paramètre conversationnel actif.",
        token_est=(100, 300),
        keyword_flags=("resume",),
    ),
    _Template(
        "resume",
        "claude-haiku-4-5",
        16,
        "second point de la cellule haiku, plage légèrement décalée (120-320 tok.) — élargit "
        "la dispersion sans introduire de nouveau paramètre catégoriel.",
        token_est=(120, 320),
        keyword_flags=("resume",),
    ),
    _Template(
        "resume",
        "claude-haiku-4-5",
        8,
        "réplique EN (lang_weights=en) de la cellule haiku, token_est 100-260, poids mineur — "
        "plancher non-fr symétrique aux autres catégories.",
        token_est=(100, 260),
        keyword_flags=("resume",),
        lang_weights=_LANG_EN_FIXED,
    ),
    _Template(
        "resume",
        "claude-sonnet-5",
        20,
        "franchissement de palier par LONGUEUR SEULE : token_est 900-1400 franchit le seuil "
        "haut, PLAFONNÉ sonnet (jamais opus pour le seul volume, cf. tête de module).",
        token_est=(900, 1400),
        keyword_flags=("resume",),
    ),
    _Template(
        "resume",
        "claude-sonnet-5",
        18,
        "franchissement de palier par NATURE (paramètre distinct du précédent) : token_est "
        "200-500, plage moyenne mais exige un traitement au-delà de la transformation légère.",
        token_est=(200, 500),
        keyword_flags=("resume",),
    ),
    _Template(
        "resume",
        "claude-sonnet-5",
        12,
        "seule cellule à fil non-vierge de la catégorie (msg_count 5-9, current_model=haiku) : "
        "isole l'effet du paramètre conversationnel du volume brut de prompt (150-300 tok. "
        "moins que l'ancre haiku ci-dessus en tokens de contexte cumulés).",
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
        "seule cellule opus, poids mineur (6) : token_est 400-700 — paramètre distinctif = "
        "sortie attendue au format recommandation argumentée, pas une simple compression.",
        token_est=(400, 700),
        keyword_flags=("resume",),
    ),
    # === extraction =============================================================
    _Template(
        "extraction",
        "claude-haiku-4-5",
        22,
        "ancre basse, poids maximal (22) : token_est 70-220, sortie strictement structurée, "
        "aucun paramètre de contexte étendu.",
        token_est=(70, 220),
    ),
    _Template(
        "extraction",
        "claude-haiku-4-5",
        16,
        "test anti-volume dédié : msg_count 16-28 / tok_per_msg 220-340 (contexte élevé) mais "
        "token_est prompt réduit (60-150) — isole le paramètre volume du paramètre difficulté.",
        token_est=(60, 150),
        msg_count=(16, 28),
        tok_per_msg=(220, 340),
        current_model_weights=_cm("claude-sonnet-5"),
    ),
    _Template(
        "extraction",
        "claude-haiku-4-5",
        8,
        "réplique EN de l'ancre (lang_weights=en), token_est 60-180, poids mineur symétrique.",
        token_est=(60, 180),
        lang_weights=_LANG_EN_FIXED,
    ),
    _Template(
        "extraction",
        "claude-sonnet-5",
        22,
        "paramètre distinctif = ambiguïté de la source (pas la longueur) : token_est 150-300, "
        "poids égal à l'ancre haiku — cellule sonnet centrale de la catégorie.",
        token_est=(150, 300),
    ),
    _Template(
        "extraction",
        "claude-sonnet-5",
        14,
        "second point sonnet, domaine chiffré/financier, token_est 250-450 — même palier que "
        "le précédent, paramètre de contenu différent (discernement quantitatif).",
        token_est=(250, 450),
    ),
    _Template(
        "extraction",
        "claude-opus-4-8",
        10,
        "cellule opus n°1 : drapeau `contrat` actif, token_est 400-700 — la QUALIFICATION du "
        "risque (au-delà de la localisation mécanique) est le paramètre qui monte le palier.",
        token_est=(400, 700),
        keyword_flags=("contrat",),
    ),
    _Template(
        "extraction",
        "claude-opus-4-8",
        4,
        "cellule opus n°2, poids résiduel (4) : drapeau `analyse` actif, token_est 500-800, "
        "source multi-documents — second paramètre indépendant du premier (signal faible vs "
        "clause à risque), garantit ≥ 2 gabarits opus distincts pour la catégorie.",
        token_est=(500, 800),
        keyword_flags=("analyse",),
    ),
    # === traduction ==============================================================
    _Template(
        "traduction",
        "claude-haiku-4-5",
        22,
        "ancre basse, poids maximal (22) : token_est 80-300, aucune contrainte de fidélité "
        "stylistique — plafond haiku par défaut de la catégorie.",
        token_est=(80, 300),
        keyword_flags=("traduction",),
    ),
    _Template(
        "traduction",
        "claude-haiku-4-5",
        10,
        "réplique EN de l'ancre (source en, lang_weights=en), token_est 60-250, poids mineur.",
        token_est=(60, 250),
        keyword_flags=("traduction",),
        lang_weights=_LANG_EN_FIXED,
    ),
    _Template(
        "traduction",
        "claude-sonnet-5",
        20,
        "franchissement par LONGUEUR SEULE (paramètre identique au cas resume) : token_est "
        "900-1300, PLAFONNÉ sonnet — le volume ne fait jamais monter à opus.",
        token_est=(900, 1300),
        keyword_flags=("traduction",),
    ),
    _Template(
        "traduction",
        "claude-sonnet-5",
        18,
        "franchissement par NATURE : token_est 80-200 (court) mais paramètre de préservation "
        "de forme (registre/jeu de mots) actif — la longueur seule ne l'aurait pas justifié.",
        token_est=(80, 200),
        keyword_flags=("traduction",),
    ),
    _Template(
        "traduction",
        "claude-sonnet-5",
        14,
        "seule cellule à fil non-vierge (msg_count 4-7, current_model=haiku) : isole l'effet "
        "conversationnel, token_est 300-600, registre administratif standard.",
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
        "double drapeau (traduction+contrat) EN, token_est 300-600 — contrôle de cohérence "
        "interne du set : la sensibilité terminologique ne franchit PAS le plafond sonnet de "
        "la catégorie (transformation, pas rédaction juridique de fond).",
        token_est=(300, 600),
        keyword_flags=("traduction", "contrat"),
        lang_weights=_LANG_EN_FIXED,
    ),
    _Template(
        "traduction",
        "claude-opus-4-8",
        6,
        "seule cellule opus, poids mineur (6) : token_est 200-450 — paramètre distinctif = "
        "sortie CRÉATIVE/stratégique, sort du périmètre transformation-fidèle de la catégorie.",
        token_est=(200, 450),
        keyword_flags=("traduction",),
    ),
    # === code ====================================================================
    _Template(
        "code",
        "claude-haiku-4-5",
        16,
        "ancre basse : token_est 10-40, un seul point de syntaxe — plancher de la catégorie.",
        token_est=(10, 40),
        has_code=True,
        keyword_flags=("code",),
    ),
    _Template(
        "code",
        "claude-haiku-4-5",
        4,
        "réplique EN de l'ancre (lang_weights=en), token_est 10-35, poids résiduel (4).",
        token_est=(10, 35),
        has_code=True,
        keyword_flags=("code",),
        lang_weights=_LANG_EN_FIXED,
    ),
    _Template(
        "code",
        "claude-sonnet-5",
        22,
        "cellule sonnet dominante (22) : token_est 150-400, correction d'un défaut logique — "
        "paramètre = présence d'un bug identifié, pas la taille du fichier.",
        token_est=(150, 400),
        has_code=True,
        keyword_flags=("code",),
    ),
    _Template(
        "code",
        "claude-sonnet-5",
        10,
        "réplique EN de la cellule précédente (lang_weights=en), token_est 150-350.",
        token_est=(150, 350),
        has_code=True,
        keyword_flags=("code",),
        lang_weights=_LANG_EN_FIXED,
    ),
    _Template(
        "code",
        "claude-sonnet-5",
        16,
        "second point sonnet, paramètre = production (pas correction), token_est 150-350 avec "
        "exigence de robustesse (gestion d'erreurs) explicite.",
        token_est=(150, 350),
        has_code=True,
        keyword_flags=("code",),
    ),
    _Template(
        "code",
        "claude-sonnet-5",
        12,
        "troisième point sonnet, paramètre = relecture (pas écriture), token_est 300-600 — "
        "volume plus élevé par nature de la tâche (fichier entier), pas par choix de palier.",
        token_est=(300, 600),
        has_code=True,
        keyword_flags=("code",),
    ),
    _Template(
        "code",
        "claude-opus-4-8",
        12,
        "cellule opus n°1, fil non-vierge (msg_count 10-18, seen_code=True, current_model="
        "sonnet) : token_est 400-900 — paramètre = contraintes MULTIPLES simultanées sur la "
        "structure logicielle, pas le volume du fil.",
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
        "cellule opus n°2, fil vierge, token_est 250-550 — second paramètre indépendant du "
        "premier (non-déterminisme temporel plutôt que contraintes structurelles), garantit "
        "≥ 2 gabarits opus distincts.",
        token_est=(250, 550),
        has_code=True,
        keyword_flags=("code",),
    ),
    # === maths_raisonnement ======================================================
    _Template(
        "maths_raisonnement",
        "claude-haiku-4-5",
        18,
        "ancre basse : token_est 15-50, une seule opération/conversion — plancher haiku.",
        token_est=(15, 50),
        has_math=True,
    ),
    _Template(
        "maths_raisonnement",
        "claude-haiku-4-5",
        6,
        "réplique EN de l'ancre (lang_weights=en), token_est 15-45, poids résiduel (6).",
        token_est=(15, 45),
        has_math=True,
        lang_weights=_LANG_EN_FIXED,
    ),
    _Template(
        "maths_raisonnement",
        "claude-sonnet-5",
        20,
        "cellule sonnet dominante (20) : token_est 120-300, paramètre = enchaînement de "
        "plusieurs opérations avec risque d'erreur cumulée.",
        token_est=(120, 300),
        has_math=True,
    ),
    _Template(
        "maths_raisonnement",
        "claude-sonnet-5",
        16,
        "second point sonnet, registre scolaire, token_est 150-350 — même paramètre "
        "multi-étapes que le précédent, domaine différent.",
        token_est=(150, 350),
        has_math=True,
    ),
    _Template(
        "maths_raisonnement",
        "claude-sonnet-5",
        10,
        "réplique EN de la cellule sonnet (lang_weights=en), token_est 150-300.",
        token_est=(150, 300),
        has_math=True,
        lang_weights=_LANG_EN_FIXED,
    ),
    _Template(
        "maths_raisonnement",
        "claude-sonnet-5",
        14,
        "quatrième point sonnet, domaine combinatoire/optimisation, token_est 100-250 — "
        "paramètre = structure du problème plutôt que calcul arithmétique pur.",
        token_est=(100, 250),
        has_math=True,
    ),
    _Template(
        "maths_raisonnement",
        "claude-opus-4-8",
        16,
        "seule cellule opus, poids élevé (16, cf. maths ~17% de la catégorie, référence "
        "interne pour l'étalonnage des autres catégories) : token_est 150-400, paramètre = "
        "originalité de la démonstration, pas sa longueur.",
        token_est=(150, 400),
        has_math=True,
    ),
    # === juridique_contrat =======================================================
    # Rééquilibrage M4 (correction ronde 0, data-quality) : la part opus de
    # cette catégorie était à 39,6 % (poids 20+10+10=40/100) — DEUX FOIS le
    # ratio des autres catégories à cellule opus dense (code 20,7 %, maths
    # 17 %, cf. les gabarits ci-dessus). Rationnel du nouveau poids cible
    # (~20/100 = 20 %, soit environ 1 dossier juridique sur 5, PAS 2 sur 5) :
    # l'examen d'un contrat franchit RAREMENT le seuil opus dans un flux
    # d'entreprise réel — la majorité des contrats (types, gabarits connus)
    # relève d'une relecture/rédaction standard (sonnet) ; seule une clause
    # AMBIGUË à fort enjeu, une négociation multi-parties, ou une analyse
    # cross-juridictions exigent réellement le palier le plus capable. Fixer
    # opus à 40 % aurait fait de la catégorie une exception statistique sans
    # justification de fond (mission sobriété du chantier) — le poids retiré
    # (20 points) est redistribué à sonnet (relecture/rédaction standard),
    # PAS à haiku (la vérification mécanique reste, elle, une minorité
    # honnête de la catégorie, inchangée à 20 %).
    _Template(
        "juridique_contrat",
        "claude-haiku-4-5",
        16,
        "ancre basse : token_est 80-200, contrôle de PRÉSENCE d'une clause nommée — pas "
        "d'interprétation requise.",
        token_est=(80, 200),
        keyword_flags=("contrat",),
    ),
    _Template(
        "juridique_contrat",
        "claude-haiku-4-5",
        4,
        "second point haiku, poids résiduel (4) : contrôle de conformité sur un référentiel "
        "fixe (RGPD), token_est 100-250 — même nature mécanique que l'ancre.",
        token_est=(100, 250),
        keyword_flags=("contrat",),
    ),
    _Template(
        "juridique_contrat",
        "claude-sonnet-5",
        32,
        "cellule sonnet dominante (32/100, cf. rééquilibrage M4 ci-dessus) : token_est "
        "320-550, relecture d'un contrat au gabarit connu, aucune clause hors norme.",
        token_est=(320, 550),
    ),
    _Template(
        "juridique_contrat",
        "claude-sonnet-5",
        28,
        "second point sonnet (28/100) : token_est 350-600, production d'une clause à partir "
        "d'un modèle existant — paramètre PRODUCTION plutôt que relecture, même palier.",
        token_est=(350, 600),
    ),
    _Template(
        "juridique_contrat",
        "claude-opus-4-8",
        10,
        "cellule opus n°1, poids réduit (10/100, cf. rééquilibrage M4) : token_est 500-900, "
        "paramètre = ambiguïté de clause à fort enjeu — le CAS RARE qui justifie réellement "
        "le palier le plus capable, pas le défaut de la catégorie.",
        token_est=(500, 900),
        keyword_flags=("contrat", "analyse"),
    ),
    _Template(
        "juridique_contrat",
        "claude-opus-4-8",
        5,
        "cellule opus n°2, poids minimal (5/100) : EN, fil non-vierge (msg_count 10-16, "
        "seen_reasoning=True, current_model=opus), token_est 600-900 — paramètre = "
        "MULTI-JURIDICTIONS, indépendant du paramètre du gabarit précédent.",
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
        5,
        "cellule opus n°3, poids minimal (5/100) : fil non-vierge (msg_count 15-25, "
        "seen_reasoning=True, current_model=opus), token_est 700-950 — paramètre = "
        "MULTI-PARTIES, troisième source indépendante de justification opus de la catégorie.",
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
        "prompt court (token_est 5-15) mais fil déjà porteur d'un raisonnement mathématique "
        "(seen_math/seen_reasoning=True, msg_count 4-10) — paramètre CONVERSATIONNEL, pas le "
        "prompt lui-même, qui pilote le palier.",
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
        "variante code : fil porteur (seen_code=True, msg_count 4-9), prompt court "
        "(token_est 10-40) — même structure paramétrique que le gabarit précédent, domaine "
        "différent.",
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
        "test anti-volume dédié : msg_count 25-45 (le plus élevé du set), token_est prompt "
        "modéré (150-400) — isole le paramètre volume de contexte du paramètre difficulté, "
        "PLAFONNÉ sonnet par construction.",
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
        "paramètre dérogations ÉLEVÉ (derogations_up 3-6) avec recos_followed_ratio BAS "
        "(0.15-0.4) — profil utilisateur qui s'écarte fréquemment de la recommandation "
        "affichée, token_est 200-400.",
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
        "fil long (msg_count 16-26) mais tok_per_msg FAIBLE (15-40, le plus bas du set) — "
        "paramètre = densité d'échange légère malgré le volume de tours, token_est 15-45.",
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
        "paramètre recos_followed_ratio ÉLEVÉ (0.75-0.95, symétrique du gabarit "
        "dérogations-élevées ci-dessus), token_est 200-400 — profil qui suit largement les "
        "recommandations affichées.",
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
        "double paramètre conversationnel (seen_code ET seen_math simultanés), token_est "
        "400-700 modéré — combinaison de deux domaines qui reste, PAR CONSTRUCTION du set, "
        "dans le palier intermédiaire (aucun des deux domaines n'est individuellement à un "
        "niveau de complexité opus ici).",
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
        "current_model=opus (le plus capable déjà en cours) avec prompt minimal (token_est "
        "10-35, msg_count 3-6) — teste la borne basse indépendamment du modèle courant du "
        "fil : le paramètre PROMPT prime sur le paramètre current_model.",
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
        "cellule opus n°1 : combinaison seen_math+seen_reasoning+msg_count élevé (15-25) — "
        "trois paramètres CONVERSATIONNELS simultanés distincts, pas un effet de volume seul "
        "(token_est modéré 300-600).",
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
        "cellule opus n°2, poids résiduel (4) : drapeaux contrat+analyse combinés à un fil "
        "juridique déjà dense (msg_count 14-22, current_model=opus) — second paramètre "
        "indépendant du premier (domaine juridique vs mathématique), garantit ≥ 2 gabarits "
        "opus distincts pour la catégorie.",
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

    Garde interne (M7, correction ronde 0) : `total < 0` levait un défaut
    SILENCIEUX — `remainder = total - sum(base.values())` devenait négatif et
    `order[:remainder]` (slicing négatif Python : compte depuis la FIN de la
    liste) attribuait le reste aux MAUVAISES clés sans jamais lever d'erreur.
    Prouvé par exécution (`_allocate(-3, {"a": 1, "b": 1})` retournait un
    résultat plausible mais faux). `total == 0` reste valide (retourne toutes
    les clés à 0) : seul un total négatif est un abus d'appel.
    """
    if total < 0:
        raise ValueError(f"_allocate : total doit être >= 0 (reçu {total!r})")
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


_GOLDEN_DIR = Path(__file__).resolve().parents[1] / "eval" / "golden"


def _verifier_golden_fige(golden_dir: Path = _GOLDEN_DIR) -> None:
    """Garde de couplage : RECALCULE le sha256 des octets de golden.jsonl et le
    compare au sha COMMITTÉ (1er champ de GOLDEN_SHA256, format shasum).

    Correction ronde 2 (major dq+eval+qa, prouvé par expérience) : la version
    ronde 1 comparait `golden_sha256()` — qui LIT le fichier GOLDEN_SHA256 —
    au même fichier lu directement : une tautologie (`x != x`) incapable de
    détecter une dérive réelle de golden.jsonl. Ici le hash est recalculé
    sur les OCTETS COURANTS : un golden.jsonl modifié sans re-figeage fait
    échouer la génération bruyamment, jamais en silence.
    """
    sha_attendu = (golden_dir / "GOLDEN_SHA256").read_text(encoding="utf-8").split()[0]
    sha_octets = hashlib.sha256((golden_dir / "golden.jsonl").read_bytes()).hexdigest()
    if sha_octets != sha_attendu:
        raise RuntimeError(
            f"golden.jsonl a dérivé (octets {sha_octets[:12]}… != {sha_attendu[:12]}… "
            "committé) — garde anti-fuite invalidée, génération refusée"
        )


def _attribuer_abandon(fails_anti_fuite: int, fails_contradiction: int) -> str:
    """Cause DOMINANTE de l'historique d'échecs d'une ligne abandonnée (r1) ;
    égalité → anti_fuite (la garde la plus critique). Extrait pour être
    testable unitairement (minor eval/qa r2 : chemin latent, 0 abandon réel).
    """
    return "contradiction" if fails_contradiction > fails_anti_fuite else "anti_fuite"


def generate(n: int, seed: int = DEFAULT_SEED, bruit_rate: float = DEFAULT_BRUIT_RATE):
    """Engendre jusqu'à `n` lignes de corpus + les statistiques associées.

    Un SEUL flux `random.Random(seed)` pour les signaux (ordre : catégories
    triées alphabétiquement, puis gabarits dans l'ordre de `TEMPLATES`, puis
    instances) + un flux DÉDIÉ `random.Random(seed + _BRUIT_SEED_OFFSET)`
    pour le bruit d'étiquetage (isolation documentée en tête de module).
    Reproductible à l'octet près : deux appels avec le même `(n, seed,
    bruit_rate)` produisent des listes STRICTEMENT identiques.

    Anti-fuite (M1) + anti-contradiction (M3) : chaque ligne candidate est
    RE-TIRÉE (nouveaux tirages consommés sur le MÊME flux `rng`, donc
    toujours déterministe) tant que sa signature (a) coïncide avec le golden
    set ou (b) contredit le label VÉRITÉ déjà associé à cette signature dans
    CE run — jusqu'à `_MAX_RETIRAGE_ATTEMPTS` tentatives, au-delà desquelles
    la ligne est ABANDONNÉE (comptée, jamais silencieuse — voir les
    compteurs `n_rejets_anti_fuite`/`n_rejets_contradiction`/`n_abandons_*`
    du rapport de stats). Le bruit d'étiquetage n'est appliqué qu'APRÈS
    acceptation d'une ligne, sur le label VÉRITÉ déjà enregistré — les
    contradictions qu'il introduit ensuite sont donc TOUJOURS attribuables
    au bruit contrôlé, jamais à un défaut structurel du générateur.

    Lève `ValueError` si `n <= 0` ou `bruit_rate` hors `[0, 1]` (M7) — la CLI
    (`main()`) valide ces mêmes contraintes en amont avec un message propre.
    """
    if n <= 0:
        raise ValueError(f"n doit être un entier > 0 (reçu {n!r})")
    if not (0.0 <= bruit_rate <= 1.0):
        raise ValueError(f"bruit_rate doit être dans [0, 1] (reçu {bruit_rate!r})")

    _valider_templates()
    rng = random.Random(seed)
    rng_bruit = random.Random(seed + _BRUIT_SEED_OFFSET)
    _verifier_golden_fige()
    golden_sigs = golden_signatures()

    by_category: dict[str, list[_Template]] = {}
    for t in TEMPLATES:
        by_category.setdefault(t.category, []).append(t)

    cat_counts = _allocate(n, CATEGORY_WEIGHTS)

    rows: list[dict] = []
    bruit_appliques = 0
    n_rejets_anti_fuite = 0
    n_rejets_contradiction = 0
    n_abandons_anti_fuite = 0
    n_abandons_contradiction = 0
    signature_labels: dict[tuple, str] = {}

    for category in sorted(CATEGORY_WEIGHTS):
        templates = by_category[category]
        tmpl_weights = {i: t.weight for i, t in enumerate(templates)}
        tmpl_counts = _allocate(cat_counts[category], tmpl_weights)
        for i, template in enumerate(templates):
            for _ in range(tmpl_counts[i]):
                accepted: dict | None = None
                accepted_sig: tuple | None = None
                fails_anti_fuite = 0
                fails_contradiction = 0
                for _attempt in range(_MAX_RETIRAGE_ATTEMPTS):
                    candidate = _build_row(rng, template)
                    sig = signal_signature(
                        candidate["signals"]["prompt"], candidate["signals"]["conversation"]
                    )
                    if sig in golden_sigs:
                        n_rejets_anti_fuite += 1
                        fails_anti_fuite += 1
                        continue
                    label_existant = signature_labels.get(sig)
                    if label_existant is not None and label_existant != candidate["label"]:
                        n_rejets_contradiction += 1
                        fails_contradiction += 1
                        continue
                    accepted, accepted_sig = candidate, sig
                    break

                if accepted is None:
                    if _attribuer_abandon(fails_anti_fuite, fails_contradiction) == "contradiction":
                        n_abandons_contradiction += 1
                    else:
                        n_abandons_anti_fuite += 1
                    continue

                # Label VÉRITÉ enregistré AVANT toute bascule de bruit (M3) :
                # les contradictions du bruit contrôlé ne polluent jamais
                # cette table, seule source de vérité anti-contradiction.
                signature_labels.setdefault(accepted_sig, accepted["label"])

                is_bruit = rng_bruit.random() < bruit_rate
                if is_bruit:
                    # `sorted(...)` : VISIBLE_MODELS est un frozenset, son ordre
                    # d'itération dépend du hash randomization (PYTHONHASHSEED,
                    # différent par PROCESSUS) — sans tri explicite, `rng_bruit.choice`
                    # piocherait un index déterministe dans un ORDRE non déterministe,
                    # cassant la reproductibilité inter-run (§5.6). Piège découvert et
                    # corrigé pendant la vérification empirique du déterminisme.
                    autres = [m for m in sorted(VISIBLE_MODELS) if m != accepted["label"]]
                    accepted = {**accepted, "label": rng_bruit.choice(autres)}
                    bruit_appliques += 1
                accepted["_bruit"] = is_bruit
                rows.append(accepted)

    rng.shuffle(rows)

    final_rows: list[dict] = []
    bruit_ids: list[str] = []
    for i, row in enumerate(rows, start=1):
        row_id = f"corp-{i:06d}"
        is_bruit = row.pop("_bruit")
        final_rows.append({"id": row_id, **row})
        if is_bruit:
            bruit_ids.append(row_id)

    stats = _compute_stats(
        final_rows,
        seed,
        bruit_rate,
        bruit_appliques,
        n_rejets_anti_fuite=n_rejets_anti_fuite,
        n_rejets_contradiction=n_rejets_contradiction,
        n_abandons_anti_fuite=n_abandons_anti_fuite,
        n_abandons_contradiction=n_abandons_contradiction,
    )
    # `bruit_ids` (3e valeur) : liste des ids EFFECTIVEMENT bruités — annexe
    # `corpus-v1.bruit.json` écrite par `main()` (M3b), JAMAIS dans le corpus
    # ni dans `stats` (évite d'alourdir `router/data/reference/*.stats.json`
    # d'une liste ~ n*bruit_rate ids à chaque régénération de référence).
    return final_rows, stats, bruit_ids


def _compute_stats(
    rows: list[dict],
    seed: int,
    bruit_rate: float,
    bruit_appliques: int,
    *,
    n_rejets_anti_fuite: int = 0,
    n_rejets_contradiction: int = 0,
    n_abandons_anti_fuite: int = 0,
    n_abandons_contradiction: int = 0,
) -> dict:
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
        # M1 (anti-fuite) + M3 (anti-contradiction), correction ronde 0 : voir
        # docstring de `generate()`. > 0 est ATTENDU sur un grand corpus (des
        # collisions résiduelles surviennent, re-tirées) ; `n_abandons_*` > 0
        # signalerait un plafond de tentatives trop bas (à surveiller, pas
        # une erreur en soi tant que la proportion reste négligeable vs `n`).
        "n_rejets_anti_fuite": n_rejets_anti_fuite,
        "n_rejets_contradiction": n_rejets_contradiction,
        "n_abandons_anti_fuite": n_abandons_anti_fuite,
        "n_abandons_contradiction": n_abandons_contradiction,
        "n_abandons": n_abandons_anti_fuite + n_abandons_contradiction,
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
    """CLI — validations FAIL-CLOSED (M7) : message propre + exit 2, jamais de traceback brut."""
    parser = argparse.ArgumentParser(
        description="Génère le corpus synthétique R4 (démarrage à froid, étage 1)."
    )
    parser.add_argument(
        "--n",
        type=int,
        default=DEFAULT_N,
        help=(
            f"nombre de lignes (défaut {DEFAULT_N}) — doit être > 0 ; plage livrable "
            "TYPIQUE 20 000-50 000 (démarrage à froid, cf. docstring du module), non "
            "imposée par ce garde-fou"
        ),
    )
    parser.add_argument(
        "--seed", type=int, default=DEFAULT_SEED, help=f"graine (défaut {DEFAULT_SEED})"
    )
    parser.add_argument(
        "--bruit",
        type=float,
        default=DEFAULT_BRUIT_RATE,
        help=(
            f"taux de bruit d'étiquetage dans [0, 1], 0 pour désactiver "
            f"(défaut {DEFAULT_BRUIT_RATE})"
        ),
    )
    parser.add_argument("--out-dir", type=Path, default=ARTIFACTS_DIR, help="répertoire de sortie")
    args = parser.parse_args(argv)

    if args.n <= 0:
        print(f"--n doit être un entier > 0 (reçu {args.n})", file=sys.stderr)
        return 2
    if not (0.0 <= args.bruit <= 1.0):
        print(f"--bruit doit être dans [0, 1] (reçu {args.bruit})", file=sys.stderr)
        return 2

    try:
        args.out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"--out-dir invalide ({args.out_dir}) : {exc}", file=sys.stderr)
        return 2

    rows, stats, bruit_ids = generate(args.n, args.seed, args.bruit)

    corpus_path = args.out_dir / "corpus-v1.jsonl.gz"
    metadata_path = args.out_dir / "corpus-v1.metadata.json"
    stats_path = args.out_dir / "corpus-v1.stats.json"
    bruit_path = args.out_dir / "corpus-v1.bruit.json"

    sha = _write_gz(corpus_path, rows)

    metadata = {
        "seed": args.seed,
        "n": len(rows),
        "generator_version": __version__,
        "generator": "router/data/generate_corpus.py",
        "sha256_gz": sha,
        "date_generation": datetime.now(tz=UTC).isoformat(),
        "bruit_rate_parametre": args.bruit,
        "n_rejets_anti_fuite": stats["n_rejets_anti_fuite"],
        "n_rejets_contradiction": stats["n_rejets_contradiction"],
        "n_abandons": stats["n_abandons"],
        "invariant_5_6": (
            "seed fixé, version épinglée (generator_version), sha256 committé pour ce run — "
            "reproductible via : python router/data/generate_corpus.py "
            f"--n {args.n} --seed {args.seed} --bruit {args.bruit}"
        ),
        "seed_different_du_golden": (
            f"seed={args.seed} volontairement DIFFÉRENT du seed=2026 du golden set "
            "(router/eval/golden/generate_golden.py) — précaution SUPPLÉMENTAIRE contre une "
            "corrélation d'échantillonnage fine avec le juge de paix (chantier R2/R3) ; "
            "l'absence de chevauchement EXACT n'en dépend PAS (elle vient des gabarits "
            "indépendants ET de la garde anti-fuite par re-tirage, cf. docstring du module — "
            "corrigé ronde 0, M1)."
        ),
    }
    metadata_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    stats_path.write_text(json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    bruit_annexe = {
        "avertissement": (
            "ANNEXE (M3) — ids des lignes dont le label a été basculé par le bruit contrôlé "
            "(`--bruit`) : PAS dans le corpus lui-même (schéma des lignes inchangé), consommée "
            "par quality_report.py SI PRÉSENTE pour ventiler contradictions bruit/hors-bruit."
        ),
        "bruit_rate_parametre": args.bruit,
        "n_bruit": len(bruit_ids),
        "bruit_ids": bruit_ids,
    }
    bruit_path.write_text(
        json.dumps(bruit_annexe, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(f"corpus-v1.jsonl.gz : {stats['n']} lignes -> {corpus_path}")
    print(f"par catégorie : {stats['by_category']}")
    print(f"par étiquette : {stats['by_label']}")
    print(f"part FR : {stats['fr_share']:.1%}")
    print(f"bruit effectif : {stats['bruit_rate_effectif']:.2%}")
    print(f"doublons de signature : {stats['taux_doublons_signature']:.2%}")
    print(
        f"anti-fuite : {stats['n_rejets_anti_fuite']} rejets, "
        f"{stats['n_abandons_anti_fuite']} abandons"
    )
    print(
        f"anti-contradiction : {stats['n_rejets_contradiction']} rejets, "
        f"{stats['n_abandons_contradiction']} abandons"
    )
    print(f"sha256 : {sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
