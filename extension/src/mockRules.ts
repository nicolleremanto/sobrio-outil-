/**
 * Règles de décision du MOCK — pures, déterministes, testables.
 *
 * Ce module est la « fausse intelligence serveur » de la V0 : 4 règles simples
 * mais vivantes, qui consomment TOUT le bloc `signals` (prompt + conversation).
 * La raison d'être de la mémoire de conversation est encodée ici : un prompt
 * court dans un fil maths/raisonnement ne part PAS sur Haiku.
 *
 * Hors périmètre V0 : tout modèle ML — l'API réelle décidera en production.
 */
import type { Signals } from './signals';

/** Seuil de contexte long → suggestion de repartir de zéro (tokens estimés). */
export const LONG_CONTEXT_TOKENS = 8000;

export interface MockDecision {
  recommended_model: string;
  /** Explicabilité obligatoire — clé traduite en langage clair par l'UI. */
  rule: string;
  confidence: number;
  suggest_new_conversation: boolean;
}

/** Décision pure à partir des signaux — 4 règles V0, ton humble assumé. */
export function decide(signals: Signals): MockDecision {
  const { prompt, conversation } = signals;
  const suggest = conversation.context_token_est > LONG_CONTEXT_TOKENS;

  // Règle 1 — contexte code : le fil ou le prompt contiennent du code.
  if (prompt.has_code || conversation.seen_code || prompt.keyword_flags.includes('code')) {
    return {
      recommended_model: 'claude-sonnet-5',
      rule: 'mock:code_context',
      confidence: 0.7,
      suggest_new_conversation: suggest,
    };
  }

  // Règle 2 — contexte raisonnement/maths : MÊME si le prompt est court
  // (« démontre-le ») — c'est LA raison d'être de la mémoire de conversation.
  if (
    prompt.has_math ||
    conversation.seen_math ||
    conversation.seen_reasoning ||
    prompt.keyword_flags.includes('demonstration')
  ) {
    return {
      recommended_model: 'claude-sonnet-5',
      rule: 'mock:reasoning_context',
      // Prompt court sur signal ambigu ⇒ confiance moindre (ton humble).
      confidence: prompt.token_est < 50 ? 0.6 : 0.75,
      suggest_new_conversation: suggest,
    };
  }

  // Règle 3 — court et simple, dans un fil léger : Haiku suffit probablement.
  const heavyFlags = prompt.keyword_flags.some((flag) => flag === 'contrat' || flag === 'analyse');
  if (
    prompt.token_est < 300 &&
    !heavyFlags &&
    conversation.msg_count <= 6 &&
    conversation.context_token_est < 2000
  ) {
    return {
      recommended_model: 'claude-haiku-4-5',
      rule: 'mock:short_simple',
      confidence: 0.8,
      suggest_new_conversation: suggest,
    };
  }

  // Règle 4 — tâche lourde (contrat/analyse, prompt long ou fil chargé).
  if (heavyFlags || prompt.token_est > 800 || conversation.context_token_est > 4000) {
    return {
      recommended_model: 'claude-opus-4-8',
      rule: 'mock:complex_task',
      confidence: 0.65,
      suggest_new_conversation: suggest,
    };
  }

  // Par défaut : équilibre, confiance modeste (signal ambigu, on le dit).
  return {
    recommended_model: 'claude-sonnet-5',
    rule: 'mock:default_balanced',
    confidence: 0.55,
    suggest_new_conversation: suggest,
  };
}
