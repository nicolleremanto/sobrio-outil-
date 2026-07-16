/**
 * Journal de debug LOCAL et optionnel — règle 1 encodée dans le TYPE :
 * `debugLog` n'accepte que des nombres et des booléens en données. Il est
 * STRUCTURELLEMENT incapable d'imprimer du contenu (texte de prompt, bulle,
 * libellé) : toute valeur non numérique/booléenne est écartée au runtime, et
 * le type refuse les strings à la compilation.
 *
 * Activation : popup → « journal de debug » (browser.storage.local).
 */
import { browser } from 'wxt/browser';

const DEBUG_KEY = 'sobrio_debug';

let enabled = false;

/** Lit l'état du journal au démarrage (jamais bloquant). */
export async function initDebugLog(): Promise<void> {
  try {
    const stored = await browser.storage.local.get(DEBUG_KEY);
    enabled = stored[DEBUG_KEY] === true;
  } catch {
    enabled = false;
  }
}

/** Force l'état (popup + tests). */
export function setDebugLogEnabled(value: boolean): void {
  enabled = value;
}

export async function saveDebugLogEnabled(value: boolean): Promise<void> {
  enabled = value;
  try {
    await browser.storage.local.set({ [DEBUG_KEY]: value });
  } catch {
    // Dégradation silencieuse.
  }
}

/** Données autorisées : nombres et booléens UNIQUEMENT — jamais de texte. */
export type DebugData = Record<string, number | boolean>;

/**
 * Trace un événement nommé (littéral développeur) + données sans contenu.
 * Filtre runtime en plus du type : seules les valeurs number/boolean passent.
 */
export function debugLog(event: string, data: DebugData = {}): void {
  if (!enabled) return;
  const safe: DebugData = {};
  for (const [key, value] of Object.entries(data)) {
    if (typeof value === 'number' || typeof value === 'boolean') safe[key] = value;
  }
  // Seul point de sortie console de l'extension : événement nommé +
  // nombres/booléens, jamais de contenu (règle 1).
  // eslint-disable-next-line no-console
  console.debug(`[sobrio] ${event}`, safe);
}
