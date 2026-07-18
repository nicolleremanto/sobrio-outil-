"""Générateur DÉTERMINISTE du golden set du routeur Sobrio (chantier R2).

Produit `golden.jsonl` (150-200 lignes) et `coverage_stats.json` à partir
d'une cinquantaine de GABARITS de scénarios réalistes (`GABARITS` ci-dessous).
Chaque gabarit engendre 3-4 instances par jitter numérique SEEDÉ
(`random.Random(SEED)`) — aucun horodatage, aucune source d'aléa externe :
deux exécutions produisent des fichiers strictement identiques.

Principe d'étiquetage (le plus important, cf. `docs/decisions/ROUTEUR_CLASSIFIEUR.md`
et le mandat du chantier R2) : le champ `label` de chaque gabarit est le modèle
LE MOINS CHER qui suffit RÉELLEMENT à la tâche décrite par `note`, jugé au
fond (guides fournisseurs, bon sens produit) — **PAS** le résultat de
`HeuristicRouter`. Le routeur heuristique n'est exécuté qu'APRÈS coup, en
DIAGNOSTIC seul (`_heuristic_agreement`), pour mesurer le taux d'accord et le
consigner dans `coverage_stats.json` — jamais pour décider d'une étiquette.

Le set contient donc, DÉLIBÉRÉMENT et HONNÊTEMENT, des cas où l'heuristique
v0 se trompe probablement (ex. `heuristic:code_context` recommande toujours
Sonnet, même pour une question de code triviale d'une ligne ; `heuristic:
reasoning_context` recommande toujours Sonnet, même pour une démonstration
mathématique profonde qui mérite Opus ; un drapeau lourd `contrat` fait
toujours basculer sur `heuristic:complex_task` → Opus, même pour une
vérification mécanique triviale) — sans pour autant inventer d'erreurs :
chaque étiquette reste un jugement de fond honnête sur le scénario décrit.

RÈGLE N°1 ABSOLUE (CLAUDE.md, `docs/decisions/ROUTEUR_CLASSIFIEUR.md`) :
aucun texte de prompt nulle part. `note` décrit la CLASSE de scénario de
façon abstraite (comme les gabarits eux-mêmes, jamais un prompt cité) ; le
champ `prompt_text` de `PromptSignals` n'est JAMAIS alimenté ici.
"""

from __future__ import annotations

import json
import random
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from sobrio_router import (
    VISIBLE_MODELS,
    ConversationSignals,
    HeuristicRouter,
    PromptSignals,
    Signals,
)

SEED = 2026
OUT_DIR = Path(__file__).resolve().parent
GOLDEN_PATH = OUT_DIR / "golden.jsonl"
STATS_PATH = OUT_DIR / "coverage_stats.json"
REPORT_PATH = OUT_DIR / "coverage_report.json"

# Vocabulaire fermé de `keyword_flags` (RFC-0001 : extension de l'enum v1.0
# `contracts/openapi.yaml` avec `demonstration`, cf. `heuristic.py`).
_ALLOWED_FLAGS = frozenset({"contrat", "analyse", "code", "resume", "traduction", "demonstration"})
_ALLOWED_LANGS = frozenset({"fr", "en"})


@dataclass(frozen=True)
class Gabarit:
    """Un gabarit de scénario : engendre `n_instances` lignes golden par jitter seedé.

    Seuls les champs `*_range` (bornes min/max inclusives) varient d'une
    instance à l'autre — tous les champs catégoriels (drapeaux, `has_code`,
    `seen_*`, `current_model`) sont FIXES par gabarit pour rester cohérents
    avec le scénario décrit par `note`. Les défauts correspondent à un « fil
    vierge » (mêmes valeurs neutres que `ConversationSignals`).
    """

    category: str
    lang: str
    label: str
    note: str
    n_instances: int
    token_est: tuple[int, int]
    char_len_factor: tuple[float, float] = (3.6, 4.4)
    has_code: bool = False
    has_math: bool = False
    keyword_flags: tuple[str, ...] = ()
    msg_count: tuple[int, int] = (0, 0)
    tok_per_msg: tuple[int, int] = (0, 0)
    seen_code: bool = False
    seen_math: bool = False
    seen_reasoning: bool = False
    current_model: str | None = None
    recos_shown: tuple[int, int] = (0, 0)
    recos_followed_ratio: tuple[float, float] = (0.0, 0.0)
    derogations_up: tuple[int, int] = (0, 0)
    # Trace de la double-revue indépendante (R2) : (ml_architect, eval_scientist).
    # "agree" | "amended: <raison>" | "contesté→conservé: <arbitrage>".
    review: tuple[str, str] = ("agree", "agree")


