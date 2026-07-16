/**
 * Boucle 4 — parcours COMPLET en mode mock : saisie → reco affichée → suivi /
 * dérogation → événement de télémétrie capturé par le mock, conforme au
 * contrat strict. La mémoire de conversation est mise à jour au passage.
 */
import { beforeEach, describe, expect, it } from 'vitest';

import { ConversationMemory } from '../src/conversationMemory';
import { runRecommendationFlow, type FlowDeps } from '../src/content-main';
import { FR_MESSAGES } from '../src/messages';
import { MockClient } from '../src/mockClient';

function makeDeps(): FlowDeps & { client: MockClient } {
  return {
    client: new MockClient({ latencyMs: 0 }),
    memory: new ConversationMemory(),
    config: {
      enabled: true,
      mode: 'equilibre',
      models_visible: ['haiku-4-5', 'sonnet-4-6', 'opus-4-8'],
      send_prompt_text: false,
      messages: { fr: {} },
      min_extension_version: '0.1.0',
    },
    messages: FR_MESSAGES,
    now: () => new Date('2026-07-16T15:00:00.000Z'),
  };
}

function shadow(): ShadowRoot {
  return document.getElementById('sobrio-reco-host')!.shadowRoot!;
}

beforeEach(() => {
  document.body.innerHTML = '<main></main>';
});

describe('Parcours mock de bout en bout', () => {
  it('saisie → reco → « Utiliser » → événement followed=true capturé', async () => {
    const deps = makeDeps();
    const reco = await runRecommendationFlow('Quelle heure est-il à Tokyo ?', deps);
    expect(reco).not.toBeNull();

    (shadow().querySelector('[data-sobrio-follow]') as HTMLButtonElement).click();

    expect(deps.client.sentEvents).toHaveLength(1);
    const event = deps.client.sentEvents[0]!;
    expect(event).toEqual({
      reco_id: reco!.reco_id,
      followed: true,
      overridden_to: null,
      ts: '2026-07-16T15:00:00.000Z',
    });
    expect(deps.memory.toSignals().recos_followed).toBe(1);
  });

  it('saisie → reco → dérogation → événement followed=false + overridden_to', async () => {
    const deps = makeDeps();
    const reco = await runRecommendationFlow('Quelle heure est-il à Tokyo ?', deps);
    expect(reco!.recommended_model).toBe('haiku-4-5');

    const select = shadow().querySelector<HTMLSelectElement>('[data-sobrio-override]')!;
    select.value = 'opus-4-8';
    select.dispatchEvent(new Event('change'));

    const event = deps.client.sentEvents[0]!;
    expect(event.followed).toBe(false);
    expect(event.overridden_to).toBe('opus-4-8');
    // Dérogation vers plus cher : le signal derogations_up s'incrémente.
    expect(deps.memory.toSignals().derogations_up).toBe(1);
  });

  it("l'événement capturé respecte le schéma STRICT (aucun champ en plus)", async () => {
    const deps = makeDeps();
    await runRecommendationFlow('Bonjour', deps);
    (shadow().querySelector('[data-sobrio-follow]') as HTMLButtonElement).click();
    expect(Object.keys(deps.client.sentEvents[0]!).sort()).toEqual([
      'followed',
      'overridden_to',
      'reco_id',
      'ts',
    ]);
  });

  it('deux recos dans le même fil : la mémoire compte recos_shown=2', async () => {
    const deps = makeDeps();
    await runRecommendationFlow('Bonjour', deps);
    await runRecommendationFlow('Et ensuite ?', deps);
    expect(deps.memory.toSignals().recos_shown).toBe(2);
  });
});
