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
import { normalizeModelLabel } from './signals';

/**
 * Zone de saisie du prompt — STRATÉGIE 1 : sélecteurs candidats ordonnés,
 * du plus spécifique au plus générique. La STRATÉGIE 2 (repli) est
 * `fallbackLargestEditable` : « le plus grand textarea/contenteditable
 * visible ». Si tout échoue : dégradation silencieuse (extension inerte).
 */
export const INPUT_SELECTORS: readonly string[] = [
  'div[contenteditable="true"].ProseMirror',
  'div[contenteditable="true"][role="textbox"]',
  'div[contenteditable="true"][aria-label]',
  'fieldset div[contenteditable="true"]',
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

/** Vraisemblablement visible ? (heuristique prudente, jamais de throw) */
function isLikelyVisible(element: HTMLElement): boolean {
  try {
    if (element.hidden) return false;
    if (element.getAttribute('aria-hidden') === 'true') return false;
    const inline = element.getAttribute('style') ?? '';
    if (/display\s*:\s*none|visibility\s*:\s*hidden/.test(inline)) return false;
    return true;
  } catch {
    return false;
  }
}

/** Aire rendue (0 dans les environnements de test — départage par ordre). */
function renderedArea(element: HTMLElement): number {
  try {
    const rect = element.getBoundingClientRect();
    return Math.max(0, rect.width) * Math.max(0, rect.height);
  } catch {
    return 0;
  }
}

/**
 * STRATÉGIE 2 (repli) : le plus grand `textarea`/`contenteditable` visible.
 * À aire égale (ou inconnue), le premier dans l'ordre du document gagne.
 */
export function fallbackLargestEditable(root: ParentNode = document): HTMLElement | null {
  try {
    const candidates = root.querySelectorAll('textarea, [contenteditable="true"]');
    let best: HTMLElement | null = null;
    let bestArea = -1;
    for (const candidate of candidates) {
      if (!(candidate instanceof HTMLElement) || !isLikelyVisible(candidate)) continue;
      const area = renderedArea(candidate);
      if (area > bestArea) {
        best = candidate;
        bestArea = area;
      }
    }
    return best;
  } catch {
    return null;
  }
}

/**
 * Résout la zone de saisie : sélecteurs ordonnés puis heuristique de repli ;
 * `null` si tout échoue (dégradation silencieuse, extension inerte).
 */
export function resolveInputArea(root: ParentNode = document): HTMLElement | null {
  return resolveFirst(INPUT_SELECTORS, root) ?? fallbackLargestEditable(root);
}

// ---------------------------------------------------------------------------
// Détecteur de casse — si la résolution échoue N fois de suite, on lève un
// flag local (une seule fois) : un log debug + un signal de santé léger
// `selector_broken` (SANS autre donnée) pour être alertés.
// ---------------------------------------------------------------------------

/** Échecs consécutifs avant de déclarer les sélecteurs cassés. */
export const SELECTOR_BROKEN_THRESHOLD = 5;

let consecutiveFailures = 0;
let broken = false;

/** À appeler à chaque tentative de résolution. Retourne true au moment
 * précis où le seuil vient d'être franchi (déclencheur unique). */
export function noteInputResolution(found: boolean): boolean {
  if (found) {
    consecutiveFailures = 0;
    return false;
  }
  consecutiveFailures += 1;
  if (!broken && consecutiveFailures >= SELECTOR_BROKEN_THRESHOLD) {
    broken = true;
    return true;
  }
  return false;
}

/** Les sélecteurs sont-ils déclarés cassés pour cette session ? */
export function selectorsBroken(): boolean {
  return broken;
}

/** Réinitialisation (tests). */
export function resetSelectorHealth(): void {
  consecutiveFailures = 0;
  broken = false;
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

/** Étiquette du modèle courant — candidats ordonnés (claude.ai + testpage). */
export const MODEL_LABEL_SELECTORS: readonly string[] = [
  '[data-testid="model-selector-dropdown"]',
  '[data-testid="model-selector"]',
  'button[aria-haspopup="menu"][class*="model"]',
];

/** Conteneur porteur d'un identifiant de fil (page d'entraînement). */
export const THREAD_ID_SELECTORS: readonly string[] = ['[data-thread-id]'];

/**
 * Résout le BOUTON du sélecteur de modèle : candidats ordonnés, puis
 * heuristique de repli — premier bouton de la page dont le libellé évoque un
 * modèle du catalogue (les boutons de NOTRE panneau vivent dans un Shadow DOM
 * et ne sont donc jamais capturés par ce scan). `null` si introuvable.
 */
export function resolveModelButton(root: ParentNode = document): HTMLElement | null {
  const direct = resolveFirst(MODEL_LABEL_SELECTORS, root);
  if (direct) return direct;
  try {
    for (const button of root.querySelectorAll('button')) {
      if (!(button instanceof HTMLElement)) continue;
      if (normalizeModelLabel(button.textContent) !== null) return button;
    }
  } catch {
    // Dégradation silencieuse.
  }
  return null;
}

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
    const label = resolveModelButton(root);
    return {
      threadId: resolveThreadId(root, pathname),
      bubbles,
      modelLabel: label?.textContent?.trim() ?? null,
    };
  } catch {
    return { threadId: null, bubbles: [], modelLabel: null };
  }
}