# ---------------------------------------------------------------------------
# Les gabarits, groupés par catégorie (8 catégories ~équilibrées, >60 % fr).
# ---------------------------------------------------------------------------
GABARITS: tuple[Gabarit, ...] = (
    # === redaction_simple (20 instances) =====================================
    Gabarit(
        category="redaction_simple",
        lang="fr",
        label="claude-haiku-4-5",
        note="e-mail professionnel court et factuel, ton neutre, fil vierge.",
        n_instances=4,
        token_est=(30, 90),
    ),
    Gabarit(
        category="redaction_simple",
        lang="fr",
        label="claude-haiku-4-5",
        note="message de remerciement bref à un client, fil vierge, aucune contrainte de style.",
        n_instances=3,
        token_est=(25, 70),
    ),
    Gabarit(
        category="redaction_simple",
        lang="fr",
        label="claude-sonnet-5",
        note=(
            "rédaction créative courte mais exigeante, contrainte de ton et de style précise "
            "à respecter, fil vierge."
        ),
        n_instances=4,
        token_est=(60, 180),
    ),
    Gabarit(
        category="redaction_simple",
        lang="en",
        label="claude-haiku-4-5",
        note=(
            "accroche produit courte et simple, en anglais, fil vierge, aucune exigence "
            "stylistique."
        ),
        n_instances=3,
        token_est=(20, 60),
    ),
    Gabarit(
        category="redaction_simple",
        lang="fr",
        label="claude-sonnet-5",
        note=(
            "annonce de recrutement à la voix de marque distinctive, longueur moyenne, fil vierge."
        ),
        n_instances=3,
        token_est=(320, 480),
    ),
    Gabarit(
        category="redaction_simple",
        lang="en",
        label="claude-haiku-4-5",
        note="légende de réseau social brève et informelle, en anglais, fil vierge.",
        n_instances=3,
        token_est=(15, 50),
    ),
    # === resume (19 instances) ================================================
    Gabarit(
        category="resume",
        lang="fr",
        label="claude-haiku-4-5",
        note="résumé court d'un article de presse ordinaire, fil vierge.",
        n_instances=4,
        token_est=(100, 350),
        keyword_flags=("resume",),
    ),
    Gabarit(
        category="resume",
        lang="fr",
        label="claude-sonnet-5",
        note="résumé long d'un rapport technique dense, au-delà du seuil de longueur, fil vierge.",
        n_instances=3,
        token_est=(900, 1400),
        keyword_flags=("resume",),
    ),
    Gabarit(
        category="resume",
        lang="en",
        label="claude-haiku-4-5",
        note="résumé bref d'un compte-rendu de réunion de routine, en anglais, fil vierge.",
        n_instances=3,
        token_est=(100, 280),
        keyword_flags=("resume",),
    ),
    Gabarit(
        category="resume",
        lang="fr",
        label="claude-haiku-4-5",
        note="résumé d'une note interne standard de longueur moyenne, fil vierge.",
        n_instances=3,
        token_est=(300, 600),
        keyword_flags=("resume",),
    ),
    Gabarit(
        category="resume",
        lang="fr",
        label="claude-haiku-4-5",
        note="résumé très court de notes de réunion informelles, fil déjà engagé mais léger.",
        n_instances=3,
        token_est=(80, 200),
        keyword_flags=("resume",),
        msg_count=(5, 9),
        tok_per_msg=(40, 90),
        current_model="claude-haiku-4-5",
    ),
    Gabarit(
        category="resume",
        lang="en",
        label="claude-sonnet-5",
        note=(
            "résumé d'un texte de recherche nuancé nécessitant une interprétation fine, "
            "en anglais, fil vierge."
        ),
        n_instances=3,
        token_est=(200, 500),
        keyword_flags=("resume",),
    ),
    # === extraction (20 instances) ============================================
    Gabarit(
        category="extraction",
        lang="fr",
        label="claude-haiku-4-5",
        note=(
            "extraction de champs structurés (dates, montants) depuis un texte court fourni, "
            "fil vierge."
        ),
        n_instances=4,
        token_est=(80, 250),
    ),
    Gabarit(
        category="extraction",
        lang="fr",
        label="claude-haiku-4-5",
        note=(
            "extraction mécanique d'une liste d'éléments depuis un fil de discussion déjà "
            "très long, tâche simple malgré le volume de contexte."
        ),
        n_instances=4,
        token_est=(60, 150),
        msg_count=(18, 28),
        tok_per_msg=(250, 350),
        current_model="claude-sonnet-5",
        review=(
            "agree",
            "contesté→conservé: arbitrage — le golden étiquette la SUFFISANCE du modèle "
            "pour la tâche (extraction mécanique), pas l'UX de bascule en cours de fil ; "
            "principe anti-volume du set",
        ),
    ),
    Gabarit(
        category="extraction",
        lang="fr",
        label="claude-sonnet-5",
        note=(
            "extraction avec interprétation : distinguer des informations ambiguës ou "
            "implicites dans un texte moyen, fil vierge."
        ),
        n_instances=3,
        token_est=(150, 280),
    ),
    Gabarit(
        category="extraction",
        lang="en",
        label="claude-haiku-4-5",
        note=(
            "extraction structurée de coordonnées depuis un court bloc de texte, en anglais, "
            "fil vierge."
        ),
        n_instances=3,
        token_est=(60, 180),
    ),
    Gabarit(
        category="extraction",
        lang="fr",
        label="claude-opus-4-8",
        note=(
            "extraction ET qualification de clauses à risque dans un contrat dense et à fort "
            "enjeu, fil vierge."
        ),
        n_instances=3,
        token_est=(400, 700),
        keyword_flags=("contrat",),
    ),
    Gabarit(
        category="extraction",
        lang="en",
        label="claude-haiku-4-5",
        note=(
            "extraction de chiffres-clés depuis un court extrait financier, en anglais, fil vierge."
        ),
        n_instances=3,
        token_est=(50, 150),
    ),
    # === traduction (20 instances) ============================================
    Gabarit(
        category="traduction",
        lang="fr",
        label="claude-haiku-4-5",
        note="traduction courte et standard d'un texte simple, fil vierge.",
        n_instances=4,
        token_est=(80, 300),
        keyword_flags=("traduction",),
    ),
    Gabarit(
        category="traduction",
        lang="fr",
        label="claude-sonnet-5",
        note="traduction longue d'un document technique, au-delà du seuil de longueur, fil vierge.",
        n_instances=3,
        token_est=(900, 1300),
        keyword_flags=("traduction",),
    ),
    Gabarit(
        category="traduction",
        lang="en",
        label="claude-haiku-4-5",
        note="traduction courte et routinière d'une phrase simple, en anglais, fil vierge.",
        n_instances=3,
        token_est=(60, 250),
        keyword_flags=("traduction",),
    ),
    Gabarit(
        category="traduction",
        lang="fr",
        label="claude-sonnet-5",
        note=(
            "traduction courte mais littéraire, exigeant de préserver le ton et les jeux de "
            "mots, fil vierge."
        ),
        n_instances=4,
        token_est=(80, 200),
        keyword_flags=("traduction",),
    ),
    Gabarit(
        category="traduction",
        lang="fr",
        label="claude-haiku-4-5",
        note="traduction administrative standard de longueur moyenne, fil déjà présent mais léger.",
        n_instances=3,
        token_est=(300, 600),
        keyword_flags=("traduction",),
        msg_count=(4, 7),
        tok_per_msg=(60, 120),
        current_model="claude-haiku-4-5",
    ),
    Gabarit(
        category="traduction",
        lang="en",
        label="claude-sonnet-5",
        note=(
            "traduction juridique officielle, terminologie exacte requise, en anglais, "
            "longueur moyenne, fil vierge — cela RESTE une traduction (transformation à "
            "faible risque) : le modèle intermédiaire suffit, l'enjeu probant relève de la "
            "relecture humaine, pas d'un palier supérieur."
        ),
        n_instances=3,
        token_est=(300, 600),
        keyword_flags=("traduction", "contrat"),
        review=(
            "amended: opus→sonnet — plafond traduction, cohérence interne du set, "
            "l'enjeu probant ne monte pas de palier",
            "agree — avait relu le label INITIAL opus sans le contester ; le label figé "
            "sonnet vient de l'arbitrage du désaccord ml",
        ),
    ),
    # === code (24 instances) ===================================================
    Gabarit(
        category="code",
        lang="fr",
        label="claude-haiku-4-5",
        note="question de code triviale, syntaxe d'une seule ligne, fil vierge.",
        n_instances=4,
        token_est=(15, 40),
        has_code=True,
        keyword_flags=("code",),
    ),
    Gabarit(
        category="code",
        lang="fr",
        label="claude-sonnet-5",
        note=(
            "débogage d'une fonction de taille moyenne avec erreur logique non triviale, "
            "fil vierge."
        ),
        n_instances=4,
        token_est=(150, 400),
        has_code=True,
        keyword_flags=("code",),
    ),
    Gabarit(
        category="code",
        lang="fr",
        label="claude-opus-4-8",
        note=(
            "conception d'une architecture logicielle complexe multi-contraintes, fil déjà "
            "engagé avec du code vu précédemment."
        ),
        n_instances=4,
        token_est=(400, 900),
        has_code=True,
        keyword_flags=("code",),
        msg_count=(10, 18),
        tok_per_msg=(150, 300),
        seen_code=True,
        current_model="claude-sonnet-5",
        review=(
            "agree",
            "contesté→conservé: arbitrage — conception multi-contraintes à la frontière "
            "réelle Sonnet/Opus, jugée au-dessus du dev standard ; conserve la couverture "
            "opus de la catégorie code",
        ),
    ),
    Gabarit(
        category="code",
        lang="en",
        label="claude-sonnet-5",
        note="débogage modéré sur une fonction de taille moyenne, en anglais, fil vierge.",
        n_instances=3,
        token_est=(150, 350),
        has_code=True,
        keyword_flags=("code",),
    ),
    Gabarit(
        category="code",
        lang="fr",
        label="claude-sonnet-5",
        note="revue de code standard sur un fichier de taille moyenne, fil vierge.",
        n_instances=3,
        token_est=(300, 600),
        has_code=True,
        keyword_flags=("code",),
    ),
    Gabarit(
        category="code",
        lang="en",
        label="claude-sonnet-5",
        note=(
            "investigation d'un bogue modérément complexe, fil déjà engagé avec du code vu "
            "précédemment, en anglais."
        ),
        n_instances=3,
        token_est=(400, 800),
        has_code=True,
        keyword_flags=("code",),
        msg_count=(12, 20),
        tok_per_msg=(150, 300),
        seen_code=True,
        current_model="claude-sonnet-5",
    ),
    Gabarit(
        category="code",
        lang="fr",
        label="claude-sonnet-5",
        note=(
            "génération d'un script utilitaire de complexité moyenne avec gestion d'erreurs, "
            "fil vierge."
        ),
        n_instances=3,
        token_est=(150, 350),
        has_code=True,
        keyword_flags=("code",),
    ),
    # === maths_raisonnement (24 instances) =====================================
    Gabarit(
        category="maths_raisonnement",
        lang="fr",
        label="claude-sonnet-5",
        note="calcul à plusieurs étapes avec risque réel d'erreur de calcul, fil vierge.",
        n_instances=4,
        token_est=(120, 300),
        has_math=True,
    ),
    Gabarit(
        category="maths_raisonnement",
        lang="fr",
        label="claude-sonnet-5",
        note="exercice de mathématiques de niveau lycée à plusieurs étapes, fil vierge.",
        n_instances=4,
        token_est=(150, 350),
        has_math=True,
    ),
    Gabarit(
        category="maths_raisonnement",
        lang="fr",
        label="claude-opus-4-8",
        note=(
            "démonstration mathématique profonde et originale nécessitant plusieurs étapes "
            "de preuve rigoureuse, fil vierge."
        ),
        n_instances=4,
        token_est=(150, 400),
        has_math=True,
    ),
    Gabarit(
        category="maths_raisonnement",
        lang="en",
        label="claude-sonnet-5",
        note=(
            "problème à plusieurs étapes nécessitant un raisonnement soigné, en anglais, "
            "fil vierge."
        ),
        n_instances=3,
        token_est=(150, 300),
        has_math=True,
    ),
    Gabarit(
        category="maths_raisonnement",
        lang="fr",
        label="claude-sonnet-5",
        note="preuve mathématique standard mais longue, fil vierge.",
        n_instances=3,
        token_est=(850, 1200),
        has_math=True,
    ),
    Gabarit(
        category="maths_raisonnement",
        lang="fr",
        label="claude-sonnet-5",
        note="problème de logique de difficulté moyenne, fil vierge.",
        n_instances=3,
        token_est=(100, 250),
        has_math=True,
    ),
    Gabarit(
        category="maths_raisonnement",
        lang="en",
        label="claude-haiku-4-5",
        note="conversion d'unité triviale, en anglais, fil vierge.",
        n_instances=3,
        token_est=(15, 50),
        has_math=True,
    ),
    # === juridique_contrat (20 instances) =======================================
    Gabarit(
        category="juridique_contrat",
        lang="fr",
        label="claude-opus-4-8",
        note=(
            "analyse fine de clauses contractuelles ambiguës à fort enjeu, fil vierge, "
            "longueur importante."
        ),
        n_instances=4,
        token_est=(500, 900),
        keyword_flags=("contrat", "analyse"),
    ),
    Gabarit(
        category="juridique_contrat",
        lang="fr",
        label="claude-sonnet-5",
        note=(
            "relecture standard d'un contrat type sans clause inhabituelle, fil vierge, "
            "longueur moyenne — demande formulée de manière générique, sans nommer le "
            "type de document : aucun drapeau détecté, cas réaliste."
        ),
        n_instances=4,
        token_est=(320, 550),
    ),
    Gabarit(
        category="juridique_contrat",
        lang="fr",
        label="claude-haiku-4-5",
        note=(
            "vérification mécanique de la présence d'une clause précise dans un contrat "
            "court, fil vierge."
        ),
        n_instances=3,
        token_est=(80, 200),
        keyword_flags=("contrat",),
    ),
    Gabarit(
        category="juridique_contrat",
        lang="en",
        label="claude-opus-4-8",
        note=(
            "analyse de risque contractuel multi-juridictions à fort enjeu, en anglais, fil "
            "déjà engagé avec du contexte juridique antérieur."
        ),
        n_instances=3,
        token_est=(600, 900),
        keyword_flags=("contrat", "analyse"),
        msg_count=(10, 16),
        tok_per_msg=(200, 350),
        seen_reasoning=True,
        current_model="claude-opus-4-8",
    ),
    Gabarit(
        category="juridique_contrat",
        lang="fr",
        label="claude-sonnet-5",
        note=(
            "rédaction d'une clause contractuelle standard à partir d'un modèle connu, fil "
            "vierge, longueur moyenne — demande formulée de manière générique, sans "
            "vocabulaire contractuel explicite : aucun drapeau détecté, cas réaliste."
        ),
        n_instances=3,
        token_est=(350, 600),
    ),
    Gabarit(
        category="juridique_contrat",
        lang="fr",
        label="claude-opus-4-8",
        note=(
            "négociation contractuelle complexe multi-parties nécessitant une analyse "
            "juridique poussée, fil déjà engagé."
        ),
        n_instances=3,
        token_est=(700, 950),
        keyword_flags=("contrat", "analyse"),
        msg_count=(15, 25),
        tok_per_msg=(200, 350),
        seen_reasoning=True,
        current_model="claude-opus-4-8",
    ),
    # === multi_tours (25 instances) — signaux de conversation VARIÉS ============
    Gabarit(
        category="multi_tours",
        lang="fr",
        label="claude-sonnet-5",
        note=(
            "prompt très bref demandant le détail des étapes du raisonnement, posé dans "
            "un fil déjà engagé sur une démonstration mathématique."
        ),
        n_instances=4,
        token_est=(5, 15),
        keyword_flags=("demonstration",),
        msg_count=(4, 10),
        tok_per_msg=(60, 150),
        seen_math=True,
        seen_reasoning=True,
        current_model="claude-haiku-4-5",
        recos_shown=(1, 3),
        recos_followed_ratio=(0.3, 0.7),
        derogations_up=(0, 1),
    ),
    Gabarit(
        category="multi_tours",
        lang="fr",
        label="claude-sonnet-5",
        note="fil déjà engagé sur du code, nouvelle demande de correction ponctuelle et brève.",
        n_instances=3,
        token_est=(10, 40),
        msg_count=(4, 9),
        tok_per_msg=(80, 180),
        seen_code=True,
        current_model="claude-sonnet-5",
        recos_shown=(1, 3),
        recos_followed_ratio=(0.5, 0.9),
        derogations_up=(0, 1),
    ),
    Gabarit(
        category="multi_tours",
        lang="fr",
        label="claude-sonnet-5",
        note=(
            "fil déjà très long et dense, nouvelle demande de synthèse générale recoupant "
            "l'ensemble des échanges — la synthèse dense est une tâche du modèle "
            "intermédiaire : le volume de contexte seul ne fait pas monter de palier."
        ),
        n_instances=3,
        token_est=(150, 400),
        review=(
            "amended: opus→sonnet — synthèse dense plafonnée à Sonnet, le volume seul ne "
            "monte pas de palier (principe du set)",
            "agree — avait relu le label INITIAL opus sans le contester ; label figé "
            "sonnet issu de l'arbitrage du désaccord ml",
        ),
        msg_count=(25, 45),
        tok_per_msg=(200, 320),
        current_model="claude-sonnet-5",
        recos_shown=(2, 5),
        recos_followed_ratio=(0.4, 0.8),
        derogations_up=(0, 2),
    ),
    Gabarit(
        category="multi_tours",
        lang="fr",
        label="claude-sonnet-5",
        note=(
            "nouvelle question de synthèse argumentée de complexité moyenne, après plusieurs "
            "dérogations de l'utilisateur vers un modèle plus capable que la recommandation "
            "précédente."
        ),
        n_instances=3,
        token_est=(200, 400),
        msg_count=(8, 14),
        tok_per_msg=(80, 150),
        current_model="claude-haiku-4-5",
        recos_shown=(6, 10),
        recos_followed_ratio=(0.15, 0.4),
        derogations_up=(3, 6),
    ),
    Gabarit(
        category="multi_tours",
        lang="en",
        label="claude-haiku-4-5",
        note=(
            "fil de discussion informel et déjà long, nombreux échanges courts et légers, "
            "nouvelle question factuelle brève et anodine, en anglais."
        ),
        n_instances=3,
        token_est=(15, 45),
        msg_count=(16, 26),
        tok_per_msg=(15, 40),
        current_model="claude-haiku-4-5",
        recos_shown=(3, 7),
        recos_followed_ratio=(0.3, 0.6),
        derogations_up=(0, 2),
    ),
    Gabarit(
        category="multi_tours",
        lang="fr",
        label="claude-sonnet-5",
        note=(
            "fil où les recommandations précédentes ont été largement suivies, nouvelle "
            "demande de rédaction de longueur moyenne."
        ),
        n_instances=3,
        token_est=(200, 400),
        msg_count=(8, 14),
        tok_per_msg=(60, 120),
        current_model="claude-sonnet-5",
        recos_shown=(8, 14),
        recos_followed_ratio=(0.75, 0.95),
        derogations_up=(0, 1),
    ),
    Gabarit(
        category="multi_tours",
        lang="fr",
        label="claude-sonnet-5",
        note=(
            "fil mixte déjà engagé sur du code et des mathématiques, nouvelle question "
            "combinant les deux domaines de façon soutenue — prompt et contexte modestes : "
            "la combinaison reste dans le périmètre du modèle intermédiaire."
        ),
        n_instances=3,
        token_est=(400, 700),
        review=(
            "agree — avait relu le label INITIAL opus sans le contester ; label figé "
            "sonnet issu de l'arbitrage du désaccord eval",
            "amended: opus→sonnet — combinaison code+maths à prompt/contexte modestes, "
            "périmètre Sonnet (sobriété : le moins cher qui suffit)",
        ),
        msg_count=(10, 18),
        tok_per_msg=(100, 200),
        seen_code=True,
        seen_math=True,
        current_model="claude-sonnet-5",
        recos_shown=(2, 5),
        recos_followed_ratio=(0.3, 0.7),
        derogations_up=(0, 2),
    ),
    Gabarit(
        category="multi_tours",
        lang="en",
        label="claude-haiku-4-5",
        note=(
            "fil bref déjà sur le modèle le plus capable, nouvelle question de clarification "
            "très courte et triviale, en anglais."
        ),
        n_instances=3,
        token_est=(10, 35),
        msg_count=(3, 6),
        tok_per_msg=(50, 100),
        current_model="claude-opus-4-8",
        recos_shown=(1, 3),
        recos_followed_ratio=(0.5, 1.0),
        derogations_up=(0, 1),
    ),
    # === ajout post-arbitrage (R2) : opus honnête en multi_tours ==============
    # Les deux relecteurs ont fait redescendre les 2 gabarits opus de la
    # catégorie (surdimensionnés) ; ce scénario-ci est un opus DE FOND : une
    # preuve profonde poursuivie en fil long — l'heuristique v0 répondra
    # Sonnet (reasoning_context, sans palier Opus) : mésaccord honnête.
    Gabarit(
        category="multi_tours",
        lang="fr",
        label="claude-opus-4-8",
        note=(
            "fil de démonstration mathématique profonde poursuivi sur de nombreux tours, "
            "nouvelle étape décisive de la preuve exigeant un raisonnement original "
            "soutenu — le fond (preuve profonde), pas le volume, justifie le modèle le "
            "plus capable."
        ),
        n_instances=3,
        token_est=(300, 600),
        has_math=True,
        keyword_flags=("demonstration",),
        msg_count=(15, 25),
        tok_per_msg=(150, 280),
        seen_math=True,
        seen_reasoning=True,
        current_model="claude-sonnet-5",
        recos_shown=(2, 5),
        recos_followed_ratio=(0.4, 0.8),
        derogations_up=(0, 1),
        review=(
            "non_soumis: ajout post-arbitrage orchestrateur — relecture formelle "
            "ml-architect au panel ronde 2 (verdict au ledger)",
            "valide panel ronde 1 (eval-scientist, contexte neuf) — verdict détaillé au "
            "ledger R2 round 1",
        ),
    ),
    # === ajouts correction ronde 0 (eval-scientist : cellules opus à 1 seul
    # gabarit = pilier fragile). Étiquettes opus DE FOND, provenance honnête
    # (non soumis à la double-revue initiale — à revoir par le panel ronde 1).
    Gabarit(
        category="code",
        lang="fr",
        label="claude-opus-4-8",
        note=(
            "diagnostic d'un bug de concurrence subtil et intermittent dans un système "
            "distribué, raisonnement causal profond requis, fil vierge — le fond (course "
            "critique non déterministe), pas le volume, justifie le modèle le plus capable."
        ),
        n_instances=3,
        token_est=(250, 550),
        has_code=True,
        keyword_flags=("code",),
        review=(
            "non_soumis: ajout correction ronde 0 — relecture formelle ml-architect au "
            "panel ronde 2 (verdict au ledger)",
            "valide panel ronde 1 (eval-scientist, contexte neuf) — verdict détaillé au "
            "ledger R2 round 1",
        ),
    ),
    Gabarit(
        category="multi_tours",
        lang="fr",
        label="claude-opus-4-8",
        note=(
            "fil juridique déjà long et dense, nouvelle demande de synthèse des risques "
            "croisés entre de nombreuses clauses interdépendantes, à fort enjeu — "
            "l'interdépendance des risques (pas le volume) exige le modèle le plus capable."
        ),
        n_instances=3,
        token_est=(300, 600),
        keyword_flags=("contrat", "analyse"),
        msg_count=(14, 22),
        tok_per_msg=(200, 330),
        seen_reasoning=True,
        current_model="claude-opus-4-8",
        recos_shown=(2, 5),
        recos_followed_ratio=(0.5, 0.9),
        derogations_up=(0, 1),
        review=(
            "non_soumis: ajout correction ronde 0 — relecture formelle ml-architect au "
            "panel ronde 2 (verdict au ledger)",
            "valide panel ronde 1 (eval-scientist, contexte neuf) — verdict détaillé au "
            "ledger R2 round 1",
        ),
    ),
)


