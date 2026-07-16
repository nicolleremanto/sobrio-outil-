/**
 * Tests des sélecteurs claude.ai (src/selectors.ts) sur un DOM factice
 * (happy-dom). Vérifie l'ordre des fallbacks et la dégradation silencieuse
 * (retour null, jamais de throw).
 */
import { beforeEach, describe, expect, it } from 'vitest';

import { resolveFirst, resolveInputArea, resolvePanelAnchor } from '../src/selectors';

beforeEach(() => {
  document.body.innerHTML = '';
});

describe('resolveInputArea', () => {
  it('résout le sélecteur principal (ProseMirror) en priorité', () => {
    document.body.innerHTML = `
      <textarea id="fallback"></textarea>
      <div id="editeur" contenteditable="true" class="ProseMirror"></div>
    `;
    expect(resolveInputArea()?.id).toBe('editeur');
  });

  it('retombe sur un fallback si le markup principal a changé', () => {
    document.body.innerHTML = `<textarea id="zone-texte"></textarea>`;
    expect(resolveInputArea()?.id).toBe('zone-texte');
  });

  it('retombe sur un contenteditable générique', () => {
    document.body.innerHTML = `<div id="generique" contenteditable="true"></div>`;
    expect(resolveInputArea()?.id).toBe('generique');
  });

  it('retourne null sans throw quand rien ne matche (dégradation silencieuse)', () => {
    document.body.innerHTML = `<p>Aucune zone de saisie ici.</p>`;
    expect(resolveInputArea()).toBeNull();
  });
});

describe('resolvePanelAnchor', () => {
  it('préfère <main> quand il existe', () => {
    document.body.innerHTML = `<main id="principal"></main>`;
    expect(resolvePanelAnchor()?.id).toBe('principal');
  });

  it('retombe sur <body> sinon', () => {
    document.body.innerHTML = `<p>contenu</p>`;
    expect(resolvePanelAnchor()?.tagName.toLowerCase()).toBe('body');
  });
});

describe('resolveFirst', () => {
  it('ignore un sélecteur invalide sans throw et continue la liste', () => {
    document.body.innerHTML = `<span id="cible"></span>`;
    const result = resolveFirst([':::selecteur-invalide:::', '#cible'], document);
    expect(result?.id).toBe('cible');
  });

  it('retourne null sur une liste vide', () => {
    expect(resolveFirst([], document)).toBeNull();
  });
});
