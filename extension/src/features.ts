/**
 * Calcul LOCAL des features du prompt — fonctions PURES, sans effet de bord.
 *
 * Règle n°1 (non négociable) : AUCUN texte ne sort de ce module. Il reçoit le
 * texte du prompt, le réduit en mesures/indicateurs, et retourne UNIQUEMENT
 * l'objet `Features` conforme au schéma `Features` de contracts/openapi.yaml.
 * Aucun log, aucun stockage, aucune exfiltration.
 */
import type { Features, KeywordFlag, Lang } from './api';

/** Liste FERMÉE du contrat — ne pas étendre sans RFC (règle n°7). */
export const KEYWORD_FLAGS: readonly KeywordFlag[] = [
  'contrat',
  'analyse',
  'code',
  'resume',
  'traduction',
];

/** Normalise : minuscules + suppression des diacritiques (é → e, ç → c…). */
function normalize(text: string): string {
  return text
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase();
}

/**
 * Estimation grossière du nombre de tokens : chars / 4, arrondi supérieur.
 * TODO(LotA) : brancher un tokenizer réel (approximation volontaire en v0).
 */
export function estimateTokens(charLen: number): number {
  return Math.ceil(Math.max(0, charLen) / 4);
}

/** Mots fréquents français (formes normalisées, sans accents). */
const FR_STOPWORDS = new Set([
  'le',
  'la',
  'les',
  'de',
  'des',
  'du',
  'un',
  'une',
  'et',
  'est',
  'que',
  'qui',
  'pour',
  'dans',
  'ce',
  'cette',
  'il',
  'elle',
  'je',
  'tu',
  'nous',
  'vous',
  'pas',
  'sur',
  'avec',
  'mais',
  'son',
  'ses',
  'aux',
  'etre',
  'avoir',
  'fais',
  'peux',
]);

/** Mots fréquents anglais. */
const EN_STOPWORDS = new Set([
  'the',
  'of',
  'and',
  'to',
  'in',
  'is',
  'that',
  'for',
  'it',
  'with',
  'as',
  'this',
  'be',
  'are',
  'was',
  'at',
  'by',
  'from',
  'or',
  'an',
  'not',
  'you',
  'we',
  'they',
  'have',
  'has',
  'can',
  'please',
  'write',
]);

/**
 * Détection naïve de langue par comptage de mots fréquents.
 * Égalité ou aucun indice ⇒ 'other'. TODO(LotA) : heuristique plus robuste.
 */
export function detectLang(text: string): Lang {
  const words = normalize(text).split(/[^a-z]+/);
  let fr = 0;
  let en = 0;
  for (const word of words) {
    if (FR_STOPWORDS.has(word)) fr += 1;
    if (EN_STOPWORDS.has(word)) en += 1;
  }
  if (fr > en && fr > 0) return 'fr';
  if (en > fr && en > 0) return 'en';
  return 'other';
}

/** Motifs de code : fences, backticks, déclarations, imports… (heuristique v0). */
const CODE_MOTIFS: readonly RegExp[] = [
  /```/, // fence Markdown
  /`[^`\n]{2,}`/, // code inline
  /\b(function|const|let|var)\s+\w+/,
  /\bdef\s+\w+\s*\(/,
  /\bclass\s+\w+\s*[({:]/,
  /^\s*(import|from)\s+[\w./@'"-]+/m,
  /\b(console\.log|print)\s*\(/,
  /=>/,
];

/** Vrai si le texte contient un motif de code. TODO(LotA) : affiner. */
export function hasCode(text: string): boolean {
  return CODE_MOTIFS.some((motif) => motif.test(text));
}

/** Indices (normalisés, sans accents) qu'une pièce jointe est mentionnée. */
const ATTACHMENT_HINTS: readonly string[] = [
  'piece jointe',
  'pieces jointes',
  'ci-joint',
  'ci joint',
  'fichier joint',
  'document joint',
  'en pj',
  'attached',
  'attachment',
  'uploaded file',
];

/** Vrai si le texte évoque une pièce jointe (heuristique v0). */
export function hasAttachmentHint(text: string): boolean {
  const normalized = normalize(text);
  return ATTACHMENT_HINTS.some((hint) => normalized.includes(hint));
}

/**
 * Détection des mots-clés de la liste fermée du contrat, insensible à la
 * casse ET aux accents (« Résumé » ⇒ 'resume', « CONTRAT » ⇒ 'contrat').
 * Correspondance sur mot entier après normalisation.
 * TODO(LotA) : gérer pluriels/dérivés (lemmatisation légère).
 */
export function detectKeywordFlags(text: string): KeywordFlag[] {
  const normalized = normalize(text);
  return KEYWORD_FLAGS.filter((flag) => new RegExp(`\\b${flag}\\b`).test(normalized));
}

/**
 * Point d'entrée : texte → objet Features conforme au contrat.
 * Seul cet objet (mesures + indicateurs) quitte le module — jamais le texte.
 */
export function computeFeatures(text: string): Features {
  const charLen = text.length;
  return {
    char_len: charLen,
    token_est: estimateTokens(charLen),
    lang: detectLang(text),
    has_code: hasCode(text),
    has_attachment_hint: hasAttachmentHint(text),
    keyword_flags: detectKeywordFlags(text),
  };
}
