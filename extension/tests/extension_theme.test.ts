/**
 * Chantier A — thèmes & charte graphique : détection de thème hôte, tokens
 * charte §4 dans la source unique PANEL_CSS, application du thème au panneau.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';

import { PANEL_CSS } from '../src/panelStyle';
import { detectHostTheme, removePanel, renderPanel } from '../src/panel';
import { FR_MESSAGES } from '../src/messages';
import type { RecoV0 } from '../src/mockClient';

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

afterEach(() => {
  document.documentElement.className = '';
  document.documentElement.removeAttribute('data-theme');
  document.body.innerHTML = '';
  removePanel();
});

describe('detectHostTheme — thème de la page hôte', () => {
  it('classe/attribut de thème claude.ai', () => {
    document.documentElement.className = 'dark';
    expect(detectHostTheme()).toBe('dark');
    document.documentElement.className = 'theme-light';
    expect(detectHostTheme()).toBe('light');
    document.documentElement.className = '';
    document.documentElement.setAttribute('data-theme', 'dark');
    expect(detectHostTheme()).toBe('dark');
  });

  it('attribut data-mode (variante de thème)', () => {
    document.documentElement.setAttribute('data-mode', 'dark');
    expect(detectHostTheme()).toBe('dark');
    document.documentElement.setAttribute('data-mode', 'light');
    expect(detectHostTheme()).toBe('light');
    document.documentElement.removeAttribute('data-mode');
  });

  it('repli par LUMINANCE du fond opaque (sombre vs clair)', () => {
    document.documentElement.className = '';
    const spy = vi.spyOn(window, 'getComputedStyle');
    spy.mockReturnValue({ backgroundColor: 'rgb(20, 20, 20)' } as CSSStyleDeclaration);
    expect(detectHostTheme()).toBe('dark');
    spy.mockReturnValue({ backgroundColor: 'rgb(255, 255, 255)' } as CSSStyleDeclaration);
    expect(detectHostTheme()).toBe('light');
    // Fond transparent (alpha 0) : indéterminable → null.
    spy.mockReturnValue({ backgroundColor: 'rgba(0, 0, 0, 0)' } as CSSStyleDeclaration);
    expect(detectHostTheme()).toBeNull();
    spy.mockRestore();
  });

  it('fond transparent / indéterminable → null (prefers-color-scheme gouverne)', () => {
    document.documentElement.className = '';
    document.documentElement.removeAttribute('data-theme');
    // happy-dom : body sans fond opaque → aucune détection forcée.
    expect(detectHostTheme()).toBeNull();
  });
});

describe('PANEL_CSS — tokens de la charte §4 (source unique)', () => {
  it('accents sauge clair/sombre exacts', () => {
    expect(PANEL_CSS).toContain('#0E7C66'); // accent clair
    expect(PANEL_CSS).toContain('#4FB8A0'); // accent sombre
  });
  it('couleurs de fond/texte clair et sombre exactes', () => {
    expect(PANEL_CSS).toContain('#FFFFFF'); // fond clair
    expect(PANEL_CSS).toContain('#1A1A18'); // texte clair
    expect(PANEL_CSS).toContain('#262521'); // fond sombre
    expect(PANEL_CSS).toContain('#ECEAE4'); // texte sombre
  });
  it('conteneur : rayon 12 px, ombre charte, largeur max 320 px, isolation', () => {
    expect(PANEL_CSS).toContain('border-radius: 12px');
    expect(PANEL_CSS).toContain('0 4px 16px rgba(0, 0, 0, 0.08)');
    expect(PANEL_CSS).toContain('max-width: 320px');
    expect(PANEL_CSS).toContain('all: initial');
  });
  it('badge 22 px, jauges 4 px, animation d’apparition', () => {
    expect(PANEL_CSS).toContain('width: 22px');
    expect(PANEL_CSS).toContain('height: 4px'); // jauge
    expect(PANEL_CSS).toContain('translateY(4px)');
  });
  it('aucun emoji, aucun dégradé (charte : accent unique)', () => {
    expect(PANEL_CSS).not.toContain('gradient');
    expect(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u.test(PANEL_CSS)).toBe(false);
  });
});

describe('renderPanel — thème appliqué à l’hôte + fourchettes FR', () => {
  it('pose data-sobrio-theme depuis le thème hôte détecté', () => {
    document.body.innerHTML = '<main></main>';
    document.documentElement.className = 'dark';
    renderPanel(RECO, {
      modelsVisible: [],
      messages: FR_MESSAGES,
      callbacks: { onFollow() {}, onOverride() {} },
    });
    expect(document.getElementById('sobrio-reco-host')?.getAttribute('data-sobrio-theme')).toBe(
      'dark',
    );
  });

  it('fourchette au format charte : virgule + tiret demi-cadratin, sans espaces', () => {
    document.body.innerHTML = '<main></main>';
    renderPanel(RECO, {
      modelsVisible: [],
      messages: FR_MESSAGES,
      callbacks: { onFollow() {}, onOverride() {} },
    });
    const text = document.getElementById('sobrio-reco-host')!.shadowRoot!.textContent!;
    expect(text).toContain('0,0004–0,0006');
    expect(text).not.toContain('0.0004'); // plus de point décimal
  });

  it('jauge budget accessible : role=progressbar + aria-valuenow (parité confiance)', () => {
    document.body.innerHTML = '<main></main>';
    renderPanel(RECO, {
      modelsVisible: [],
      messages: FR_MESSAGES,
      callbacks: { onFollow() {}, onOverride() {} },
    });
    const budget = document
      .getElementById('sobrio-reco-host')!
      .shadowRoot!.querySelector('[data-sobrio-budget]')!;
    expect(budget.getAttribute('role')).toBe('progressbar');
    expect(budget.getAttribute('aria-valuenow')).toBe('42');
    expect(budget.getAttribute('aria-label')).toContain('Budget');
  });
});
