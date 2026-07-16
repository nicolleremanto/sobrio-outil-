/**
 * Application automatique du modèle dans la page hôte — SEUL module du code
 * autorisé à interagir avec l'UI de claude.ai.
 *
 * ⚠️ AMENDEMENT DE LA RÈGLE 2 (décision fondateur du 2026-07-16, consignée
 * dans docs/decisions.md) : l'extension reste en LECTURE SEULE par défaut.
 * Ce module ne s'exécute que si l'utilisateur a EXPLICITEMENT activé
 * « appliquer automatiquement le modèle » dans le popup (opt-in strict,
 * désactivé par défaut). TODO(V1) : gating supplémentaire par politique org
 * (`allow_auto_apply` — proposé dans docs/rfc/RFC-0001).
 *
 * Risques assumés et amortis :
 *  - fragilité : sélecteurs candidats + vérification du résultat + abandon
 *    silencieux à la moindre étape douteuse (jamais de retry agressif) ;
 *  - réversibilité : un seul clic d'ouverture + un seul clic d'item, jamais
 *    de saisie, jamais d'envoi de message, jamais d'autre action ;
 *  - transparence : l'utilisateur vient de cliquer « Utiliser [modèle] » —
 *    l'action est TOUJOURS déclenchée par son geste, jamais spontanée.
 */
import { debugLog } from './debugLog';
import { resolveModelButton } from './selectors';
import { normalizeModelLabel } from './signals';

/** Sélecteurs des items de menu candidats (menu du sélecteur de modèle). */
const MENU_ITEM_SELECTORS =
  '[role="menuitem"], [role="option"], [role="menuitemradio"], [role="radio"]';

export interface ApplyModelOptions {
  /** Attente maximale de l'apparition du menu (ms). */
  menuTimeoutMs?: number;
  /** Délai de stabilisation avant vérification du résultat (ms). */
  settleMs?: number;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Clic réaliste : les composants de claude.ai (Radix UI) réagissent au
 * `pointerdown`, pas seulement au `click`. On envoie la séquence complète —
 * pointerdown → pointerup → click — chacune en best-effort.
 */
function simulateClick(element: HTMLElement): void {
  const base = { bubbles: true, cancelable: true, composed: true };
  try {
    if (typeof PointerEvent === 'function') {
      element.dispatchEvent(new PointerEvent('pointerdown', { ...base, pointerId: 1 }));
      element.dispatchEvent(new PointerEvent('pointerup', { ...base, pointerId: 1 }));
    } else {
      element.dispatchEvent(new MouseEvent('mousedown', base));
      element.dispatchEvent(new MouseEvent('mouseup', base));
    }
  } catch {
    // Certains environnements refusent PointerEvent : le click suffit alors.
  }
  try {
    element.click();
  } catch {
    // Dégradation silencieuse.
  }
}

/** Cherche un item de menu dont le libellé correspond au modèle cible. */
function findMenuItem(targetId: string): HTMLElement | null {
  try {
    for (const element of document.querySelectorAll(MENU_ITEM_SELECTORS)) {
      if (!(element instanceof HTMLElement)) continue;
      if (normalizeModelLabel(element.textContent) === targetId) return element;
    }
  } catch {
    // Dégradation silencieuse.
  }
  return null;
}

/** Tente de refermer un menu ouvert (Échap), sans jamais throw. */
function tryCloseMenu(): void {
  try {
    document.activeElement?.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }),
    );
  } catch {
    // Dégradation silencieuse.
  }
}

/**
 * Applique `targetId` (id du catalogue) dans le sélecteur de modèle de la
 * page hôte. Retourne `true` UNIQUEMENT si le changement est vérifié
 * (l'étiquette relue correspond au modèle demandé). Toute incertitude ⇒
 * abandon silencieux et `false` — l'utilisateur garde la main.
 */
export async function applyModelInPage(
  targetId: string,
  options: ApplyModelOptions = {},
): Promise<boolean> {
  const menuTimeoutMs = options.menuTimeoutMs ?? 2500;
  const settleMs = options.settleMs ?? 200;
  try {
    const selector = resolveModelButton();
    if (!selector) {
      debugLog('auto_apply_abandon', { bouton_trouve: false });
      return false;
    }

    // Déjà le bon modèle : rien à faire.
    if (normalizeModelLabel(selector.textContent) === targetId) return true;

    // Ouverture du menu — première des deux seules actions simulées.
    simulateClick(selector);

    // Attente de l'item cible (le menu peut se monter de façon asynchrone).
    const deadline = Date.now() + menuTimeoutMs;
    let item = findMenuItem(targetId);
    while (!item && Date.now() < deadline) {
      await delay(50);
      item = findMenuItem(targetId);
    }
    if (!item) {
      tryCloseMenu();
      debugLog('auto_apply_abandon', { menu_trouve: false });
      return false;
    }

    // Sélection de l'item — seconde et dernière action.
    simulateClick(item);
    await delay(settleMs);

    // Vérification : l'étiquette relue doit correspondre au modèle demandé.
    const after = resolveModelButton();
    const applied = normalizeModelLabel(after?.textContent ?? null) === targetId;
    debugLog('auto_apply', { applique: applied });
    if (!applied) tryCloseMenu();
    return applied;
  } catch {
    tryCloseMenu();
    return false; // jamais bloquant, jamais d'erreur visible
  }
}
