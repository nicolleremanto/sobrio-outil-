/**
 * Chantier B — bascule de modèle encadrée (assist_mode : auto / one_click /
 * guide). Résolution du mode effectif, UI optimiste, ACCEPTATION DIFFÉRÉE (un
 * seul événement net par reco), Annuler, garde de conversation (anti-fuite SPA),
 * repli silencieux `guide`. Aucun texte ne quitte le poste (règle 1).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ConversationMemory } from '../src/conversationMemory';
import {
  DEFAULT_AUTO_THRESHOLD,
  flushPendingAutoAccept,
  resolveAssistMode,
  runRecommendationFlow,
  type FlowDeps,
} from '../src/content-main';
import { FR_MESSAGES } from '../src/messages';
import { removeBadge, removePanel, renderBadge } from '../src/panel';
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
function q(sel: string): Element | null {
  const host = document.getElementById('sobrio-reco-host');
  return host ? host.shadowRoot!.querySelector(sel) : null;
}
function followedTrue(events: RecoEvent[]) {
  return events.filter((e) => e.followed === true);
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
  flushPendingAutoAccept(); // pas de fuite d'acceptation en attente entre tests
  removePanel();
  removeBadge();
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

describe('auto — UI optimiste + acceptation différée (un seul événement net)', () => {
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
      isCurrent: () => true,
      ...over,
    };
    return { deps, events, health, applyModel, readCurrentModel };
  }

  it('bascule immédiate + panneau « basculé » + Annuler ; issue EN ATTENTE (aucun événement)', async () => {
    const { deps, events, applyModel } = autoDeps();
    await runRecommendationFlow('Refactore ce module', deps);

    expect(q('[data-sobrio-switched]')?.textContent).toContain('Claude Sonnet 5');
    expect(q('[data-sobrio-cancel]')).toBeTruthy();
    expect(q('[data-sobrio-follow]')).toBeNull();
    expect(applyModel).toHaveBeenCalledWith('claude-sonnet-5');
    // Rien n'est émis tant que l'utilisateur peut annuler.
    expect(events).toEqual([]);
  });

  it('acceptation committée à la fermeture (écarter sans annuler) = followed:true, UNE fois', async () => {
    const { deps, events } = autoDeps();
    await runRecommendationFlow('Refactore ce module', deps);
    (shadow().querySelector('[data-sobrio-close]') as HTMLButtonElement).click();
    expect(events).toEqual([
      { reco_id: 'mock-1', followed: true, overridden_to: null, ts: '2026-07-17T10:00:00.000Z' },
    ]);
    flushPendingAutoAccept(); // idempotent : pas de double-comptage
    expect(events).toHaveLength(1);
    expect(deps.memory.toSignals().recos_followed).toBe(1);
  });

  it('acceptation committée par le flux suivant (flushPendingAutoAccept)', async () => {
    const { deps, events } = autoDeps();
    await runRecommendationFlow('Refactore ce module', deps);
    expect(events).toEqual([]); // en attente
    flushPendingAutoAccept();
    expect(events).toEqual([
      { reco_id: 'mock-1', followed: true, overridden_to: null, ts: '2026-07-17T10:00:00.000Z' },
    ]);
    flushPendingAutoAccept();
    expect(events).toHaveLength(1);
  });

  it('Annuler après succès = UN SEUL événement net (followed:false), JAMAIS followed:true', async () => {
    const { deps, events, applyModel } = autoDeps();
    await runRecommendationFlow('Refactore ce module', deps);
    applyModel.mockClear();

    (shadow().querySelector('[data-sobrio-cancel]') as HTMLButtonElement).click();
    await flush();

    expect(events).toEqual([
      {
        reco_id: 'mock-1',
        followed: false,
        overridden_to: 'claude-haiku-4-5',
        ts: '2026-07-17T10:00:00.000Z',
      },
    ]);
    expect(applyModel).toHaveBeenCalledWith('claude-haiku-4-5'); // restauration
    // Aucune acceptation ne peut plus être committée (issue déjà tranchée).
    (shadow().querySelector('[data-sobrio-close]') as HTMLButtonElement)?.click();
    flushPendingAutoAccept();
    expect(followedTrue(events)).toHaveLength(0);
    expect(events).toHaveLength(1);
    expect(deps.memory.toSignals().recos_followed).toBe(0); // pas gonflé
  });

  it('COURSE : Annuler PENDANT une bascule lente → followed:false unique, pas de followed:true tardif', async () => {
    const { client, events } = fakeClient(BASE_RECO);
    const slow = deferred<boolean>();
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
      isCurrent: () => true,
    };

    const flowP = runRecommendationFlow('Refactore ce module', deps);
    await flush(); // panneau « basculé » affiché, bascule en vol

    (shadow().querySelector('[data-sobrio-cancel]') as HTMLButtonElement).click();
    expect(events).toEqual([
      {
        reco_id: 'mock-1',
        followed: false,
        overridden_to: 'claude-haiku-4-5',
        ts: '2026-07-17T10:00:00.000Z',
      },
    ]);

    slow.resolve(true); // la bascule se résout APRÈS l'annulation
    await flowP;
    expect(followedTrue(events)).toHaveLength(0);
    expect(applyModel).toHaveBeenLastCalledWith('claude-haiku-4-5'); // restauration sérialisée
  });

  it('confiance < seuil → pas de bascule (UI one_click)', async () => {
    const { deps, applyModel } = autoDeps();
    await runRecommendationFlow('x', {
      ...deps,
      client: fakeClient({ ...BASE_RECO, confidence: 0.5 }).client,
    });
    expect(q('[data-sobrio-switched]')).toBeNull();
    expect(q('[data-sobrio-follow]')).toBeTruthy();
    expect(applyModel).not.toHaveBeenCalled();
  });

  it('modèle courant illisible (null) → pas de bascule + signal selector_broken', async () => {
    const { deps, applyModel, health, readCurrentModel } = autoDeps();
    readCurrentModel.mockReturnValue(null);
    await runRecommendationFlow('Refactore ce module', deps);
    expect(q('[data-sobrio-switched]')).toBeNull();
    expect(q('[data-sobrio-follow]')).toBeTruthy();
    expect(applyModel).not.toHaveBeenCalled();
    expect(health).toContain('selector_broken');
  });

  it('déjà sur le modèle recommandé → accusé « Déjà sur … », pas de bascule ni d’événement', async () => {
    const { deps, applyModel, events, readCurrentModel } = autoDeps();
    readCurrentModel.mockReturnValue('claude-sonnet-5'); // == reco
    await runRecommendationFlow('Refactore ce module', deps);
    expect(q('[data-sobrio-already]')?.textContent).toContain('Claude Sonnet 5');
    expect(q('[data-sobrio-follow]')).toBeNull();
    expect(applyModel).not.toHaveBeenCalled();
    expect(events).toEqual([]);
  });

  it('échec des sélecteurs → repli one_click + selector_broken, aucun événement', async () => {
    const { deps, events, health, applyModel } = autoDeps();
    applyModel.mockResolvedValue(false);
    await runRecommendationFlow('Refactore ce module', deps);
    expect(applyModel).toHaveBeenCalledWith('claude-sonnet-5');
    expect(q('[data-sobrio-switched]')).toBeNull();
    expect(q('[data-sobrio-follow]')).toBeTruthy();
    expect(health).toContain('selector_broken');
    expect(events).toHaveLength(0);
  });

  it('GARDE SPA : conversation changée pendant l’appel réseau → rien affiché, aucune bascule', async () => {
    const { deps, applyModel, events } = autoDeps({ isCurrent: () => false });
    const reco = await runRecommendationFlow('Refactore ce module', deps);
    expect(reco).toBeNull();
    expect(document.getElementById('sobrio-reco-host')).toBeNull();
    expect(applyModel).not.toHaveBeenCalled();
    expect(events).toEqual([]);
  });

  it('CONCURRENCE : F1 (bascule lente) supplanté par F2 → acceptation de F1 committée EXACTEMENT une fois', async () => {
    const events: RecoEvent[] = [];
    const mkClient = (reco: RecoV0): RecoClientV0 => ({
      recommend: async () => reco,
      sendRecoEvent: (e) => events.push(e),
      deliverRecoEvent: async () => true,
      getConfig: async () => null,
      sendHealthSignal: () => {},
    });
    const now = () => new Date('2026-07-17T10:00:00.000Z');
    const slow = deferred<boolean>();
    const deps1: FlowDeps = {
      client: mkClient({ ...BASE_RECO, reco_id: 'reco-1' }),
      memory: new ConversationMemory(),
      config: CONFIG,
      messages: FR_MESSAGES,
      now,
      assistMode: 'auto',
      applyModel: vi.fn().mockReturnValue(slow.promise),
      readCurrentModel: () => 'claude-haiku-4-5',
      isCurrent: () => true,
    };
    const deps2: FlowDeps = {
      client: mkClient({ ...BASE_RECO, reco_id: 'reco-2' }),
      memory: new ConversationMemory(),
      config: CONFIG,
      messages: FR_MESSAGES,
      now,
      assistMode: 'auto',
      applyModel: vi.fn().mockResolvedValue(true),
      readCurrentModel: () => 'claude-haiku-4-5',
      isCurrent: () => true,
    };

    const f1 = runRecommendationFlow('Refactore A', deps1);
    await flush(); // F1 en vol (bascule lente)
    await runRecommendationFlow('Refactore B', deps2); // F2 supplante F1
    expect(events).toEqual([]); // rien encore committé (F2 en attente)

    slow.resolve(true);
    await f1; // F1 résout après avoir été supplanté → committe SON acceptation
    expect(events).toEqual([
      { reco_id: 'reco-1', followed: true, overridden_to: null, ts: '2026-07-17T10:00:00.000Z' },
    ]);
    expect(deps1.memory.toSignals().recos_followed).toBe(1);

    flushPendingAutoAccept(); // committe F2 (le pending le plus récent)
    // Chaque reco committée EXACTEMENT une fois (aucune orpheline, aucun double).
    expect(events.filter((e) => e.reco_id === 'reco-1')).toHaveLength(1);
    expect(events.filter((e) => e.reco_id === 'reco-2')).toHaveLength(1);
  });

  it('COURSE : nav SPA (removePanel) pendant une bascule échouée → panneau NON ressuscité', async () => {
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
      isCurrent: () => true,
    };

    const flowP = runRecommendationFlow('Refactore ce module', deps);
    await flush();
    expect(document.getElementById('sobrio-reco-host')).not.toBeNull();

    removePanel(); // nav SPA
    slow.resolve(false); // la bascule échoue
    await flowP;
    expect(document.getElementById('sobrio-reco-host')).toBeNull();
  });
});

describe('guide — aucun contact page', () => {
  it('bouton à libellé NON-actif + hint de sélection ; « suivre » note l’intention sans agir', async () => {
    const { client, events } = fakeClient(BASE_RECO);
    const deps: FlowDeps = {
      client,
      memory: new ConversationMemory(),
      config: CONFIG,
      messages: FR_MESSAGES,
      now: () => new Date('2026-07-17T10:00:00.000Z'),
      assistMode: 'guide',
      applyModel: undefined, // guide ⇒ aucun contact page (bootstrap le retire)
      readCurrentModel: undefined,
      isCurrent: () => true,
    };
    await runRecommendationFlow('Refactore ce module', deps);

    // Libellé d'intention (pas « Utiliser »), hint de sélection manuelle.
    expect(q('[data-sobrio-guide-hint]')).toBeTruthy();
    expect(q('[data-sobrio-follow]')?.textContent).toContain('J’utiliserai');
    expect(q('[data-sobrio-switched]')).toBeNull();

    // « Suivre » note l'intention (followed:true) mais ne touche jamais la page.
    (shadow().querySelector('[data-sobrio-follow]') as HTMLButtonElement).click();
    expect(events[0]?.followed).toBe(true);
  });
});

describe('badge — honnêteté du libellé selon le mode (règle 7)', () => {
  it('en auto, le titre n’affirme PAS « n’agit jamais » ; le clic committe l’acceptation', () => {
    const onDismiss = vi.fn();
    renderBadge(FR_MESSAGES, document.querySelector('main'), {
      assistMode: 'auto',
      onDismiss,
    });
    const badge = document
      .getElementById('sobrio-badge-host')!
      .shadowRoot!.querySelector('.badge') as HTMLButtonElement;
    expect(badge.title).not.toContain('n’agit jamais');
    expect(badge.title.toLowerCase()).toContain('automatiquement');
    badge.click();
    expect(onDismiss).toHaveBeenCalled();
  });

  it('one_click : « applique … à votre clic » (agit au clic) ; guide : « n’agit jamais » (aucun contact)', () => {
    renderBadge(FR_MESSAGES, document.querySelector('main'), { assistMode: 'one_click' });
    const oneClick = document
      .getElementById('sobrio-badge-host')!
      .shadowRoot!.querySelector('.badge') as HTMLButtonElement;
    expect(oneClick.title).toContain('à votre clic');
    expect(oneClick.title).not.toContain('n’agit jamais');

    removeBadge();
    renderBadge(FR_MESSAGES, document.querySelector('main'), { assistMode: 'guide' });
    const guide = document
      .getElementById('sobrio-badge-host')!
      .shadowRoot!.querySelector('.badge') as HTMLButtonElement;
    expect(guide.title).toContain('n’agit jamais');
  });
});
