/**
 * Textes FR de l'UI — centralisés, surchargeables par `config.messages.fr`.
 *
 * Règle 7 : TON HUMBLE. « recommandé », « suffit probablement », jamais
 * péremptoire ; sur signal ambigu, on le dit. Les textes ne contiennent
 * jamais de contenu utilisateur.
 */

export type Messages = Record<string, string>;

export const FR_MESSAGES: Messages = {
  badge_title: 'Sobrio — recommandation de modèle (n’agit jamais à votre place)',
  panel_title: 'Sobrio',
  recommended_suffix: 'recommandé',
  probably_enough: 'suffit probablement pour cette demande.',
  confidence_label: 'Confiance',
  ambiguous_note:
    'Signal ambigu — si cette conversation demande un raisonnement complexe, restez sur Sonnet.',
  cost_label: 'Coût estimé',
  cost_unit: '€ / appel',
  energy_label: 'Énergie estimée',
  energy_unit: 'Wh · périmètre : inférence',
  budget_label: 'Budget',
  budget_used_suffix: '% utilisé',
  use_model: 'Utiliser {model}',
  use_model_hint: 'Note votre intention — ne change rien dans la page.',
  choose_other: 'Choisir un autre modèle…',
  why_link: 'Pourquoi ?',
  followed_ack: 'Merci, c’est noté.',
  overridden_ack: 'C’est noté — votre choix compte pour ajuster nos recommandations.',
  long_conversation_banner:
    'Conversation longue — repartir d’une nouvelle conversation coûtera probablement moins.',

  // Explications des règles en langage clair (clé = `rule` de la réponse).
  'rule:mock:short_simple':
    'Votre demande semble courte et simple : un modèle léger suffit probablement.',
  'rule:mock:code_context':
    'Cette conversation contient du code : un modèle intermédiaire est recommandé.',
  'rule:mock:reasoning_context':
    'Cette conversation contient des maths ou un raisonnement suivi : un modèle plus capable est recommandé, même pour un message court.',
  'rule:mock:complex_task':
    'La tâche semble lourde (analyse, contrat ou long contexte) : un modèle plus capable est recommandé.',
  'rule:mock:default_balanced': 'Signal peu marqué : un modèle équilibré est proposé par prudence.',
  'rule:heuristic:short_simple':
    'Votre demande semble courte et simple : un modèle léger suffit probablement.',
  'rule:heuristic:code_task':
    'Cette demande contient du code : un modèle intermédiaire est recommandé.',
  'rule:heuristic:complex_task':
    'La tâche semble complexe : un modèle plus capable est recommandé.',
  rule_fallback: 'Recommandation fondée sur des signaux sans contenu (longueur, code, contexte).',
};

/** Noms d'affichage des modèles (ids du catalogue → libellés lisibles). */
export const MODEL_DISPLAY_NAMES: Readonly<Record<string, string>> = {
  'haiku-4-5': 'Claude Haiku 4.5',
  'sonnet-4-6': 'Claude Sonnet 4.6',
  'opus-4-8': 'Claude Opus 4.8',
};

/** Libellé lisible d'un id de modèle (l'id brut sinon). */
export function modelDisplayName(modelId: string): string {
  return MODEL_DISPLAY_NAMES[modelId] ?? modelId;
}

/**
 * Fusionne les textes par défaut avec les surcharges de la config distante
 * (seules les valeurs string sont retenues — jamais d'objet inattendu).
 */
export function mergeMessages(overrides: Record<string, unknown> | undefined): Messages {
  const merged: Messages = { ...FR_MESSAGES };
  if (overrides) {
    for (const [key, value] of Object.entries(overrides)) {
      if (typeof value === 'string') merged[key] = value;
    }
  }
  return merged;
}

/** Explication en langage clair d'une clé `rule` (ton humble). */
export function ruleExplanation(rule: string, messages: Messages): string {
  return messages[`rule:${rule}`] ?? messages['rule_fallback'] ?? '';
}

/** Interpolation minimaliste `{model}` — aucun contenu utilisateur. */
export function formatMessage(template: string, values: Record<string, string>): string {
  return template.replace(/\{(\w+)\}/g, (_, key: string) => values[key] ?? '');
}
