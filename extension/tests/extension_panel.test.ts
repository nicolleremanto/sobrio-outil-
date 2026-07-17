/**
 * Boucle 3 — rendu du badge + panneau (happy-dom) : tous les états.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ConversationMemory } from '../src/conversationMemory';
import { runRecommendationFlow, type FlowDeps } from '../src/content-main';
import { FR_MESSAGES } from '../src/messages';
import { MockClient, type RecoV0 } from '../src/mockClient';
import { renderBadge, renderPanel, removeBadge, removePanel } from '../src/panel';

const BASE_RECO: RecoV0 = {
  reco_id: 'mock-000042',
  recommended_model: 'claude-haiku-4-5',
  confidence: 0.8,
  rule: 'mock:short_simple',
  impact_estimate: {
    cost_eur_min: 0.0004,
    cost_eur_max: 0.0006,
    energy_wh_min: 0.05,
    energy_wh_max: 0.21,
  },
  budget: { team_label: 'Équipe démo', pct_used: 42 },
  suggest_new_conversation: false,
};

function panelRoot(): ShadowRoot {
  const host = document.getElementById('sobrio-reco-host');
  expect(host?.shadowRoot).toBeTruthy();
  return host!.shadowRoot!;
}

function render(
  reco: Partial<RecoV0> = {},
  callbacks = { onFollow: vi.fn(), onOverride: vi.fn() },
) {
  renderPanel(
    { ...BASE_RECO, ...reco },
    {
      modelsVisible: ['claude-haiku-4-5', 'claude-sonnet-5', 'claude-opus-4-8'],
      messages: FR_MESSAGES,
      callbacks,
    },
  );
  return callbacks;
}

beforeEach(() => {
  document.body.innerHTML = '<main></main>';
  removePanel();
  removeBadge();
});

describe('renderPanel — reco simple', () => {
  it('affiche le modèle recommandé, la jauge de confiance et les fourchettes', () => {
    render();
    const root = panelRoot();
    expect(root.querySelector('[data-sobrio-model="claude-haiku-4-5"]')?.textContent).toContain(
      'Claude Haiku 4.5',
    );
    expect(root.querySelector('[data-sobrio-confidence="0.8"]')).toBeTruthy();
    const text = root.querySelector('[data-sobrio-panel]')!.textContent!;
    expect(text).toContain('0.0004 – 0.0006');
    expect(text).toContain('€ / appel');
    expect(text).toContain('Wh');
    expect(text).toContain('périmètre'); // règle 5 : fourchette + périmètre
  });

  it('affiche la jauge budget quand elle est fournie', () => {
    render();
    expect(panelRoot().querySelector('[data-sobrio-budget]')).toBeTruthy();
    expect(panelRoot().querySelector('[data-sobrio-panel]')!.textContent).toContain('Équipe démo');
  });

  it('« Pourquoi ? » révèle la règle en langage clair', () => {
    render();
    const root = panelRoot();
    const why = root.querySelector<HTMLElement>('[data-sobrio-why]')!;
    expect(why.classList.contains('visible')).toBe(false);
    (root.querySelector('button.why') as HTMLButtonElement).click();
    expect(why.classList.contains('visible')).toBe(true);
    expect(why.textContent).toContain('courte et simple');
  });
});

describe('renderPanel — dérogation et suivi', () => {
  it('« Utiliser [modèle] » déclenche onFollow puis un accusé (aucune action page)', () => {
    const callbacks = render();
    const root = panelRoot();
    (root.querySelector('[data-sobrio-follow]') as HTMLButtonElement).click();
    expect(callbacks.onFollow).toHaveBeenCalledTimes(1);
    expect(root.querySelector('[data-sobrio-ack]')).toBeTruthy();
  });

  it('la dérogation liste models_visible (sans le recommandé) et remonte le choix', () => {
    const callbacks = render();
    const select = panelRoot().querySelector<HTMLSelectElement>('[data-sobrio-override]')!;
    const values = [...select.options].map((option) => option.value).filter(Boolean);
    expect(values).toEqual(['claude-sonnet-5', 'claude-opus-4-8']);
    select.value = 'claude-opus-4-8';
    select.dispatchEvent(new Event('change'));
    expect(callbacks.onOverride).toHaveBeenCalledWith('claude-opus-4-8');
  });
});

describe('renderPanel — états particuliers', () => {
  it('budget absent : aucune jauge budget', () => {
    render({ budget: null });
    expect(panelRoot().querySelector('[data-sobrio-budget]')).toBeNull();
  });

  it('suggestion nouvelle conversation : bandeau discret présent', () => {
    render({ suggest_new_conversation: true });
    expect(panelRoot().querySelector('[data-sobrio-banner]')?.textContent).toContain(
      'Conversation longue',
    );
  });

  it('confiance basse : la note « signal ambigu » est affichée (ton humble)', () => {
    render({ confidence: 0.55 });
    expect(panelRoot().querySelector('[data-sobrio-ambiguous]')).toBeTruthy();
  });

  it('badge : rendu une seule fois, sans polluer la page hôte', () => {
    renderBadge(FR_MESSAGES);
    renderBadge(FR_MESSAGES);
    expect(document.querySelectorAll('#sobrio-badge-host')).toHaveLength(1);
    // La page hôte ne reçoit que nos hôtes à nous — rien d'autre.
    expect(document.querySelector('main')!.children.length).toBe(1);
  });

  it('badge ancré : positionné sur le bord droit de la barre de saisie, centré', () => {
    const input = document.createElement('div');
    input.setAttribute('contenteditable', 'true');
    document.querySelector('main')!.appendChild(input);
    vi.spyOn(input, 'getBoundingClientRect').mockReturnValue({
      top: 500,
      height: 52,
      right: 800,
      width: 600,
      left: 200,
      bottom: 552,
    } as DOMRect);

    renderBadge(FR_MESSAGES, input);
    const badge = document
      .getElementById('sobrio-badge-host')!
      .shadowRoot!.querySelector<HTMLElement>('.badge')!;
    // top = 500 + (52 − 26)/2 = 513 ; left = 800 − 26 − 10 = 764.
    expect(badge.style.top).toBe('513px');
    expect(badge.style.left).toBe('764px');
  });

  it('badge sans ancre mesurable : repli sur le coin bas-droit', () => {
    renderBadge(FR_MESSAGES, null);
    const badge = document
      .getElementById('sobrio-badge-host')!
      .shadowRoot!.querySelector<HTMLElement>('.badge')!;
    expect(badge.style.right).toBe('16px');
    expect(badge.style.bottom).toBe('48px');
  });
});

describe('runRecommendationFlow — silence et kill-switch', () => {
  function deps(overrides: Partial<FlowDeps> = {}): FlowDeps {
    return {
      client: new MockClient({ latencyMs: 0 }),
      memory: new ConversationMemory(),
      config: {
        enabled: true,
        mode: 'equilibre',
        models_visible: ['claude-haiku-4-5', 'claude-sonnet-5', 'claude-opus-4-8'],
        send_prompt_text: false,
        messages: { fr: {} },
        min_extension_version: '0.1.0',
      },
      messages: FR_MESSAGES,
      ...overrides,
    };
  }

  it('API muette : RIEN ne s’affiche (règle 3)', async () => {
    const result = await runRecommendationFlow('Bonjour', {
      ...deps(),
      client: new MockClient({ latencyMs: 0, failure: 'mute' }),
    });
    expect(result).toBeNull();
    expect(document.getElementById('sobrio-reco-host')).toBeNull();
  });

  it('kill-switch (enabled=false) : extension inerte', async () => {
    const flowDeps = deps();
    const result = await runRecommendationFlow('Bonjour', {
      ...flowDeps,
      config: { ...flowDeps.config!, enabled: false },
    });
    expect(result).toBeNull();
    expect(document.getElementById('sobrio-reco-host')).toBeNull();
  });

  it('texte vide : le panneau est retiré, aucun appel', async () => {
    render(); // panneau présent
    const result = await runRecommendationFlow('   ', deps());
    expect(result).toBeNull();
    expect(document.getElementById('sobrio-reco-host')).toBeNull();
  });

  it('flux nominal : la reco est affichée et notée dans la mémoire', async () => {
    const memory = new ConversationMemory();
    const result = await runRecommendationFlow('Quelle heure est-il ?', deps({ memory }));
    expect(result?.recommended_model).toBe('claude-haiku-4-5');
    expect(document.getElementById('sobrio-reco-host')).toBeTruthy();
    expect(memory.toSignals().recos_shown).toBe(1);
  });
});
