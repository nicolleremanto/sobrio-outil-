/**
 * Chantier B — bascule de modèle encadrée (assist_mode : auto / one_click /
 * guide). Résolution du mode effectif, UI optimiste + Annuler, repli silencieux
 * `guide`, télémétrie cohérente. Aucun texte ne quitte le poste (règle 1).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ConversationMemory } from '../src/conversationMemory';
import {
  DEFAULT_AUTO_THRESHOLD,
  resolveAssistMode,
  runRecommendationFlow,
  type FlowDeps,
} from '../src/content-main';
import { FR_MESSAGES } from '../src/messages';
import { removePanel } from '../src/panel';
import type { RecoClientV0, RecoV0 } from '../src/mockClient';
import type { ExtensionConfig, RecoEvent } from '../src/api';

const BASE_RECO: RecoV0 = {
  reco_id: 'mock-1',
  recommended_model: 'claude-sonnet-5',
  confidence: 0.9,
  rule: 'mock:code_context',
  impact_estimate: {
    cost_eur_min: 0.002,
    cost_eur_max: 0.004,
    energy_wh_min: 0.4,
    energy_wh_max: 1.8,
  },
  budget: null,
  suggest_new_conversation: false,
};

/** Client factice : reco fixe, capture des événements et signaux de santé. */
function fakeClient(reco: RecoV0) {
  const events: RecoEvent[] = [];
  const health: string[] = [];
  const client: RecoClientV0 = {
    recommend: async () => reco,
    sendRecoEvent: (e) => events.push(e),
    deliverRecoEvent: async () => true,
    getConfig: async () => null,
    sendHealthSignal: (s) => health.push(s),
  };
  return { client, events, health };
}

const CONFIG: ExtensionConfig = {
  enabled: true,
  mode: 'equilibre',
  models_visible: ['claude-haiku-4-5', 'claude-sonnet-5', 'claude-opus-4-8'],
  send_prompt_text: false,
  messages: { fr: {} },
  min_extension_version: '0.1.0',
};

function shadow(): ShadowRoot {
  return document.getElementById('sobrio-reco-host')!.shadowRoot!;
}

/** Promesse résoluble à la demande — pour simuler une bascule LENTE (course). */
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

/** Draine la file des microtâches (le flux atteint son `await` de bascule). */
function flush(): Promise<void> {
  return new Promise((r) => setTimeout(r, 0));
}

beforeEach(() => {
  document.body.innerHTML = '<main></main>';
  removePanel();
});

describe('resolveAssistMode — mode effectif (opt-in local ∧ politique org)', () => {
  it('opt-out local strict → guide, quelle que soit la config org', () => {
    expect(resolveAssistMode({ ...CONFIG, assist_mode: 'auto' }, false)).toBe('guide');
    expect(resolveAssistMode({ ...CONFIG, assist_mode: 'one_click' }, false)).toBe('guide');
  });

  it('opt-in local + config : la politique org décide', () => {
    expect(resolveAssistMode({ ...CONFIG, assist_mode: 'auto' }, true)).toBe('auto');
    expect(resolveAssistMode({ ...CONFIG, assist_mode: 'guide' }, true)).toBe('guide');
  });

  it('assist_mode absent → one_click (défaut, compat ascendante)', () => {
    expect(resolveAssistMode(CONFIG, true)).toBe('one_click');
    expect(resolveAssistMode(null, true)).toBe('one_click');
  });
});