def _valider_gabarits() -> None:
    """Garde-fou : lève AVANT génération si un gabarit est mal formé (typo, etc.)."""
    for g in GABARITS:
        assert g.label in VISIBLE_MODELS, f"étiquette hors catalogue visible : {g.label!r}"
        assert g.lang in _ALLOWED_LANGS, f"langue inattendue : {g.lang!r}"
        assert set(g.keyword_flags) <= _ALLOWED_FLAGS, f"drapeau inconnu : {g.keyword_flags!r}"
        assert g.n_instances in (3, 4), f"n_instances hors [3,4] : {g.n_instances!r}"
        if g.current_model is not None:
            assert g.current_model in VISIBLE_MODELS, (
                f"current_model hors catalogue visible : {g.current_model!r}"
            )
    # Garde-fous d'ÉQUILIBRE (correction ronde 0, eval-scientist) : une édition
    # fondateur ne doit pas faire dériver silencieusement la couverture.
    par_categorie: dict[str, int] = {}
    opus_gabarits: dict[str, int] = {}
    total_fr = 0
    total = 0
    for g in GABARITS:
        par_categorie[g.category] = par_categorie.get(g.category, 0) + g.n_instances
        total += g.n_instances
        if g.lang == "fr":
            total_fr += g.n_instances
        if g.label == "claude-opus-4-8":
            opus_gabarits[g.category] = opus_gabarits.get(g.category, 0) + 1
    for cat, n in par_categorie.items():
        assert 15 <= n <= 32, f"catégorie déséquilibrée : {cat} = {n} instances"
    assert total_fr / total > 0.6, f"part FR insuffisante : {total_fr / total:.0%}"
    # Cellules opus à ≥ 2 gabarits DISTINCTS là où le set en revendique la
    # couverture (code, multi_tours — correction ronde 0) ; les autres cellules
    # opus minces sont ASSUMÉES et documentées dans coverage_report.json.
    for cat in ("code", "multi_tours"):
        assert opus_gabarits.get(cat, 0) >= 2, (
            f"couverture opus trop mince en {cat} : {opus_gabarits.get(cat, 0)} gabarit(s)"
        )


