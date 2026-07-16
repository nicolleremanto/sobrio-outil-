/**
 * Boucle 5 — robustesse : résolution sur 3 variantes HTML (dont une cassée),
 * heuristique de repli, détecteur de casse, throttle de l'observation DOM.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { createThrottle } from '../src/client';
import {
  collectPageView,
  fallbackLargestEditable,
  noteInputResolution,
  resetSelectorHealth,
  resolveInputArea,
  selectorsBroken,
  SELECTOR_BROKEN_THRESHOLD,
} from '../src/selectors';

function loadVariant(name: string): void {
  // process.cwd() = extension/ (vitest y tourne, localement comme en CI).
  const path = join(process.cwd(), 'dev', 'testpage', name);
  const html = readFileSync(path, 'utf-8');
  // On injecte le <body> de la variante (les scripts de démo ne tournent pas).
  document.body.innerHTML = /<body>([\s\S]*)<\/body>/.exec(html)?.[1] ?? '';
}

beforeEach(() => {
  resetSelectorHealth();
});
afterEach(() => {
  document.body.innerHTML = '';
});

describe('Variante A (page d’entraînement) — sélecteurs ordonnés', () => {
  it('résout la zone ProseMirror et lit bulles + modèle + fil', () => {
    loadVariant('index.html');
    const input = resolveInputArea();
    expect(input?.classList.contains('ProseMirror')).toBe(true);

    const view = collectPageView(document, '/');
    expect(view.threadId).toBe('t-001');
    expect(view.bubbles.length).toBeGreaterThanOrEqual(2);
    expect(view.modelLabel).toContain('Opus');
  });
});

describe('Variante B (markup alternatif) — heuristique de repli', () => {
  it('résout le textarea via « plus grand éditable visible »', () => {
    loadVariant('variant-b.html');
    const input = resolveInputArea();
    expect(input).toBeInstanceOf(HTMLTextAreaElement);
  });

  it('lit les bulles data-testid et l’étiquette de modèle alternative', () => {
    loadVariant('variant-b.html');
    const view = collectPageView(document, '/');
    expect(view.bubbles).toHaveLength(2);
    expect(view.bubbles[0]?.role).toBe('user');
    expect(view.modelLabel).toContain('Sonnet');
  });

  it('le repli choisit le PLUS GRAND éditable visible', () => {
    document.body.innerHTML = `
      <div contenteditable="true" id="petit"></div>
      <textarea id="grand"></textarea>
      <textarea id="cache" hidden></textarea>`;
    const small = document.getElementById('petit')!;
    const big = document.getElementById('grand')!;
    vi.spyOn(small, 'getBoundingClientRect').mockReturnValue({
      width: 50,
      height: 20,
    } as DOMRect);
    vi.spyOn(big, 'getBoundingClientRect').mockReturnValue({
      width: 600,
      height: 80,
    } as DOMRect);
    expect(fallbackLargestEditable()?.id).toBe('grand');
  });

  it('ignore les éditables cachés (hidden, aria-hidden, display:none)', () => {
    document.body.innerHTML = `
      <textarea hidden></textarea>
      <div contenteditable="true" aria-hidden="true"></div>
      <textarea style="display:none"></textarea>`;
    expect(fallbackLargestEditable()).toBeNull();
  });
});

describe('Variante cassée — dégradation silencieuse + détecteur de casse', () => {
  it('aucune zone résolue, aucun throw', () => {
    loadVariant('variant-broken.html');
    expect(resolveInputArea()).toBeNull();
    expect(collectPageView(document, '/').bubbles).toEqual([]);
  });

  it(`déclare la casse après ${SELECTOR_BROKEN_THRESHOLD} échecs consécutifs — une seule fois`, () => {
    let triggered = 0;
    for (let i = 0; i < SELECTOR_BROKEN_THRESHOLD * 2; i += 1) {
      if (noteInputResolution(false)) triggered += 1;
    }
    expect(selectorsBroken()).toBe(true);
    expect(triggered).toBe(1); // le signal ne part qu'UNE fois
  });

  it('une résolution réussie remet le compteur à zéro', () => {
    for (let i = 0; i < SELECTOR_BROKEN_THRESHOLD - 1; i += 1) noteInputResolution(false);
    noteInputResolution(true); // succès : reset
    for (let i = 0; i < SELECTOR_BROKEN_THRESHOLD - 1; i += 1) {
      expect(noteInputResolution(false)).toBe(false);
    }
    expect(selectorsBroken()).toBe(false);
  });
});

describe('createThrottle — garde-fou perf de l’observation DOM', () => {
  it('au plus un appel par fenêtre, même sous rafale de mutations', () => {
    vi.useFakeTimers();
    const spy = vi.fn();
    const throttled = createThrottle(spy, 300);
    for (let i = 0; i < 50; i += 1) throttled(); // rafale
    vi.advanceTimersByTime(300);
    expect(spy).toHaveBeenCalledTimes(1);
    throttled();
    vi.advanceTimersByTime(300);
    expect(spy).toHaveBeenCalledTimes(2);
    vi.useRealTimers();
  });
});
