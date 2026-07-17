/**
 * Registre de mémoires de conversation — claude.ai est une SPA : plusieurs
 * fils vivent dans le même onglet sans rechargement. On garde une
 * `ConversationMemory` DISTINCTE par conversation (clé = identifiant d'URL),
 * conservée en session tant que l'utilisateur navigue entre fils, et purgée
 * à la fermeture de l'onglet (le registre meurt avec le content script).
 *
 * Multi-onglets : chaque onglet exécute son propre content script, donc son
 * propre registre — les états sont indépendants par construction (test dédié).
 *
 * RÈGLE 1 : chaque mémoire ne stocke que des compteurs/drapeaux, jamais le
 * texte (voir conversationMemory.ts).
 */
import { ConversationMemory } from './conversationMemory';

/** Plafond de conversations mémorisées simultanément (éviction LRU douce). */
export const MAX_CONVERSATIONS = 25;

export class ConversationRegistry {
  private readonly memories = new Map<string, ConversationMemory>();
  private activeKey: string | null = null;

  constructor(
    private readonly factory: () => ConversationMemory = () => new ConversationMemory(),
    private readonly maxSize: number = MAX_CONVERSATIONS,
  ) {}

  /**
   * Active (en la créant au besoin) la mémoire de la conversation `key` et la
   * retourne. Réactiver une clé connue restitue son état antérieur intact.
   */
  activate(key: string): ConversationMemory {
    let memory = this.memories.get(key);
    if (!memory) {
      this.evictIfNeeded();
      memory = this.factory();
      this.memories.set(key, memory);
    } else {
      // Rafraîchit l'ordre d'insertion (LRU) : on la remet en fin de Map.
      this.memories.delete(key);
      this.memories.set(key, memory);
    }
    this.activeKey = key;
    return memory;
  }

  /** Mémoire active courante, ou `null` si aucune conversation activée. */
  current(): ConversationMemory | null {
    return this.activeKey ? (this.memories.get(this.activeKey) ?? null) : null;
  }

  /** Clé de la conversation active (ou `null`). */
  get activeConversationKey(): string | null {
    return this.activeKey;
  }

  /** Nombre de conversations mémorisées. */
  size(): number {
    return this.memories.size;
  }

  /** Vide tout le registre (rarement utile : la fermeture d'onglet suffit). */
  clear(): void {
    this.memories.clear();
    this.activeKey = null;
  }

  /** Évince la conversation la plus ancienne (sauf l'active) si le plafond
   * est atteint — garde-fou mémoire pour les très longues sessions. */
  private evictIfNeeded(): void {
    if (this.memories.size < this.maxSize) return;
    for (const key of this.memories.keys()) {
      if (key !== this.activeKey) {
        this.memories.delete(key);
        return;
      }
    }
  }
}