def _build_prompt(rng: random.Random, g: Gabarit) -> tuple[dict, tuple[str, ...]]:
    """Tire les signaux du PROMPT (jitter seedé). `char_len` reste ≈ 4×`token_est`."""
    token_est = rng.randint(*g.token_est)
    facteur = rng.uniform(*g.char_len_factor)
    char_len = max(1, round(token_est * facteur))
    flags = g.keyword_flags
    prompt_json = {
        "char_len": char_len,
        "token_est": token_est,
        "lang": g.lang,
        "has_code": g.has_code,
        "has_math": g.has_math,
        "keyword_flags": list(flags),
    }
    return prompt_json, flags


def _build_conversation(rng: random.Random, g: Gabarit) -> dict:
    """Tire les signaux de CONVERSATION (jitter seedé), cohérents entre eux.

    `context_token_est` dérive de `msg_count × tok_per_msg` (+ bruit léger) —
    jamais un nombre indépendant du nombre de messages. `recos_followed`
    dérive d'un ratio de `recos_shown` (toujours ≤ `recos_shown`).
    """
    msg_count = rng.randint(*g.msg_count)
    if msg_count > 0 and g.tok_per_msg != (0, 0):
        tok_per_msg = rng.randint(*g.tok_per_msg)
        bruit = rng.randint(-30, 30)
        context_token_est = max(0, msg_count * tok_per_msg + bruit)
    else:
        context_token_est = 0
    # Une recommandation ne peut s'afficher qu'à un tour UTILISATEUR :
    # recos_shown est plafonné à ceil(msg_count/2) (correction ronde 0,
    # data-quality : gold-0165 affichait 10 recos pour 9 messages).
    max_user_turns = (msg_count + 1) // 2
    recos_shown = min(rng.randint(*g.recos_shown), max_user_turns)
    if recos_shown > 0:
        ratio = rng.uniform(*g.recos_followed_ratio)
        recos_followed = min(recos_shown, round(recos_shown * ratio))
    else:
        recos_followed = 0
    derogations_up = rng.randint(*g.derogations_up)
    return {
        "msg_count": msg_count,
        "context_token_est": context_token_est,
        "seen_code": g.seen_code,
        "seen_math": g.seen_math,
        "seen_reasoning": g.seen_reasoning,
        "current_model": g.current_model,
        "recos_shown": recos_shown,
        "recos_followed": recos_followed,
        "derogations_up": derogations_up,
    }


