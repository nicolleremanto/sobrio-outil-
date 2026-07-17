/**
 * Robustesse : résolution des sélecteurs sur les 4 fixtures DOM headless
 * (nominal, alt1, alt2, broken), heuristique de repli, détecteur de casse,
 * throttle de l'observation DOM. Remplace l'ancienne page d'entraînement.
 */
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
import { loadFixture } from '../test/loadFixture';

beforeEach(() => {
  resetSelectorHealth();
});
afterEach(() => {
  document.body.innerHTML = '';
});

describe('Fixture nominale — sélecteurs ordonnés', () => {
  it('résout la zone ProseMirror et lit bulles + modèle + fil', () => {
    const path = loadFixture('nominal');
    const input = resolveInputArea();
    expect(input?.classList.contains('ProseMirror')).toBe(true);

    const view = collectPageView(document, path);
    expect(view.threadId).toBe('conv-nominal-001');
    expect(view.bubbles.length).toBeGreaterThanOrEqual(4);
    expect(view.modelLabel).toContain('Opus');
  });
});

describe('Fixture alt1 — markup alternatif (contenteditable sans ProseMirror)', () => {
  it('résout la zone de saisie et lit les bulles data-testid', () => {
    const path = loadFixture('alt1');
    const input = resolveInputArea();
    expect(input?.getAttribute('contenteditable')).toBe('true');

    const view = collectPageView(document, path);
    expect(view.bubbles).toHaveLength(2);
    expect(view.bubbles[0]?.role).toBe('user');
    expect(view.modelLabel).toContain('Sonnet');
    expect(view.threadId).toBe('conv-alt1-777');
  });
});

describe('Fixture alt2 — variante minimale (textarea, heuristique de repli)', () => {
  it('résout le textarea via « plus grand éditable visible »', () => {
    loadFixture('alt2');
    expect(resolveInputArea()).toBeInstanceOf(HTMLTextAreaElement);
  });

  it('étiquette de modèle lue via heuristique de libellé (bouton générique)', () => {
    const path = loadFixture('alt2');
    const view = collectPageView(document, path);
    expect(view.modelLabel).toContain('Haiku');
  });
});

describe('fallbackLargestEditable — choix et visibilité', () => {
  it('choisit le PLUS GRAND éditable visible, ignore les cachés', () => {
    document.body.innerHTML = `
      <div contenteditable="true" id="petit"></div>
      <textarea id="grand"></textarea>
      <textarea id="cache" hidden></textarea>`;
    const small = document.getElementById('petit')!;
    const big = document.getElementById('grand')!;
    vi.spyOn(small, 'getBoundingClientRect').mockReturnValue({ width: 50, height: 20 } as DOMRect);
    vi.spyOn(big, 'getBoundingClientRect').mockReturnValue({ width: 600, height: 80 } as DOMRect);
    expect(fallbackLargestEditable()?.id).toBe('grand');
  });

  it('ignore hidden, aria-hidden, display:none', () => {
    document.body.innerHTML = `
      <textarea hidden></textarea>
      <div contenteditable="true" aria-hidden="true"></div>
      <textarea style="display:none"></textarea>`;
    expect(fallbackLargestEditable()).toBeNull();
  });
});

describe('Fixture cassée — dégradation silencieuse + détecteur de casse', () => {
  it('aucune zone résolue, aucune bulle, aucun throw', () => {
    loadFixture('broken');
    expect(resolveInputArea()).toBeNull();
    expect(collectPageView(document, '/settings/profile').bubbles).toEqual([]);
  });

  it(`déclare la casse après ${SELECTOR_BROKEN_THRESHOLD} échecs consécutifs — une seule fois`, () => {
    let triggered = 0;
    for (let i = 0; i < SELECTOR_BROKEN_THRESHOLD * 2; i += 1) {
      if (noteInputResolution(false)) triggered += 1;
    }
    expect(selectorsBroken()).toBe(true);
    expect(triggered).toBe(1);
  });

  it('une résolution réussie remet le compteur à zéro', () => {
    for (let i = 0; i < SELECTOR_BROKEN_THRESHOLD - 1; i += 1) noteInputResolution(false);
    noteInputResolution(true);
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
    for (let i = 0; i < 50; i += 1) throttled();
    vi.advanceTimersByTime(300);
    expect(spy).toHaveBeenCalledTimes(1);
    throttled();
    vi.advanceTimersByTime(300);
    expect(spy).toHaveBeenCalledTimes(2);
    vi.useRealTimers();
  });
});
