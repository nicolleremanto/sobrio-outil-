/**
 * Boucle 5 — panneau complet : modes, i18n, accessibilité, isolation shadow DOM.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { EN_MESSAGES, FR_MESSAGES, getMessages, modeNote, mergeMessages } from '../src/messages';
import type { RecoV0 } from '../src/mockClient';
import { removePanel, renderPanel } from '../src/panel';

const RECO: RecoV0 = {
  reco_id: 'mock-1',
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

function render(over: Partial<Parameters<typeof renderPanel>[1]> = {}) {
  renderPanel(RECO, {
    modelsVisible: ['claude-haiku-4-5', 'claude-sonnet-5', 'claude-opus-4-8'],
    messages: FR_MESSAGES,
    callbacks: { onFollow: vi.fn(), onOverride: vi.fn() },
    ...over,
  });
}

function shadow(): ShadowRoot {
  return document.getElementById('sobrio-reco-host')!.shadowRoot!;
}

beforeEach(() => {
  document.body.innerHTML = '<main></main>';
  removePanel();
});

describe('i18n — locales et surcharge', () => {
  it('getMessages(fr) complet ; getMessages(en) complété par repli FR', () => {
    expect(getMessages('fr')['why_link']).toBe('Pourquoi ?');
    expect(getMessages('en')['why_link']).toBe('Why?');
    // Clé absente en EN → repli FR.
    expect(getMessages('en')['use_model_hint']).toBe(FR_MESSAGES['use_model_hint']);
    expect(EN_MESSAGES['badge_title']).toContain('never acts');
  });

  it('surcharge par config.messages : la valeur distante gagne', () => {
    const m = getMessages('fr', { why_link: 'Explication ?', ignore: 42 });
    expect(m['why_link']).toBe('Explication ?');
    expect(mergeMessages({ panel_title: 'X' })['panel_title']).toBe('X');
  });
});

describe('modes eco/equilibre/qualite', () => {
  it('modeNote renvoie le bon ton, vide si mode absent', () => {
    expect(modeNote('eco', FR_MESSAGES)).toContain('sobriété');
    expect(modeNote('qualite', FR_MESSAGES)).toContain('qualité');
    expect(modeNote(undefined, FR_MESSAGES)).toBe('');
  });

  it('le panneau affiche la note de mode quand un mode est fourni', () => {
    render({ mode: 'eco' });
    const line = shadow().querySelector('[data-sobrio-mode="eco"]');
    expect(line?.textContent).toContain('sobriété');
  });

  it('aucune note de mode si le mode est absent', () => {
    render();
    expect(shadow().querySelector('[data-sobrio-mode]')).toBeNull();
  });
});

describe('accessibilité', () => {
  it('le panneau est nommé et non modal (focus jamais piégé)', () => {
    render();
    const panel = shadow().querySelector('[data-sobrio-panel]')!;
    expect(panel.getAttribute('role')).toBe('complementary'); // non modal
    expect(panel.getAttribute('aria-label')).toBeTruthy();
  });

  it('la jauge de confiance est un progressbar avec aria-valuenow', () => {
    render();
    const gauge = shadow().querySelector('[data-sobrio-confidence]')!;
    expect(gauge.getAttribute('role')).toBe('progressbar');
    expect(gauge.getAttribute('aria-valuenow')).toBe('80');
  });

  it('bouton de fermeture nommé ; Échap et clic ferment le panneau', () => {
    render();
    const close = shadow().querySelector('[data-sobrio-close]')!;
    expect(close.getAttribute('aria-label')).toBeTruthy();

    // Échap.
    shadow()
      .querySelector('[data-sobrio-panel]')!
      .dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    expect(document.getElementById('sobrio-reco-host')).toBeNull();

    // Clic sur la croix.
    render();
    (shadow().querySelector('[data-sobrio-close]') as HTMLButtonElement).click();
    expect(document.getElementById('sobrio-reco-host')).toBeNull();
  });

  it('les actions sont des éléments focalisables natifs (Tab naturel)', () => {
    render();
    const follow = shadow().querySelector('[data-sobrio-follow]')!;
    const override = shadow().querySelector('[data-sobrio-override]')!;
    expect(follow.tagName).toBe('BUTTON');
    expect(override.tagName).toBe('SELECT');
    // Aucun tabindex négatif qui casserait la navigation clavier.
    expect(follow.getAttribute('tabindex')).not.toBe('-1');
  });
});

describe('isolation shadow DOM — aucune fuite de style', () => {
  it('les styles vivent dans le shadow root, pas dans le document', () => {
    const headStylesBefore = document.head.querySelectorAll('style').length;
    render();
    // Le panneau n'est pas accessible en lumière (il est dans le shadow root).
    expect(document.querySelector('.panel')).toBeNull();
    // Le <style> est dans le shadow root.
    expect(shadow().querySelector('style')).toBeTruthy();
    // Aucun style ajouté au <head> du document hôte.
    expect(document.head.querySelectorAll('style').length).toBe(headStylesBefore);
  });

  it(':host { all: initial } isole des styles hérités de la page', () => {
    render();
    expect(shadow().querySelector('style')!.textContent).toContain('all: initial');
  });
});