def generate() -> tuple[list[dict], list[tuple[Signals, str]]]:
    """Engendre les lignes golden + les couples (signaux, étiquette) pour le diagnostic.

    Un SEUL `random.Random(SEED)`, consommé dans l'ordre déclaré de `GABARITS`
    puis dans l'ordre des instances de chaque gabarit : reproductible à l'octet
    près d'une exécution à l'autre.
    """
    rng = random.Random(SEED)
    entries: list[dict] = []
    diagnostics: list[tuple[Signals, str]] = []
    compteur = 1
    for g in GABARITS:
        for _ in range(g.n_instances):
            prompt_json, flags = _build_prompt(rng, g)
            conversation_json = _build_conversation(rng, g)
            entry = {
                "id": f"gold-{compteur:04d}",
                "category": g.category,
                "lang": g.lang,
                "signals": {"prompt": prompt_json, "conversation": conversation_json},
                "label": g.label,
                "note": g.note,
                "review": {"ml_architect": g.review[0], "eval_scientist": g.review[1]},
            }
            entries.append(entry)
            signals = Signals(
                prompt=PromptSignals(
                    char_len=prompt_json["char_len"],
                    token_est=prompt_json["token_est"],
                    lang=prompt_json["lang"],
                    has_code=prompt_json["has_code"],
                    has_math=prompt_json["has_math"],
                    keyword_flags=flags,
                ),
                conversation=ConversationSignals(**conversation_json),
            )
            diagnostics.append((signals, g.label))
            compteur += 1
    return entries, diagnostics


