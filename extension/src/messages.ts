/**
 * Textes de l'UI — centralisés, surchargeables par `config.messages.{locale}`.
 *
 * i18n : le FR est la locale complète ; l'EN est un squelette prêt à compléter
 * (TODO(V2) : traduction intégrale). `getMessages(locale, overrides)` retourne
 * la base de la locale demandée (repli FR) fusionnée avec les surcharges.
 *
 * Règle 7 : TON HUMBLE. « recommandé », « suffit probablement », jamais
 * péremptoire ; sur signal ambigu, on le dit. Les textes ne contiennent
 * jamais de contenu utilisateur.
 */

export type Messages = Record<string, string>;

export type Locale = 'fr' | 'en';

/** Modes de l'organisation (config `mode`) — inflèchissent le ton affiché. */
export type ExtensionMode = 'eco' | 'equilibre' | 'qualite';

export const FR_MESSAGES: Messages = {
  badge_title: 'Sobrio — recommandation de modèle (n’agit jamais à votre place)',
  panel_title: 'Sobrio',
  panel_aria_label: 'Recommandation de modèle Sobrio',
  recommended_suffix: 'recommandé',
  probably_enough: 'suffit probablement pour cette demande.',
  confidence_label: 'Confiance',
  // Ne nomme aucun modèle en dur : reste cohérent quelle que soit la reco.
  ambiguous_note:
    'Signal ambigu — si cette conversation demande un raisonnement complexe, préférez un modèle plus capable.',
  cost_label: 'Coût estimé',
  cost_unit: '€ / appel',
  energy_label: 'Énergie estimée',
  energy_unit: 'Wh · périmètre : inférence',
  budget_label: 'Budget',
  budget_used_suffix: '% utilisé',
  use_model: 'Utiliser {model}',
  // Mode guide : l'extension n'agit pas — libellé d'intention, non d'action.
  use_model_guide: 'J’utiliserai {model}',
  use_model_hint: 'Note votre intention.',
  choose_other: 'Choisir un autre modèle…',
  why_link: 'Pourquoi ?',
  close_label: 'Fermer le panneau',
  followed_ack: 'Merci, c’est noté.',
  overridden_ack: 'C’est noté — votre choix compte pour ajuster nos recommandations.',
  long_conversation_banner:
    'Conversation longue — repartir d’une nouvelle conversation coûtera probablement moins.',

  // Bascule de modèle (RFC-0003 / Chantier B). {model} = libellé du modèle.
  auto_switched: 'Basculé sur {model}',
  auto_switch_hint: 'Bascule automatique — vous gardez la main.',
  cancel_auto: 'Annuler',
  switched_back: 'Modèle précédent restauré.',
  already_on_model: 'Déjà sur {model} — rien à faire.',
  // Mode guide : l'extension n'agit pas sur la page, elle indique quoi faire.
  guide_hint: 'À sélectionner dans le menu de modèle de Claude.',

  // Ton par mode d'organisation (config.mode).
  'mode:eco': 'Priorité à la sobriété : on privilégie le modèle le plus léger qui suffit.',
  'mode:equilibre': 'Équilibre coût / qualité : le modèle proposé vise le juste nécessaire.',
  'mode:qualite': 'Priorité à la qualité : un modèle plus capable est proposé en cas de doute.',

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

/**
 * Squelette EN — prêt à compléter. Volontairement PARTIEL en V1 (TODO(V2)) :
 * les clés absentes retombent sur le FR via `getMessages`.
 */
export const EN_MESSAGES: Messages = {
  badge_title: 'Sobrio — model recommendation (never acts for you)',
  panel_title: 'Sobrio',
  recommended_suffix: 'recommended',
  confidence_label: 'Confidence',
  cost_label: 'Estimated cost',
  energy_label: 'Estimated energy',
  use_model: 'Use {model}',
  why_link: 'Why?',
  close_label: 'Close panel',
};

const LOCALES: Readonly<Record<Locale, Messages>> = { fr: FR_MESSAGES, en: EN_MESSAGES };

/**
 * Noms d'affichage des modèles (ids d'API → libellés IDENTIQUES au sélecteur
 * de modèle de claude.ai). Gamme vérifiée en ligne le 2026-07-17.
 */
export const MODEL_DISPLAY_NAMES: Readonly<Record<string, string>> = {
  'claude-haiku-4-5': 'Claude Haiku 4.5',
  'claude-sonnet-5': 'Claude Sonnet 5',
  'claude-opus-4-8': 'Claude Opus 4.8',
  'claude-fable-5': 'Claude Fable 5',
};

/** Libellé lisible d'un id de modèle (l'id brut sinon). */
export function modelDisplayName(modelId: string): string {
  return MODEL_DISPLAY_NAMES[modelId] ?? modelId;
}

/**
 * Fusionne les textes par défaut (FR) avec les surcharges de la config
 * distante (seules les valeurs string sont retenues). Conservé pour
 * compatibilité — préférer `getMessages`.
 */
export function mergeMessages(overrides: Record<string, unknown> | undefined): Messages {
  return getMessages('fr', overrides);
}

/**
 * Messages pour une locale : base FR complète, EN complété par repli FR, plus
 * surcharges de la config d'organisation (`config.messages.{locale}`).
 */
export function getMessages(
  locale: Locale = 'fr',
  overrides: Record<string, unknown> | undefined = undefined,
): Messages {
  const base: Messages = locale === 'en' ? { ...FR_MESSAGES, ...LOCALES.en } : { ...FR_MESSAGES };
  if (overrides) {
    for (const [key, value] of Object.entries(overrides)) {
      if (typeof value === 'string') base[key] = value;
    }
  }
  return base;
}

/** Note de ton correspondant au mode d'organisation (ou chaîne vide). */
export function modeNote(mode: ExtensionMode | undefined, messages: Messages): string {
  return mode ? (messages[`mode:${mode}`] ?? '') : '';
}

/** Explication en langage clair d'une clé `rule` (ton humble). */
export function ruleExplanation(rule: string, messages: Messages): string {
  return messages[`rule:${rule}`] ?? messages['rule_fallback'] ?? '';
}

/** Interpolation minimaliste `{model}` — aucun contenu utilisateur. */
export function formatMessage(template: string, values: Record<string, string>): string {
  return template.replace(/\{(\w+)\}/g, (_, key: string) => values[key] ?? '');
}
