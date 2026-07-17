/**
 * Boucle 1 — signaux du prompt : langue, code, maths, drapeaux, mesures.
 */
import { describe, expect, it } from 'vitest';

import {
  computePromptSignals,
  detectKeywordFlagsV0,
  hasMath,
  normalizeModelLabel,
  KEYWORD_FLAGS_V0,
} from '../src/signals';

describe('computePromptSignals — mesures', () => {
  it('mesure char_len et estime token_est ≈ len/4', () => {
    const signals = computePromptSignals('a'.repeat(400));
    expect(signals.char_len).toBe(400);
    expect(signals.token_est).toBe(100);
  });

  it('détecte le français', () => {
    const signals = computePromptSignals(
      'Peux-tu résumer ce texte pour la réunion de demain avec les équipes ?',
    );
    expect(signals.lang).toBe('fr');
  });

  it("détecte l'anglais", () => {
    const signals = computePromptSignals('Please write a summary of the meeting notes for me.');
    expect(signals.lang).toBe('en');
  });
});

describe('hasMath', () => {
  it('détecte les symboles mathématiques (∫, ², √)', () => {
    expect(hasMath('Calcule ∫ f(x) dx sur [0,1]')).toBe(true);
    expect(hasMath('x² + 3x')).toBe(true);
    expect(hasMath('√2 est irrationnel')).toBe(true);
  });

  it('détecte le LaTeX et les motifs numériques', () => {
    expect(hasMath('\\frac{a}{b} est une fraction')).toBe(true);
    expect(hasMath('on a 3 + 4 = 7')).toBe(true);
  });

  it('détecte le lexique fr/en (démontre, theorem, preuve…)', () => {
    expect(hasMath('Démontre que la suite converge')).toBe(true);
    expect(hasMath('Prove the theorem holds')).toBe(true);
  });

  it('ne signale pas un texte ordinaire', () => {
    expect(hasMath('Rédige un email de relance poli pour le client.')).toBe(false);
  });
});

describe('detectKeywordFlagsV0 — liste fermée', () => {
  it('détecte les drapeaux malgré casse/accents/dérivés', () => {
    expect(detectKeywordFlagsV0('Résume-moi ce CONTRAT')).toEqual(
      expect.arrayContaining(['contrat', 'resume']),
    );
    expect(detectKeywordFlagsV0('démontre le lemme')).toContain('demonstration');
    expect(detectKeywordFlagsV0('translate this paragraph')).toContain('traduction');
  });

  it("n'émet que des valeurs de la liste fermée", () => {
    const flags = detectKeywordFlagsV0(
      'Analyse ce contrat, résume, traduis, code une démonstration.',
    );
    for (const flag of flags) {
      expect(KEYWORD_FLAGS_V0).toContain(flag);
    }
  });
});

describe('normalizeModelLabel — vocabulaire fermé, jamais le libellé brut', () => {
  it('normalise les libellés claude.ai vers les ids du catalogue', () => {
    expect(normalizeModelLabel('Claude Opus 4.8')).toBe('claude-opus-4-8');
    expect(normalizeModelLabel('Claude Sonnet 4.6')).toBe('claude-sonnet-5');
    expect(normalizeModelLabel('claude haiku 4.5 (aperçu)')).toBe('claude-haiku-4-5');
  });

  it('retourne null pour un libellé inconnu (rien du texte ne fuit)', () => {
    expect(normalizeModelLabel('GPT-9 Ultra')).toBeNull();
    expect(normalizeModelLabel(null)).toBeNull();
  });

  it('retombe sur la famille si la version est inconnue du catalogue', () => {
    expect(normalizeModelLabel('Claude Opus 9.1')).toBe('claude-opus-4-8');
  });
});

describe('computePromptSignals — drapeaux booléens', () => {
  it('has_code pour un fence, has_math pour une intégrale', () => {
    expect(computePromptSignals('voici : ```js\nlet x=1\n```').has_code).toBe(true);
    expect(computePromptSignals('calcule ∫ x dx').has_math).toBe(true);
  });

  it('prompt court et simple : aucun drapeau', () => {
    const signals = computePromptSignals('Bonjour, quelle heure est-il à Paris ?');
    expect(signals.has_code).toBe(false);
    expect(signals.has_math).toBe(false);
    expect(signals.keyword_flags).toEqual([]);
  });
});
