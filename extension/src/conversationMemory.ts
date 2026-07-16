/**
 * Mémoire de conversation — état PAR FIL, en mémoire de session uniquement
 * (aucun storage : la mémoire meurt avec l'onglet, règle 1).
 *
 * Elle reçoit une « vue de page » (bulles lues LOCALEMENT par les sélecteurs),
 * la réduit immédiatement en compteurs/drapeaux, et oublie le texte. Elle est
 * RÉINITIALISÉE quand une nouvelle conversation est détectée (changement de
 * fil, ou régression du nombre de bulles quand le fil n'est pas identifiable).
 *
 * C'est elle qui évite le routage naïf : un « démontre-le » court dans un fil
 * où seen_math=true doit produire des signaux qui mènent ailleurs que Haiku.
 */
import { estimateTokens, hasCode, normalize } from './features';
import { hasMath, normalizeModelLabel, KNOWN_MODELS, type ConversationSignals } from './signals';

/** Une bulle telle que lue (localement) dans la page. Le texte reste ici. */
export interface BubbleView {
  role: 'user' | 'assistant' | 'unknown';
  text: string;
}

/** Vue de page transmise par le content script à chaque mise à jour. */
export interface PageView {
  /** Identifiant du fil (URL ou attribut DOM) ; null si indéterminable. */
  threadId: string | null;
  bubbles: BubbleView[];
  /** Libellé brut de l'étiquette de modèle (normalisé ici, jamais émis). */
  modelLabel: string | null;
}

/** Rang de coût des modèles du catalogue (pour `derogations_up`). */
const MODEL_RANK: Readonly<Record<string, number>> = Object.fromEntries(
  KNOWN_MODELS.map((id, index) => [id, index]),
);

/** Marqueurs (normalisés) de raisonnement suivi dans une réponse. */
const REASONING_MARKERS: readonly string[] = [
  'donc',
  'par consequent',
  'etape 1',
  'etape 2',
  'raisonnement',
  'therefore',
  'step 1',
  'step 2',
];

/** Seuil : une réponse longue est un indice de tâche de fond. TODO(V1). */
const LONG_ASSISTANT_TOKENS = 400;

export class ConversationMemory {
  private threadId: string | null = null;
  private bubbleCount = 0;

  private msgCount = 0;
  private contextTokenEst = 0;
  private seenCode = false;
  private seenMath = false;
  private seenReasoning = false;
  private currentModel: string | null = null;

  private recosShown = 0;
  private recosFollowed = 0;
  private derogationsUp = 0;

  /** Réinitialise tout l'état (nouvelle conversation). */
  reset(threadId: string | null = null): void {
    this.threadId = threadId;
    this.bubbleCount = 0;
    this.msgCount = 0;
    this.contextTokenEst = 0;
    this.seenCode = false;
    this.seenMath = false;
    this.seenReasoning = false;
    this.currentModel = null;
    this.recosShown = 0;
    this.recosFollowed = 0;
    this.derogationsUp = 0;
  }

  /**
   * Met à jour la mémoire depuis la page. Détection de nouvelle conversation :
   * - le threadId change (ou apparaît différent), ou
   * - le nombre de bulles RÉGRESSE (fil vidé) quand le fil est anonyme.
   * Les compteurs de recommandations survivent aux mises à jour d'un même fil.
   */
  updateFromPage(view: PageView): void {
    const threadChanged =
      view.threadId !== null
        ? view.threadId !== this.threadId
        : view.bubbles.length < this.bubbleCount;
    if (threadChanged) this.reset(view.threadId);
    if (this.threadId === null && view.threadId !== null) this.threadId = view.threadId;

    this.bubbleCount = view.bubbles.length;
    this.msgCount = view.bubbles.length;

    // Réduction immédiate : le texte des bulles ne sort JAMAIS de cette boucle.
    let tokens = 0;
    let seenCode = false;
    let seenMath = false;
    let seenReasoning = false;
    for (const bubble of view.bubbles) {
      const bubbleTokens = estimateTokens(bubble.text.length);
      tokens += bubbleTokens;
      const math = hasMath(bubble.text);
      seenCode = seenCode || hasCode(bubble.text);
      seenMath = seenMath || math;
      if (!seenReasoning) {
        const normalized = normalize(bubble.text);
        seenReasoning =
          math ||
          (bubble.role === 'assistant' && bubbleTokens > LONG_ASSISTANT_TOKENS) ||
          REASONING_MARKERS.some((marker) => normalized.includes(marker));
      }
    }
    this.contextTokenEst = tokens;
    this.seenCode = seenCode;
    this.seenMath = seenMath;
    this.seenReasoning = seenReasoning;
    this.currentModel = normalizeModelLabel(view.modelLabel);
  }

  /** Une recommandation a été affichée dans ce fil. */
  noteRecoShown(): void {
    this.recosShown += 1;
  }

  /** L'utilisateur déclare suivre la recommandation. */
  noteFollowed(): void {
    this.recosFollowed += 1;
  }

  /**
   * L'utilisateur déroge. `derogations_up` ne compte que les dérogations vers
   * un modèle PLUS cher que la reco (signal d'inconfort avec la reco basse).
   */
  noteDerogation(recommended: string, chosen: string): void {
    const from = MODEL_RANK[recommended];
    const to = MODEL_RANK[chosen];
    if (from !== undefined && to !== undefined && to > from) this.derogationsUp += 1;
  }

  /** Export vers le bloc `signals.conversation` du contrat — sans texte. */
  toSignals(): ConversationSignals {
    return {
      msg_count: this.msgCount,
      context_token_est: this.contextTokenEst,
      seen_code: this.seenCode,
      seen_math: this.seenMath,
      seen_reasoning: this.seenReasoning,
      current_model: this.currentModel,
      recos_shown: this.recosShown,
      recos_followed: this.recosFollowed,
      derogations_up: this.derogationsUp,
    };
  }
}
