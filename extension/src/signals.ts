/**
 * Signaux V0 — le bloc `signals` du contrat de l'extension : des NOMBRES et
 * des DRAPEAUX, calculés localement. C'est la mémoire de conversation qui
 * permet de ne pas router naïvement un prompt court vers Haiku.
 *
 * RÈGLE 1 (non négociable) : aucun texte de prompt ou de conversation ne sort
 * de ce module. Les seules chaînes émises appartiennent à des vocabulaires
 * FERMÉS (langue, drapeaux, identifiants de modèle du catalogue) — jamais du
 * texte libre. Le test « zéro texte » l'atteste.
 *
 * NOTE CONTRAT : ce bloc `signals` étend le contrat v1.0 (`features`) — voir
 * la RFC docs/rfc/RFC-0001-signals-conversation.md. En attendant son
 * adoption, le mode `api` mappe ces signaux vers les `features` v1.0
 * (src/client.ts) ; le mode `mock` consomme le bloc complet.
 */
import type { Lang } from './api';
import { detectLang, estimateTokens, hasCode, normalize } from './features';

/** Liste FERMÉE des drapeaux V0 (v1.0 + `demonstration` — cf. RFC v1.1). */
export const KEYWORD_FLAGS_V0 = [
  'contrat',
  'analyse',
  'code',
  'resume',
  'traduction',
  'demonstration',
] as const;
export type KeywordFlagV0 = (typeof KEYWORD_FLAGS_V0)[number];

/** Signaux du prompt en cours de saisie — mesures et drapeaux uniquement. */
export interface PromptSignals {
  char_len: number;
  token_est: number;
  lang: Lang;
  has_code: boolean;
  has_math: boolean;
  keyword_flags: KeywordFlagV0[];
}

/** Signaux agrégés du fil de conversation — JAMAIS le texte. */
export interface ConversationSignals {
  msg_count: number;
  context_token_est: number;
  seen_code: boolean;
  seen_math: boolean;
  seen_reasoning: boolean;
  /** Id du catalogue (vocabulaire fermé) ou null — jamais le libellé brut. */
  current_model: string | null;
  recos_shown: number;
  recos_followed: number;
  derogations_up: number;
}

export interface Signals {
  prompt: PromptSignals;
  conversation: ConversationSignals;
}

// ---------------------------------------------------------------------------
// Maths — symboles, LaTeX, motifs numériques, lexique fr/en (normalisé).
// ---------------------------------------------------------------------------

const MATH_MOTIFS: readonly RegExp[] = [
  /[∑∫√π≤≥≠±×÷∂∞]/u,
  /[²³]/u,
  /\\(frac|int|sum|sqrt|lim|forall|exists|begin\{)/, // LaTeX
  /\$[^$\n]+\$/, // $ ... $ inline
  /\d\s*[+\-*/^=]\s*\d/, // 3 + 4, x=2…
  /\b\d+\s*\/\s*\d+\b/,
];

/** Lexique mathématique (préfixes, texte normalisé sans accents). */
const MATH_STEMS: readonly string[] = [
  'demontr', // démontre, démontrer, démontrons…
  'demonstration',
  'theoreme',
  'preuve',
  'lemme',
  'integrale',
  'derivee',
  'equation',
  'matrice',
  'probabilit',
  'proof',
  'theorem',
  'integral',
  'derivative',
  'matrix',
];

/** Vrai si le texte contient un signal mathématique. TODO(V1) : affiner. */
export function hasMath(text: string): boolean {
  if (MATH_MOTIFS.some((motif) => motif.test(text))) return true;
  const normalized = normalize(text);
  return MATH_STEMS.some((stem) => normalized.includes(stem));
}

// ---------------------------------------------------------------------------
// Drapeaux V0 — détection par racine (insensible casse/accents/dérivés).
// ---------------------------------------------------------------------------

/** Racines de détection par drapeau (le drapeau émis reste la liste fermée). */
const FLAG_STEMS: Readonly<Record<KeywordFlagV0, readonly string[]>> = {
  contrat: ['contrat'],
  analyse: ['analys'], // analyse, analyser, analysis
  code: ['code', 'coder', 'script', 'fonction ', 'function '],
  resume: ['resum', 'summar'], // résume, résumé, summary, summarize
  traduction: ['traduction', 'traduis', 'traduire', 'translat'],
  demonstration: ['demonstr', 'demontr', 'prouve', 'preuve', 'proof'],
};

/** Drapeaux détectés — sous-ensemble de la liste FERMÉE, rien d'autre. */
export function detectKeywordFlagsV0(text: string): KeywordFlagV0[] {
  const normalized = normalize(text);
  return KEYWORD_FLAGS_V0.filter((flag) =>
    FLAG_STEMS[flag].some((stem) => normalized.includes(stem)),
  );
}

// ---------------------------------------------------------------------------
// Modèle courant — normalisation vers le vocabulaire FERMÉ du catalogue.
// ---------------------------------------------------------------------------

/**
 * Ids du catalogue (contracts/model_catalog.yaml), identifiants d'API
 * Anthropic, du moins au plus cher. Gamme vérifiée en ligne le 2026-07-17.
 */
export const KNOWN_MODELS = [
  'claude-haiku-4-5',
  'claude-sonnet-5',
  'claude-opus-4-8',
  'claude-fable-5',
] as const;

/**
 * Famille (mot-clé du libellé claude.ai) → id du catalogue. Une seule version
 * courante par famille : la correspondance par famille est donc robuste aux
 * libellés à un ou deux chiffres (« Sonnet 5 » comme « Opus 4.8 »).
 */
const FAMILY_TO_ID: Readonly<Record<string, (typeof KNOWN_MODELS)[number]>> = {
  haiku: 'claude-haiku-4-5',
  sonnet: 'claude-sonnet-5',
  opus: 'claude-opus-4-8',
  fable: 'claude-fable-5',
};

/**
 * Étiquette de la page (« Claude Opus 4.8 ») → id du catalogue
 * (« claude-opus-4-8 ») ou null si inconnu. On n'émet JAMAIS le libellé brut
 * (texte de la page) : seule une valeur du vocabulaire fermé peut sortir
 * (règle 1, par construction).
 */
export function normalizeModelLabel(label: string | null): string | null {
  if (!label) return null;
  const normalized = normalize(label);
  for (const family of Object.keys(FAMILY_TO_ID)) {
    if (normalized.includes(family)) return FAMILY_TO_ID[family]!;
  }
  return null;
}

// ---------------------------------------------------------------------------
// Point d'entrée prompt.
// ---------------------------------------------------------------------------

/** Texte saisi → signaux du prompt. Seuls des nombres/drapeaux en sortent. */
export function computePromptSignals(text: string): PromptSignals {
  const charLen = text.length;
  return {
    char_len: charLen,
    token_est: estimateTokens(charLen),
    lang: detectLang(text),
    has_code: hasCode(text),
    has_math: hasMath(text),
    keyword_flags: detectKeywordFlagsV0(text),
  };
}