def _heuristic_agreement(diagnostics: list[tuple[Signals, str]]) -> float:
    """DIAGNOSTIC seul (JAMAIS utilisé pour étiqueter) : taux d'accord `HeuristicRouter`.

    Attendu ~65-90 % (les arbitrages post-génération font baisser
    l'accord) : un set où l'heuristique aurait 100 % raison ne
    servirait à rien comme juge de paix (gate R3 infranchissable).
    """
    routeur = HeuristicRouter()
    accords = 0
    for signals, label in diagnostics:
        decision = routeur.decide(signals)
        if decision.model == label:
            accords += 1
    return accords / len(diagnostics) if diagnostics else 0.0


# Trace du processus de revue (R2) — régénérée avec le set, JAMAIS éditée à la
# main dans coverage_report.json (correction ronde 0, eval-scientist).
DOUBLE_REVUE = {
    "processus": (
        "génération builder-core (sonnet) → double-revue INDÉPENDANTE parallèle "
        "ml-architect (opus) + eval-scientist (opus) → arbitrage 2/3 orchestrateur → "
        "corrections ronde 0 du panel de juges (provenances honnêtes, ajouts opus)"
    ),
    "desaccords_ml": 2,
    "desaccords_eval": 3,
    "arbitrages": {
        "traduction_juridique_officielle (gold-0077..79)": "opus→sonnet (ml accepté)",
        "synthese_fil_long (gold-0155..57)": "opus→sonnet (ml accepté)",
        "architecture_complexe (gold-0088..91)": "CONSERVÉ opus (eval rejeté, arbitrage documenté)",
        "fil_mixte_code_maths (gold-0167..69)": "opus→sonnet (eval accepté)",
        "extraction_fil_long (gold-0044..47)": "CONSERVÉ haiku (eval rejeté, arbitrage documenté)",
    },
    "ajouts_non_soumis_double_revue": (
        "3 gabarits opus marqués review='non_soumis…' / 'valide_au_fond…' — provenance "
        "HONNÊTE, soumis au panel de juges des rondes suivantes"
    ),
}

