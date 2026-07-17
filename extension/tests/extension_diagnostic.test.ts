/**
 * Boucle 4 — diagnostic de détection : stratégie gagnante par fixture, et
 * canal de message (forme + rendu). Aucun contenu textuel dans le résultat.
 */
import { afterEach, describe, expect, it } from 'vitest';

import {
  DIAGNOSE_MESSAGE,
  formatDiagnosis,
  isDiagnoseRequest,
  runDiagnostics,
} from '../src/diagnostics';
import { diagnoseDetection } from '../src/selectors';
import { loadFixture } from '../test/loadFixture';

afterEach(() => {
  document.body.innerHTML = '';
});

describe('diagnoseDetection — stratégie par fixture', () => {
  it('nominal : sélecteur ProseMirror, modèle + bulles détectés', () => {
    loadFixture('nominal');
    const d = diagnoseDetection();
    expect(d.found).toBe(true);
    expect(d.strategy).toContain('sélecteur');
    expect(d.inputTag).toContain('ProseMirror');
    expect(d.modelDetected).toBe(true);
    expect(d.bubbleCount).toBeGreaterThanOrEqual(4);
  });

  it('alt1 : sélecteur contenteditable, bulles data-testid', () => {
    loadFixture('alt1');
    const d = diagnoseDetection();
    expect(d.found).toBe(true);
    expect(d.strategy).toContain('sélecteur');
    expect(d.bubbleCount).toBe(2);
  });

  it('alt2 : repli « plus grand éditable visible » (textarea)', () => {
    loadFixture('alt2');
    const d = diagnoseDetection();
    expect(d.found).toBe(true);
    expect(d.strategy).toContain('repli');
    expect(d.inputTag).toBe('textarea');
  });

  it('broken : rien détecté, inertie propre', () => {
    loadFixture('broken');
    const d = diagnoseDetection();
    expect(d.found).toBe(false);
    expect(d.strategy).toBe('aucune');
    expect(d.inputTag).toBeNull();
    expect(d.modelDetected).toBe(false);
  });
});

describe('canal de diagnostic', () => {
  it('isDiagnoseRequest reconnaît la requête bien formée', () => {
    expect(isDiagnoseRequest({ type: DIAGNOSE_MESSAGE })).toBe(true);
    expect(isDiagnoseRequest({ type: 'autre' })).toBe(false);
    expect(isDiagnoseRequest(null)).toBe(false);
    expect(isDiagnoseRequest('x')).toBe(false);
  });

  it('runDiagnostics renvoie {ok, diagnosis}', () => {
    loadFixture('nominal');
    const response = runDiagnostics();
    expect(response.ok).toBe(true);
    expect(response.diagnosis.found).toBe(true);
  });

  it('formatDiagnosis produit une phrase FR sans contenu de page', () => {
    loadFixture('nominal');
    const text = formatDiagnosis(diagnoseDetection());
    expect(text).toContain('Détection OK');
    expect(text).toContain('modèle détecté');
    // Aucun texte de bulle ne doit apparaître.
    expect(text).not.toContain('dérivée');
    expect(text).not.toContain('exercice');
  });

  it('formatDiagnosis explicite l’inertie quand rien n’est détecté', () => {
    loadFixture('broken');
    expect(formatDiagnosis(diagnoseDetection())).toContain('inerte');
  });
});
