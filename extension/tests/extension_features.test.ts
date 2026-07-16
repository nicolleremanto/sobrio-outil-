/**
 * Tests du calcul local des features (src/features.ts) — fonctions pures.
 * Vérifie notamment que seules des mesures/indicateurs sortent du module
 * (l'objet Features ne contient aucun champ textuel).
 */
import { describe, expect, it } from 'vitest';

import {
  computeFeatures,
  detectKeywordFlags,
  detectLang,
  estimateTokens,
  hasAttachmentHint,
  hasCode,
} from '../src/features';

describe('estimateTokens', () => {
  it('approxime chars / 4 arrondi supérieur', () => {
    expect(estimateTokens(0)).toBe(0);
    expect(estimateTokens(1)).toBe(1);
    expect(estimateTokens(4)).toBe(1);
    expect(estimateTokens(5)).toBe(2);
    expect(estimateTokens(400)).toBe(100);
  });

  it('ne retourne jamais de valeur négative', () => {
    expect(estimateTokens(-10)).toBe(0);
  });
});

describe('detectLang', () => {
  it('détecte le français', () => {
    expect(detectLang('Peux-tu faire une synthèse de ce document pour la réunion ?')).toBe('fr');
  });

  it('détecte l’anglais', () => {
    expect(detectLang('Please write a short summary of the meeting notes for me.')).toBe('en');
  });

  it("retourne 'other' sans indice clair", () => {
    expect(detectLang('')).toBe('other');
    expect(detectLang('12345 !!! ???')).toBe('other');
    expect(detectLang('hola mundo bonito')).toBe('other');
  });
});

describe('hasCode', () => {
  it('détecte un fence Markdown', () => {
    expect(hasCode('Corrige ce script :\n```python\nx = 1\n```')).toBe(true);
  });

  it('détecte des motifs de code hors fence', () => {
    expect(hasCode('def main():')).toBe(true);
    expect(hasCode('const total = 42;')).toBe(true);
    expect(hasCode('import os\nprint(os.name)')).toBe(true);
  });

  it('ne se déclenche pas sur du texte simple', () => {
    expect(hasCode('Rédige une lettre de motivation en trois paragraphes.')).toBe(false);
    expect(hasCode('Quelle est la capitale de la Norvège ?')).toBe(false);
  });
});

describe('hasAttachmentHint', () => {
  it('détecte les mentions françaises, accents inclus', () => {
    expect(hasAttachmentHint('Analyse la pièce jointe et liste les risques.')).toBe(true);
    expect(hasAttachmentHint('Voir le document ci-joint.')).toBe(true);
  });

  it('détecte les mentions anglaises', () => {
    expect(hasAttachmentHint('Summarize the attached file.')).toBe(true);
  });

  it('ne se déclenche pas sans mention', () => {
    expect(hasAttachmentHint('Explique-moi la photosynthèse.')).toBe(false);
  });
});

describe('detectKeywordFlags', () => {
  it('détecte la liste fermée, insensible à la casse et aux accents', () => {
    expect(detectKeywordFlags('Fais un RÉSUMÉ de ce CONTRAT.')).toEqual(['contrat', 'resume']);
    expect(detectKeywordFlags('Une analyse du code et une traduction.')).toEqual([
      'analyse',
      'code',
      'traduction',
    ]);
  });

  it('retourne une liste vide sans mot-clé', () => {
    expect(detectKeywordFlags('Bonjour, comment vas-tu ?')).toEqual([]);
  });

  it("ne retourne que des valeurs de l'énumération du contrat", () => {
    const allowed = new Set(['contrat', 'analyse', 'code', 'resume', 'traduction']);
    const flags = detectKeywordFlags('contrat analyse code resume traduction budget pdf');
    expect(flags.length).toBeGreaterThan(0);
    for (const flag of flags) expect(allowed.has(flag)).toBe(true);
  });
});

describe('computeFeatures', () => {
  it('retourne un objet conforme au schéma Features du contrat', () => {
    const text = 'Analyse ce contrat et fais un résumé pour la direction.';
    const features = computeFeatures(text);
    expect(features).toEqual({
      char_len: text.length,
      token_est: Math.ceil(text.length / 4),
      lang: 'fr',
      has_code: false,
      has_attachment_hint: false,
      keyword_flags: ['contrat', 'analyse', 'resume'],
    });
  });

  it('bornes : texte vide', () => {
    expect(computeFeatures('')).toEqual({
      char_len: 0,
      token_est: 0,
      lang: 'other',
      has_code: false,
      has_attachment_hint: false,
      keyword_flags: [],
    });
  });

  it("règle n°1 : l'objet retourné ne contient AUCUN champ textuel du prompt", () => {
    const secret = 'clause confidentielle unique xyzzy-42';
    const features = computeFeatures(`Analyse ce contrat : ${secret}`);
    expect(JSON.stringify(features)).not.toContain('xyzzy');
    expect(Object.keys(features).sort()).toEqual([
      'char_len',
      'has_attachment_hint',
      'has_code',
      'keyword_flags',
      'lang',
      'token_est',
    ]);
  });
});