LIMITES_STATISTIQUES = {
    "n_effectif": (
        "les instances d'un même gabarit ne diffèrent que par un jitter numérique seedé : "
        "le n effectif ≈ nombre de gabarits (voir n_gabarits), pas le nombre de lignes"
    ),
    "cellules_opus": (
        "certaines cellules catégorie×opus restent minces (extraction, maths) : le gate "
        "R3 doit consommer les métriques opus en AGRÉGÉ/relatif uniquement — JAMAIS de "
        "seuil opus par cellule"
    ),
    "non_separabilite_etage_1": (
        "des cellules adjacentes (ex. maths opus vs sonnet) ne diffèrent que par la "
        "nature SÉMANTIQUE de la tâche, invisible aux signaux : un classifieur étage 1 a "
        "un plafond de justesse < 100 % sur le golden SANS rapport avec sa qualité — "
        "argument documenté pour l'étage 2 (R6)"
    ),
    "cellules_vides_par_design": (
        "redaction_simple/opus, resume/opus, traduction/opus sont VIDES par principe "
        "(plafonds de sobriété du set)"
    ),
}


def _coverage_stats(entries: list[dict], heuristic_agreement: float) -> dict:
    n = len(entries)
    by_category = Counter(e["category"] for e in entries)
    by_label = Counter(e["label"] for e in entries)
    n_fr = sum(1 for e in entries if e["lang"] == "fr")
    return {
        "n": n,
        "by_category": dict(sorted(by_category.items())),
        "by_label": dict(sorted(by_label.items())),
        "fr_share": round(n_fr / n, 4) if n else 0.0,
        "heuristic_agreement": round(heuristic_agreement, 4),
        "seed": SEED,
        "n_gabarits": len(GABARITS),
    }


