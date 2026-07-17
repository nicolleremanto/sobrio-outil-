/**
 * Chantier A — thèmes & charte graphique : détection de thème hôte, tokens
 * charte §4 dans la source unique PANEL_CSS, application du thème au panneau.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { afterEach, describe, expect, it, vi } from 'vitest';

import { PANEL_CSS } from '../src/panelStyle';
import { detectHostTheme, formatRange, removePanel, renderPanel } from '../src/panel';
import { formatRange as harnessFormatRange } from '../scripts/lib/format.mjs';
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
  it('respecte prefers-reduced-motion (WCAG 2.3.3)', () => {
    expect(PANEL_CSS).toContain('prefers-reduced-motion: reduce');
    // Assertions TOLÉRANTES au reformatage (espaces/sauts de ligne) : on
    // vérifie le sens (animation/transition neutralisées), pas la mise en page.
    const block = PANEL_CSS.slice(PANEL_CSS.indexOf('prefers-reduced-motion'));
    expect(/\.panel\s*\{[^}]*animation:\s*none/.test(block)).toBe(true);
    expect(/\.badge\s*\{[^}]*transition:\s*none/.test(block)).toBe(true);
  });
});

describe('formatRange — décimales charte §4 (source du rendu ET du harnais)', () => {
  it('4 déc. si max<0,01 · 3 si <1 · 1 sinon — virgule + tiret demi-cadratin', () => {
    expect(formatRange(0.0004, 0.0006)).toBe('0,0004–0,0006');
    expect(formatRange(0.002, 0.004)).toBe('0,0020–0,0040');
    expect(formatRange(0.05, 0.21)).toBe('0,050–0,210');
    expect(formatRange(0.4, 1.8)).toBe('0,4–1,8');
    expect(formatRange(0.8, 3.2)).toBe('0,8–3,2');
  });

  it('parité STRICTE panel.ts ↔ harnais de capture (anti-dérive des seuils)', () => {
    // Le harnais (scripts/lib/format.mjs) et panel.ts DOIVENT coïncider : toute
    // dérive des seuils de décimales fait échouer la CI (minor product+qa r3).
    const bounds: [number, number][] = [
      [0.0004, 0.0006],
      [0.002, 0.004],
      [0.05, 0.21],
      [0.4, 1.8],
      [0.8, 3.2],
      [0.006, 0.012],
      [0, 0.009],
      [0.5, 0.99],
      [1, 250],
      [0.0099, 0.01],
    ];
    for (const [a, b] of bounds) {
      expect(harnessFormatRange(a, b)).toBe(formatRange(a, b));
    }
  });
});

describe('capture-visual — extraction PANEL_CSS (garde anti-dérive du harnais)', () => {
  it('la regex du script de capture extrait une CSS non vide avec les tokens charte', () => {
    // Reproduit exactement l'extraction de scripts/capture-visual.mjs : si elle
    // casse (renommage de l'export, backtick), le harnais visuel se viderait.
    const src = readFileSync(join(process.cwd(), 'src', 'panelStyle.ts'), 'utf-8');
    const match = /export const PANEL_CSS = `([\s\S]*?)`;/.exec(src);
    expect(match).not.toBeNull();
    const css = match?.[1] ?? '';
    expect(css.length).toBeGreaterThan(500);
    expect(css).toContain('#0E7C66'); // accent clair (token charte présent)
    expect(css).toContain('.badge'); // le badge est bien capturable
  });

  it('garde de dérive SYMÉTRIQUE : les classes clés existent dans panel.ts ET le harnais', () => {
    // panelMarkup (capture-visual.mjs) est un miroir manuel de renderPanel ;
    // seule PANEL_CSS est mono-source. Garde bilatérale : un renommage de classe
    // d'un côté OU de l'autre désynchroniserait silencieusement la capture.
    const panelSrc = readFileSync(join(process.cwd(), 'src', 'panel.ts'), 'utf-8');
    const harnessSrc = readFileSync(join(process.cwd(), 'scripts', 'capture-visual.mjs'), 'utf-8');
    // Une classe « apparaît » via un littéral 'x' (createElement + className) ou
    // un attribut class="x" (template du harnais).
    const appears = (src: string, cls: string) =>
      src.includes(`'${cls}'`) || new RegExp(`class="${cls}(?=[ "])`).test(src);
    // Ensemble élargi des classes rendues (celles apparaissant comme tokens
    // autonomes des deux côtés ; 'why-text' est composée, gardée via 'note').
    const CLASSES = [
      'panel',
      'badge',
      'gauge',
      'gauge-label',
      'model',
      'banner',
      'why',
      'actions',
      'header',
      'title',
      'close',
      'mode-note',
      'range',
      'note',
      'ack',
      'primary',
      'hint',
    ];
    for (const cls of CLASSES) {
      expect(appears(panelSrc, cls)).toBe(true);
      expect(appears(harnessSrc, cls)).toBe(true);
    }
  });
});

describe('ton humble — ambiguous_note ne nomme aucun modèle en dur (anti-régression)', () => {
  it('le message de signal ambigu ne cite ni haiku ni sonnet ni opus ni fable', () => {
    // Verrouille le correctif de ton (Chantier C→A) : aucun nom de modèle en dur.
    expect(FR_MESSAGES['ambiguous_note']).not.toMatch(/haiku|sonnet|opus|fable/i);
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

  it('budget en dépassement : barre bornée à 100 %, libellé montre le réel (sincérité)', () => {
    document.body.innerHTML = '<main></main>';
    const over: RecoV0 = { ...RECO, budget: { team_label: 'Équipe démo', pct_used: 118 } };
    renderPanel(over, {
      modelsVisible: [],
      messages: FR_MESSAGES,
      callbacks: { onFollow() {}, onOverride() {} },
    });
    const shadow = document.getElementById('sobrio-reco-host')!.shadowRoot!;
    const budget = shadow.querySelector('[data-sobrio-budget]')!;
    // Barre + aria-valuenow bornées à 100 (ne peut pas déborder visuellement)…
    expect(budget.getAttribute('aria-valuenow')).toBe('100');
    expect((budget.querySelector('div') as HTMLElement).style.width).toBe('100%');
    // …mais le dépassement RESTE visible : attribut, libellé ET aria-valuetext
    // à 118 (parité a11y ↔ visuel : le lecteur d'écran entend la valeur réelle).
    expect(budget.getAttribute('data-sobrio-budget-over')).toBe('118');
    expect(budget.getAttribute('aria-valuetext')).toBe('118 % utilisé');
    expect(shadow.textContent).toContain('118');
    expect(shadow.textContent).not.toContain('100 % utilisé');
  });
});