describe('auto — bascule optimiste, confiance ≥ seuil', () => {
  function autoDeps(over: Partial<FlowDeps> = {}) {
    const { client, events, health } = fakeClient(BASE_RECO);
    const applyModel = vi.fn().mockResolvedValue(true);
    const readCurrentModel = vi.fn().mockReturnValue('claude-haiku-4-5');
    const deps: FlowDeps = {
      client,
      memory: new ConversationMemory(),
      config: CONFIG,
      messages: FR_MESSAGES,
      now: () => new Date('2026-07-17T10:00:00.000Z'),
      assistMode: 'auto',
      autoThreshold: DEFAULT_AUTO_THRESHOLD,
      applyModel,
      readCurrentModel,
      ...over,
    };
    return { deps, events, health, applyModel, readCurrentModel };
  }

  it('panneau en état « basculé » + Annuler ; applyModel(reco) ; followed=true', async () => {
    const { deps, events, applyModel } = autoDeps();
    await runRecommendationFlow('Refactore ce module', deps);

    // UI : état basculé (pas de bouton « Utiliser »), confirmation + Annuler.
    expect(shadow().querySelector('[data-sobrio-switched]')?.textContent).toContain(
      'Claude Sonnet 5',
    );
    expect(shadow().querySelector('[data-sobrio-cancel]')).toBeTruthy();
    expect(shadow().querySelector('[data-sobrio-follow]')).toBeNull();

    // Bascule réelle vers la reco + télémétrie followed=true.
    expect(applyModel).toHaveBeenCalledWith('claude-sonnet-5');
    expect(events).toEqual([
      { reco_id: 'mock-1', followed: true, overridden_to: null, ts: '2026-07-17T10:00:00.000Z' },
    ]);
  });

  it('Annuler restaure le modèle précédent + télémétrie followed=false/overridden_to', async () => {
    const { deps, events, applyModel } = autoDeps();
    await runRecommendationFlow('Refactore ce module', deps);
    applyModel.mockClear();

    (shadow().querySelector('[data-sobrio-cancel]') as HTMLButtonElement).click();
    await Promise.resolve();

    expect(applyModel).toHaveBeenCalledWith('claude-haiku-4-5'); // restauration
    expect(events[1]).toEqual({
      reco_id: 'mock-1',
      followed: false,
      overridden_to: 'claude-haiku-4-5',
      ts: '2026-07-17T10:00:00.000Z',
    });
  });

  it('confiance < seuil → pas de bascule auto (UI one_click)', async () => {
    const { deps, applyModel } = autoDeps();
    await runRecommendationFlow('x', {
      ...deps,
      client: fakeClient({ ...BASE_RECO, confidence: 0.5 }).client,
    });
    expect(shadow().querySelector('[data-sobrio-switched]')).toBeNull();
    expect(shadow().querySelector('[data-sobrio-follow]')).toBeTruthy();
    expect(applyModel).not.toHaveBeenCalled();
  });

  it('modèle courant illisible (null) → pas de bascule auto (on ne saurait pas Annuler)', async () => {
    const { deps, applyModel, readCurrentModel } = autoDeps();
    readCurrentModel.mockReturnValue(null);
    await runRecommendationFlow('Refactore ce module', deps);
    expect(shadow().querySelector('[data-sobrio-switched]')).toBeNull();
    expect(shadow().querySelector('[data-sobrio-follow]')).toBeTruthy();
    expect(applyModel).not.toHaveBeenCalled();
  });

  it('déjà sur le modèle recommandé → pas de bascule', async () => {
    const { deps, applyModel, readCurrentModel } = autoDeps();
    readCurrentModel.mockReturnValue('claude-sonnet-5'); // == reco
    await runRecommendationFlow('Refactore ce module', deps);
    expect(shadow().querySelector('[data-sobrio-switched]')).toBeNull();
    expect(applyModel).not.toHaveBeenCalled();
  });

  it('modèle courant illisible en auto → signal selector_broken émis', async () => {
    const { deps, health, readCurrentModel } = autoDeps();
    readCurrentModel.mockReturnValue(null);
    await runRecommendationFlow('Refactore ce module', deps);
    expect(health).toContain('selector_broken');
  });

  it('échec des sélecteurs → repli silencieux one_click + signal selector_broken, pas de followed=true', async () => {
    const { deps, events, health, applyModel } = autoDeps();
    applyModel.mockResolvedValue(false); // la bascule échoue
    await runRecommendationFlow('Refactore ce module', deps);

    expect(applyModel).toHaveBeenCalledWith('claude-sonnet-5');
    // UI revenue à one_click (l'utilisateur garde la main).
    expect(shadow().querySelector('[data-sobrio-switched]')).toBeNull();
    expect(shadow().querySelector('[data-sobrio-follow]')).toBeTruthy();
    // Signal de santé émis, aucune télémétrie de suivi mensongère.
    expect(health).toContain('selector_broken');
    expect(events).toHaveLength(0);
  });

  it('COURSE : Annuler PENDANT une bascule lente → un seul événement (followed=false), pas de followed=true tardif', async () => {
    const { client, events } = fakeClient(BASE_RECO);
    const slow = deferred<boolean>();
    // 1er appel (bascule vers la reco) = LENT ; 2e (restauration) = immédiat.
    const applyModel = vi.fn().mockReturnValueOnce(slow.promise).mockResolvedValue(true);
    const readCurrentModel = vi.fn().mockReturnValue('claude-haiku-4-5');
    const deps: FlowDeps = {
      client,
      memory: new ConversationMemory(),
      config: CONFIG,
      messages: FR_MESSAGES,
      now: () => new Date('2026-07-17T10:00:00.000Z'),
      assistMode: 'auto',
      applyModel,
      readCurrentModel,
    };

    const flow = runRecommendationFlow('Refactore ce module', deps);
    await flush(); // le panneau optimiste « basculé » est affiché, bascule en vol

    // L'utilisateur annule AVANT la fin de la bascule.
    (shadow().querySelector('[data-sobrio-cancel]') as HTMLButtonElement).click();
    expect(events).toEqual([
      {
        reco_id: 'mock-1',
        followed: false,
        overridden_to: 'claude-haiku-4-5',
        ts: '2026-07-17T10:00:00.000Z',
      },
    ]);

    slow.resolve(true); // la bascule de fond se résout APRÈS l'annulation
    await flow;

    // Aucun followed=true mensonger n'a été ajouté après l'annulation.
    expect(events.filter((e) => e.followed === true)).toHaveLength(0);
    // La restauration a bien eu lieu (sérialisée après la bascule).
    expect(applyModel).toHaveBeenLastCalledWith('claude-haiku-4-5');
  });

  it('COURSE : navigation SPA (removePanel) pendant une bascule échouée → panneau NON ressuscité', async () => {
    const { client } = fakeClient(BASE_RECO);
    const slow = deferred<boolean>();
    const applyModel = vi.fn().mockReturnValue(slow.promise);
    const readCurrentModel = vi.fn().mockReturnValue('claude-haiku-4-5');
    const deps: FlowDeps = {
      client,
      memory: new ConversationMemory(),
      config: CONFIG,
      messages: FR_MESSAGES,
      now: () => new Date('2026-07-17T10:00:00.000Z'),
      assistMode: 'auto',
      applyModel,
      readCurrentModel,
    };

    const flow = runRecommendationFlow('Refactore ce module', deps);
    await flush();
    expect(document.getElementById('sobrio-reco-host')).not.toBeNull(); // panneau optimiste

    // Changement de conversation (SPA) : le panneau est retiré…
    removePanel();
    slow.resolve(false); // …puis la bascule échoue
    await flow;

    // Le panneau NE réapparaît PAS (pas de fuite de la conversation précédente).
    expect(document.getElementById('sobrio-reco-host')).toBeNull();
  });
});

describe('guide — aucun contact page', () => {
  it('applyModel absent : « Utiliser » note l’intention SANS toucher la page + hint guide', async () => {
    const { client, events } = fakeClient(BASE_RECO);
    const applyModel = vi.fn().mockResolvedValue(true);
    const deps: FlowDeps = {
      client,
      memory: new ConversationMemory(),
      config: CONFIG,
      messages: FR_MESSAGES,
      now: () => new Date('2026-07-17T10:00:00.000Z'),
      assistMode: 'guide',
      applyModel: undefined, // guide ⇒ jamais de contact page (bootstrap le retire)
      ...{ readCurrentModel: undefined },
    };
    await runRecommendationFlow('Refactore ce module', deps);

    // Hint « à sélectionner à la main » ; pas de bascule.
    expect(shadow().querySelector('[data-sobrio-guide-hint]')).toBeTruthy();
    (shadow().querySelector('[data-sobrio-follow]') as HTMLButtonElement).click();
    expect(applyModel).not.toHaveBeenCalled(); // aucune action page
    expect(events[0]?.followed).toBe(true); // intention notée quand même
  });
});
