/**
 * Boucle 1 — test « ZÉRO TEXTE » (règle 1, non négociable).
 *
 * Le bloc `signals` sérialisé ne doit contenir AUCUN texte libre :
 * - aucune valeur string de plus de 24 caractères ;
 * - aucun fragment du texte saisi ni des bulles de conversation ;
 * - toute string appartient à un vocabulaire fermé connu.
 */
import { describe, expect, it } from 'vitest';

import { ConversationMemory } from '../src/conversationMemory';
import { computePromptSignals, KEYWORD_FLAGS_V0, KNOWN_MODELS, type Signals } from '../src/signals';

/** Vocabulaire fermé : les seules strings autorisées dans les signaux. */
const CLOSED_VOCABULARY = new Set<string>([
  'fr',
  'en',
  'other',
  ...KEYWORD_FLAGS_V0,
  ...KNOWN_MODELS,
]);

/** Collecte récursivement toutes les valeurs string d'un objet sérialisable. */
function collectStrings(value: unknown, found: string[] = []): string[] {
  if (typeof value === 'string') found.push(value);
  else if (Array.isArray(value)) value.forEach((item) => collectStrings(item, found));
  else if (value && typeof value === 'object')
    Object.values(value).forEach((item) => collectStrings(item, found));
  return found;
}

const TYPED_TEXT =
  'SENTINELLE_CONFIDENTIELLE_9F3K : le client Aristide Bergamote négocie un contrat ' +
  'de 4,2 M€ avec la société Zéphyrine ; démontre que la clause 7.3 est abusive. ' +
  '∫ x² dx — voir aussi def secret_function(): return "mot_de_passe_racine"';

function buildSignals(): Signals {
  const memory = new ConversationMemory();
  memory.updateFromPage({
    threadId: 't-zero-texte',
    modelLabel: 'Claude Opus 4.8',
    bubbles: [
      { role: 'user', text: TYPED_TEXT },
      { role: 'assistant', text: `Réponse qui répète la SENTINELLE_CONFIDENTIELLE_9F3K.` },
    ],
  });
  memory.noteRecoShown();
  return { prompt: computePromptSignals(TYPED_TEXT), conversation: memory.toSignals() };
}

describe('Zéro texte — le payload signals ne transporte jamais de contenu', () => {
  it('aucune valeur string ne dépasse 24 caractères', () => {
    for (const value of collectStrings(buildSignals())) {
      expect(value.length).toBeLessThanOrEqual(24);
    }
  });

  it('toute string appartient au vocabulaire fermé (langue, drapeaux, modèles)', () => {
    for (const value of collectStrings(buildSignals())) {
      expect(CLOSED_VOCABULARY.has(value), `string hors vocabulaire fermé : "${value}"`).toBe(true);
    }
  });

  it('aucun fragment du texte saisi ou des bulles ne fuit dans le JSON', () => {
    const serialized = JSON.stringify(buildSignals());
    for (const fragment of [
      'SENTINELLE',
      'Aristide',
      'Bergamote',
      'Zéphyrine',
      'clause 7.3',
      'secret_function',
      'mot_de_passe',
    ]) {
      expect(serialized).not.toContain(fragment);
    }
  });

  it('les champs du bloc signals sont exactement ceux du contrat', () => {
    const signals = buildSignals();
    expect(Object.keys(signals).sort()).toEqual(['conversation', 'prompt']);
    expect(Object.keys(signals.prompt).sort()).toEqual([
      'char_len',
      'has_code',
      'has_math',
      'keyword_flags',
      'lang',
      'token_est',
    ]);
    expect(Object.keys(signals.conversation).sort()).toEqual([
      'context_token_est',
      'current_model',
      'derogations_up',
      'msg_count',
      'recos_followed',
      'recos_shown',
      'seen_code',
      'seen_math',
      'seen_reasoning',
    ]);
  });
});
