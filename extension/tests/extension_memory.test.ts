/**
 * Boucle 1 — mémoire de conversation : agrégation, reset, scénario
 * « démontre-le » (LA raison d'être de la mémoire).
 */
import { describe, expect, it } from 'vitest';

import { ConversationMemory, type PageView } from '../src/conversationMemory';
import { decide } from '../src/mockRules';
import { computePromptSignals } from '../src/signals';

const MATH_THREAD: PageView = {
  threadId: 't-001',
  modelLabel: 'Claude Opus 4.8',
  bubbles: [
    { role: 'user', text: 'Soit f(x) = x² + 3x. Calcule la dérivée sur [0,1].' },
    { role: 'assistant', text: "f'(x) = 2x + 3, donc la preuve suit le théorème fondamental." },
  ],
};

const SMALLTALK_THREAD: PageView = {
  threadId: 't-002',
  modelLabel: 'Claude Haiku 4.5',
  bubbles: [
    { role: 'user', text: 'Bonjour !' },
    { role: 'assistant', text: 'Bonjour, comment puis-je vous aider ?' },
  ],
};

describe('ConversationMemory — agrégation', () => {
  it('compte les messages et estime le contexte cumulé', () => {
    const memory = new ConversationMemory();
    memory.updateFromPage(MATH_THREAD);
    const signals = memory.toSignals();
    expect(signals.msg_count).toBe(2);
    expect(signals.context_token_est).toBeGreaterThan(0);
  });

  it('repère les maths et le raisonnement au fil des tours', () => {
    const memory = new ConversationMemory();
    memory.updateFromPage(MATH_THREAD);
    const signals = memory.toSignals();
    expect(signals.seen_math).toBe(true);
    expect(signals.seen_reasoning).toBe(true);
    expect(signals.seen_code).toBe(false);
  });

  it('normalise le modèle courant (jamais le libellé brut)', () => {
    const memory = new ConversationMemory();
    memory.updateFromPage(MATH_THREAD);
    expect(memory.toSignals().current_model).toBe('claude-opus-4-8');
  });

  it('un fil banal ne lève aucun drapeau', () => {
    const memory = new ConversationMemory();
    memory.updateFromPage(SMALLTALK_THREAD);
    const signals = memory.toSignals();
    expect(signals.seen_math).toBe(false);
    expect(signals.seen_code).toBe(false);
  });
});

describe('ConversationMemory — cycle de vie', () => {
  it('réinitialise quand le fil change (threadId différent)', () => {
    const memory = new ConversationMemory();
    memory.updateFromPage(MATH_THREAD);
    memory.noteRecoShown();
    memory.noteFollowed();
    expect(memory.toSignals().recos_shown).toBe(1);

    memory.updateFromPage(SMALLTALK_THREAD); // nouveau fil
    const signals = memory.toSignals();
    expect(signals.recos_shown).toBe(0);
    expect(signals.recos_followed).toBe(0);
    expect(signals.seen_math).toBe(false);
  });

  it('réinitialise sur régression du nombre de bulles quand le fil est anonyme', () => {
    const memory = new ConversationMemory();
    memory.updateFromPage({ ...MATH_THREAD, threadId: null });
    memory.noteRecoShown();
    memory.updateFromPage({ threadId: null, modelLabel: null, bubbles: [] });
    expect(memory.toSignals().recos_shown).toBe(0);
    expect(memory.toSignals().msg_count).toBe(0);
  });

  it('conserve les compteurs de recos au sein du même fil', () => {
    const memory = new ConversationMemory();
    memory.updateFromPage(MATH_THREAD);
    memory.noteRecoShown();
    memory.updateFromPage({
      ...MATH_THREAD,
      bubbles: [...MATH_THREAD.bubbles, { role: 'user', text: 'et ensuite ?' }],
    });
    expect(memory.toSignals().recos_shown).toBe(1);
    expect(memory.toSignals().msg_count).toBe(3);
  });

  it('derogations_up ne compte que les dérogations vers plus cher', () => {
    const memory = new ConversationMemory();
    memory.updateFromPage(MATH_THREAD);
    memory.noteDerogation('claude-haiku-4-5', 'claude-opus-4-8'); // vers le haut
    memory.noteDerogation('claude-opus-4-8', 'claude-haiku-4-5'); // vers le bas — ignorée
    expect(memory.toSignals().derogations_up).toBe(1);
  });
});

describe('Scénario clé — « démontre-le » dans un fil maths', () => {
  it('un prompt court dans un fil seen_math=true ne part PAS sur Haiku', () => {
    const memory = new ConversationMemory();
    memory.updateFromPage(MATH_THREAD);

    const signals = {
      prompt: computePromptSignals('démontre-le'),
      conversation: memory.toSignals(),
    };
    const decision = decide(signals);
    expect(decision.recommended_model).not.toBe('claude-haiku-4-5');
    expect(decision.recommended_model).toBe('claude-sonnet-5');
    expect(decision.rule).toBe('mock:reasoning_context');
  });

  it("contre-scénario : le même prompt court dans un fil neuf et banal part sur Haiku ('vas-y')", () => {
    const memory = new ConversationMemory();
    memory.updateFromPage(SMALLTALK_THREAD);

    const signals = {
      // Prompt court SANS signal maths : sans mémoire, le routage naïf.
      prompt: computePromptSignals('vas-y'),
      conversation: memory.toSignals(),
    };
    expect(decide(signals).recommended_model).toBe('claude-haiku-4-5');
  });

  it('ISOLE la mémoire : prompt NEUTRE (sans keyword) dans un fil maths → reco ≠ Haiku', () => {
    // « vas-y » ne déclenche AUCUN drapeau du prompt (ni has_math, ni le flag
    // 'demonstration'). Seul conversation.seen_math (la mémoire) peut router
    // hors Haiku — c'est la preuve isolée de l'apport de la mémoire.
    const neutralPrompt = computePromptSignals('vas-y');
    expect(neutralPrompt.has_math).toBe(false);
    expect(neutralPrompt.keyword_flags).not.toContain('demonstration');

    const memory = new ConversationMemory();
    memory.updateFromPage(MATH_THREAD); // seen_math = true
    const decision = decide({ prompt: neutralPrompt, conversation: memory.toSignals() });
    expect(decision.recommended_model).not.toBe('claude-haiku-4-5');
    expect(decision.recommended_model).toBe('claude-sonnet-5');
    expect(decision.rule).toBe('mock:reasoning_context');
  });
});
