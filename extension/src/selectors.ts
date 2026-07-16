/**
 * Sélecteurs claude.ai — module DÉDIÉ, seul endroit du code qui connaît la
 * structure DOM de claude.ai.
 *
 * Dégradation silencieuse (documentée) : claude.ai change régulièrement son
 * markup ; chaque cible a donc une liste de fallbacks, et la résolution
 * retourne `null` sans JAMAIS throw. `null` ⇒ l'extension ne fait rien
 * (jamais bloquant pour l'utilisateur).
 *
 * Règle n°2 : ces sélecteurs servent uniquement à LIRE la zone de saisie et à
 * choisir un point d'ancrage pour NOTRE panneau — jamais à modifier le DOM
 * fonctionnel de claude.ai.
 *
 * TODO(LotA) : vérifier/mettre à jour les sélecteurs contre le claude.ai
 * courant et ajouter un test de fumée manuel dans la checklist de release.
 */

/** Zone de saisie du prompt — du plus spécifique au plus générique. */
export const INPUT_SELECTORS: readonly string[] = [
  'div[contenteditable="true"].ProseMirror',
  'div[contenteditable="true"][role="textbox"]',
  'div[contenteditable="true"][aria-label]',
  'fieldset div[contenteditable="true"]',
  'div[contenteditable="true"]',
  'textarea',
];

/**
 * Point d'ancrage du panneau Sobrio : l'hôte est ajouté À CÔTÉ (append), le
 * contenu vit dans un Shadow DOM — aucun impact sur le DOM fonctionnel.
 */
export const PANEL_ANCHOR_SELECTORS: readonly string[] = ['main', 'body'];

/**
 * Retourne le premier élément correspondant à l'un des sélecteurs, dans
 * l'ordre. Retourne `null` si rien ne matche ou si un sélecteur est invalide
 * — ne throw jamais (dégradation silencieuse).
 */
export function resolveFirst(selectors: readonly string[], root: ParentNode): HTMLElement | null {
  for (const selector of selectors) {
    try {
      const element = root.querySelector(selector);
      if (element instanceof HTMLElement) return element;
    } catch {
      // Sélecteur invalide ou DOM indisponible : on essaie le suivant.
    }
  }
  return null;
}

/** Résout la zone de saisie du prompt ; `null` si introuvable. */
export function resolveInputArea(root: ParentNode = document): HTMLElement | null {
  return resolveFirst(INPUT_SELECTORS, root);
}

/** Résout le point d'ancrage du panneau ; `null` si introuvable. */
export function resolvePanelAnchor(root: ParentNode = document): HTMLElement | null {
  return resolveFirst(PANEL_ANCHOR_SELECTORS, root);
}