def main() -> None:
    _valider_gabarits()
    entries, diagnostics = generate()

    ids = [e["id"] for e in entries]
    assert len(ids) == len(set(ids)), "ids gold-XXXX non uniques"
    assert 150 <= len(entries) <= 200, f"taille hors [150,200] : {len(entries)}"

    heuristic_agreement = _heuristic_agreement(diagnostics)
    stats = _coverage_stats(entries, heuristic_agreement)

    with GOLDEN_PATH.open("w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False))
            f.write("\n")

    with STATS_PATH.open("w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
        f.write("\n")

    by_cat_label: dict[str, dict[str, int]] = {}
    by_lang: Counter = Counter()
    for e in entries:
        by_cat_label.setdefault(e["category"], {})
        by_cat_label[e["category"]][e["label"]] = by_cat_label[e["category"]].get(e["label"], 0) + 1
        by_lang[e["lang"]] += 1
    report = {
        **stats,
        "by_category_x_label": {
            k: dict(sorted(v.items())) for k, v in sorted(by_cat_label.items())
        },
        "by_lang": dict(sorted(by_lang.items())),
        "double_revue": DOUBLE_REVUE,
        "limites_statistiques": LIMITES_STATISTIQUES,
    }
    with REPORT_PATH.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"golden.jsonl : {stats['n']} lignes -> {GOLDEN_PATH}")
    print(f"par catégorie : {stats['by_category']}")
    print(f"par étiquette : {stats['by_label']}")
    print(f"part FR : {stats['fr_share']:.1%}")
    print(f"accord heuristique (diagnostic, PAS l'étiquetage) : {stats['heuristic_agreement']:.1%}")


if __name__ == "__main__":
    main()
