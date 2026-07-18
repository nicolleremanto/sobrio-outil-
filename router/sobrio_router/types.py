"""Types partagés du routeur (schéma = RFC-0001, docs/rfc/RFC-0001-signals-conversation.md).

Dataclasses GELÉES (`frozen=True`) : un jeu de signaux ou une décision ne
bouge jamais après construction — utile pour la testabilité et pour éviter
qu'un routeur modifie par mégarde les signaux d'un autre. Aucun champ texte
libre nulle part : uniquement des mesures et des indicateurs de vocabulaire
fermé (règle n°1 — jamais de contenu de prompt stocké ni loggé).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptSignals:
    """Signaux calculés sur le SEUL dernier prompt (jamais son texte).

    EXCEPTION RÉSERVÉE — `prompt_text` (étage 2, R6) : point d'extension
    documenté DÈS MAINTENANT pour ne pas casser l'interface plus tard
    (revue ml-architect, ronde 0). Contrat d'usage STRICT :
    - `None` partout en v0/v0.5 (l'étage 1 l'IGNORE inconditionnellement) ;
    - alimenté UNIQUEMENT si la politique d'org a `send_prompt_text=true`
      (l'étage 2 REFUSE de fonctionner s'il est absent — verrou R6) ;
    - traité EN MÉMOIRE seulement : JAMAIS stocké, loggé, sérialisé ni
      inclus dans un artefact/rapport (règle n°1, privacy-sentinel).
    """

    char_len: int
    token_est: int
    lang: str
    has_code: bool
    has_math: bool
    keyword_flags: tuple[str, ...]
    prompt_text: str | None = None


@dataclass(frozen=True)
class ConversationSignals:
    """Mémoire de conversation (RFC-0001).

    Motif : un « démontre-le » court dans un fil mathématique ne doit pas
    partir sur le modèle le plus léger. Tous les champs sont par défaut
    NEUTRES (zéro / False / None) : c'est l'état produit par l'adaptateur
    `features_to_signals` tant que le contrat `/v1/recommend` n'accepte pas
    encore le bloc `signals` (RFC-0001).
    """

    msg_count: int = 0
    context_token_est: int = 0
    seen_code: bool = False
    seen_math: bool = False
    seen_reasoning: bool = False
    current_model: str | None = None
    recos_shown: int = 0
    recos_followed: int = 0
    derogations_up: int = 0


@dataclass(frozen=True)
class Signals:
    """Bundle complet transmis à `Router.decide()`."""

    prompt: PromptSignals
    conversation: ConversationSignals


@dataclass(frozen=True)
class Decision:
    """Décision de routage : modèle recommandé, confiance, règle explicable.

    `model` est un id VISIBLE du catalogue (`contracts/model_catalog.yaml`,
    jamais `claude-fable-5` — RFC-0002, sobriété). `rule` est le nom de la
    règle/étage qui a produit la décision (contrat `/v1/recommend` : champ
    obligatoire, sert à l'explicabilité).
    """

    model: str
    confidence: float
    rule: str
