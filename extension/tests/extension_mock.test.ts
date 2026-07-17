/**
 * Boucle 2 — conformité du mock au contrat V0 : test de FORME des réponses
 * (champs exacts, fourchettes min ≤ max, règles vivantes selon les signaux).
 */
import { describe, expect, it } from 'vitest';

import { MockClient } from '../src/mockClient';
import { LONG_CONTEXT_TOKENS } from '../src/mockRules';
import { computePromptSignals, type ConversationSignals, type Signals } from '../src/signals';

const QUIET_CONVERSATION: ConversationSignals = {
  msg_count: 2,
  context_token_est: 120,
  seen_code: false,
  seen_math: false,
  seen_reasoning: false,
  current_model: 'claude-opus-4-8',
  recos_shown: 0,
  recos_followed: 0,
  derogations_up: 0,
};

function signalsFor(text: string, conversation: Partial<ConversationSignals> = {}): Signals {
  return {
    prompt: computePromptSignals(text),
    conversation: { ...QUIET_CONVERSATION, ...conversation },
  };
}

async function reco(signals: Signals, client = new MockClient({ latencyMs: 0 })) {
  const response = await client.recommend(signals);
  expect(response).not.toBeNull();
  return response!;
}

describe('MockClient — forme du contrat V0', () => {
  it('la réponse a exactement les champs du contrat', async () => {
    const response = await reco(signalsFor('Bonjour !'));
    expect(Object.keys(response).sort()).toEqual([
      'budget',
      'confidence',
      'impact_estimate',
      'reco_id',
      'recommended_model',
      'rule',
      'suggest_new_conversation',
    ]);
    expect(Object.keys(response.impact_estimate).sort()).toEqual([
      'cost_eur_max',
      'cost_eur_min',
      'energy_wh_max',
      'energy_wh_min',
    ]);
  });

  it('fourchettes obligatoires : min ≤ max, jamais de valeur unique (règle 5)', async () => {
    const { impact_estimate: impact } = await reco(
      signalsFor('Analyse détaillée de ce contrat de 40 pages, chiffrage et risques.'),
    );
    expect(impact.cost_eur_min).toBeLessThan(impact.cost_eur_max);
    expect(impact.energy_wh_min).toBeLessThan(impact.energy_wh_max);
    expect(impact.cost_eur_min).toBeGreaterThan(0);
    expect(impact.energy_wh_min).toBeGreaterThan(0);
  });

  it('confidence reste dans [0,1] et rule est non vide (explicabilité)', async () => {
    const response = await reco(signalsFor('Traduis ce paragraphe en anglais.'));
    expect(response.confidence).toBeGreaterThan(0);
    expect(response.confidence).toBeLessThanOrEqual(1);
    expect(response.rule.length).toBeGreaterThan(0);
  });
});

describe('MockClient — règles vivantes', () => {
  it('court + simple + fil léger → haiku', async () => {
    const response = await reco(signalsFor('Quelle heure est-il à Tokyo ?'));
    expect(response.recommended_model).toBe('claude-haiku-4-5');
    expect(response.rule).toBe('mock:short_simple');
  });

  it('code (prompt ou fil) → sonnet', async () => {
    const fromPrompt = await reco(signalsFor('Corrige : ```js\nlet a = 1;\n```'));
    expect(fromPrompt.recommended_model).toBe('claude-sonnet-5');
    const fromThread = await reco(signalsFor('et maintenant ?', { seen_code: true }));
    expect(fromThread.recommended_model).toBe('claude-sonnet-5');
  });

  it('contexte long → suggest_new_conversation=true', async () => {
    const response = await reco(
      signalsFor('ok continue', { context_token_est: LONG_CONTEXT_TOKENS + 1 }),
    );
    expect(response.suggest_new_conversation).toBe(true);
  });

  it('fil court → suggest_new_conversation=false', async () => {
    const response = await reco(signalsFor('ok continue'));
    expect(response.suggest_new_conversation).toBe(false);
  });

  it('budget absent : le champ est null (état UI dédié)', async () => {
    const client = new MockClient({ latencyMs: 0, budget: 'absent' });
    const response = await reco(signalsFor('Bonjour'), client);
    expect(response.budget).toBeNull();
  });

  it('les reco_id sont uniques', async () => {
    const client = new MockClient({ latencyMs: 0 });
    const first = await reco(signalsFor('a'), client);
    const second = await reco(signalsFor('b'), client);
    expect(first.reco_id).not.toBe(second.reco_id);
  });
});
