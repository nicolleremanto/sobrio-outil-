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
import type { BubbleView, PageView } from './conversationMemory';

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

// ---------------------------------------------------------------------------
// Vue de page (boucle 1) — lecture LOCALE des bulles, de l'étiquette de
// modèle et de l'identifiant de fil, pour la mémoire de conversation.
// Le texte lu ici est immédiatement réduit en signaux (conversationMemory) —
// il ne quitte jamais le content script (règle 1).
// ---------------------------------------------------------------------------

/** Bulles de conversation — claude.ai + page d'entraînement. */
export const BUBBLE_SELECTORS: readonly string[] = [
  '[data-message-author-role]',
  '[data-testid="user-message"], [data-testid="assistant-message"]',
];

/** Étiquette du modèle courant (lue, jamais modifiée — règle n°2). */
export const MODEL_LABEL_SELECTORS: readonly string[] = [
  '[data-testid="model-selector"]',
  'button[aria-haspopup="menu"][class*="model"]',
];

/** Conteneur porteur d'un identifiant de fil (page d'entraînement). */
export const THREAD_ID_SELECTORS: readonly string[] = ['[data-thread-id]'];

/** Rôle d'une bulle depuis ses attributs ; 'unknown' par défaut. */
function bubbleRole(element: HTMLElement): BubbleView['role'] {
  const role =
    element.getAttribute('data-message-author-role') ??
    (element.getAttribute('data-testid')?.startsWith('user') ? 'user' : null) ??
    (element.getAttribute('data-testid')?.startsWith('assistant') ? 'assistant' : null);
  return role === 'user' || role === 'assistant' ? role : 'unknown';
}

/**
 * Identifiant de fil : attribut DOM dédié, sinon chemin d'URL de type
 * /chat/<id> (claude.ai). `null` si indéterminable — la mémoire bascule alors
 * sur la détection par régression du nombre de bulles.
 */
export function resolveThreadId(
  root: ParentNode = document,
  pathname: string = location.pathname,
): string | null {
  const carrier = resolveFirst(THREAD_ID_SELECTORS, root);
  const fromDom = carrier?.getAttribute('data-thread-id');
  if (fromDom) return fromDom;
  const fromUrl = /\/chat\/([\w-]+)/.exec(pathname);
  return fromUrl?.[1] ?? null;
}

/**
 * Collecte la vue de page pour la mémoire de conversation. Ne throw jamais :
 * en cas de DOM inattendu, retourne une vue vide (dégradation silencieuse).
 */
export function collectPageView(
  root: ParentNode = document,
  pathname: string = location.pathname,
): PageView {
  try {
    const bubbles: BubbleView[] = [];
    for (const selector of BUBBLE_SELECTORS) {
      const found = root.querySelectorAll(selector);
      if (found.length === 0) continue;
      for (const element of found) {
        if (element instanceof HTMLElement) {
          bubbles.push({ role: bubbleRole(element), text: element.textContent ?? '' });
        }
      }
      break; // première stratégie qui matche
    }
    const label = resolveFirst(MODEL_LABEL_SELECTORS, root);
    return {
      threadId: resolveThreadId(root, pathname),
      bubbles,
      modelLabel: label?.textContent?.trim() ?? null,
    };
  } catch {
    return { threadId: null, bubbles: [], modelLabel: null };
  }
}
