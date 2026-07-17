/**
 * Contrôleur de conversation — noue le registre multi-conversations
 * (`ConversationRegistry`) au détecteur de navigation SPA
 * (`observeConversationChanges`). Expose la mémoire ACTIVE à l'orchestration
 * du content script, et notifie chaque changement de fil (pour retirer le
 * panneau obsolète et laisser la mémoire se reconstruire).
 *
 * Reconstruction paresseuse : à l'arrivée au milieu d'un fil existant, la
 * mémoire fraîchement activée se remplit au premier `updateFromPage`
 * (re-scan des bulles visibles — comptage/tailles/drapeaux, jamais le texte).
 */
import { ConversationMemory } from './conversationMemory';
import { ConversationRegistry } from './conversationRegistry';
import { observeConversationChanges, type SpaLifecycleOptions } from './spaLifecycle';

export interface ConversationController {
  /** Mémoire de la conversation active (toujours définie après création). */
  currentMemory(): ConversationMemory;
  /** Clé de la conversation active. */
  currentKey(): string;
  /** Nombre de conversations mémorisées (diagnostic/tests). */
  size(): number;
  /** Détache les écouteurs SPA (aucune fuite). */
  stop(): void;
}

export interface ConversationControllerOptions extends SpaLifecycleOptions {
  registry?: ConversationRegistry;
  /** Appelé à chaque changement de conversation (ex. retirer le panneau). */
  onConversationChange?: (key: string) => void;
}

export function createConversationController(
  options: ConversationControllerOptions = {},
): ConversationController {
  const registry = options.registry ?? new ConversationRegistry();

  const lifecycle = observeConversationChanges((key) => {
    registry.activate(key);
    options.onConversationChange?.(key);
  }, options);

  // Active la conversation initiale (aucun onChange au démarrage).
  registry.activate(lifecycle.currentKey());

  return {
    currentMemory: () => registry.activate(lifecycle.currentKey()),
    currentKey: () => lifecycle.currentKey(),
    size: () => registry.size(),
    stop: () => lifecycle.stop(),
  };
}
