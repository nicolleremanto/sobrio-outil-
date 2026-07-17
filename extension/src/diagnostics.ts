/**
 * Diagnostic de détection — canal de message entre le popup et le content
 * script. Le popup n'a pas accès au DOM de l'onglet : il DEMANDE au content
 * script d'exécuter `diagnoseDetection()` et affiche le résultat (outil pour
 * les fondateurs, sans DevTools). Aucun contenu textuel ne transite (règle 1).
 */
import { diagnoseDetection, type DetectionDiagnosis } from './selectors';

/** Type de message reconnu par le content script. */
export const DIAGNOSE_MESSAGE = 'sobrio:diagnose';

export interface DiagnoseRequest {
  type: typeof DIAGNOSE_MESSAGE;
}

export interface DiagnoseResponse {
  ok: true;
  diagnosis: DetectionDiagnosis;
}

/** Vrai si `value` est une requête de diagnostic bien formée. */
export function isDiagnoseRequest(value: unknown): value is DiagnoseRequest {
  return (
    typeof value === 'object' &&
    value !== null &&
    (value as { type?: unknown }).type === DIAGNOSE_MESSAGE
  );
}

/** Exécute le diagnostic sur le document courant (appelé côté content). */
export function runDiagnostics(): DiagnoseResponse {
  return { ok: true, diagnosis: diagnoseDetection() };
}

/** Rend un diagnostic en une phrase claire pour le popup (FR, ton factuel). */
export function formatDiagnosis(diagnosis: DetectionDiagnosis): string {
  if (!diagnosis.found) {
    return "Zone de saisie non détectée sur cet onglet — l'extension reste inerte ici.";
  }
  const model = diagnosis.modelDetected ? 'modèle détecté' : 'modèle non détecté';
  return `Détection OK · ${diagnosis.strategy} · ${diagnosis.inputTag} · ${diagnosis.bubbleCount} bulle(s) · ${model}.`;
}
