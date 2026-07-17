/**
 * Cycle de vie SPA — claude.ai change de conversation SANS rechargement de
 * page. On détecte ces transitions via l'API History (pushState/replaceState
 * enveloppés) + popstate + hashchange, et on notifie l'appelant à chaque
 * changement de clé de conversation.
 *
 * `poll()` permet une vérification manuelle. Il est CÂBLÉ en production comme
 * filet de sécurité périodique (voir `ConversationController.pollIntervalMs`,
 * 2 s) au cas où un routeur SPA contournerait History ; en tests, le polling
 * est désactivé (détection purement événementielle, déterministe).
 */

/** Dérive une clé de conversation STABLE depuis un chemin d'URL. */
export function conversationKeyFromPath(pathname: string): string {
  const chat = /\/chat\/([\w-]+)/.exec(pathname);
  if (chat) return `chat:${chat[1]}`;
  const project = /\/project\/([\w-]+)/.exec(pathname);
  if (project) return `project:${project[1]}`;
  // Nouvelle conversation / accueil : une clé commune, réinitialisée dès
  // qu'un vrai fil apparaît.
  return 'new';
}

export interface SpaLifecycle {
  /** Clé de conversation courante. */
  currentKey(): string;
  /** Vérifie manuellement un éventuel changement (tests / filet périodique). */
  poll(): void;
  /** Détache tous les écouteurs et restaure History (aucune fuite). */
  stop(): void;
}

export interface SpaLifecycleOptions {
  /** Source du chemin courant (injectable pour les tests). */
  getPath?: () => string;
  /** Objet History (injectable pour les tests). */
  history?: History;
  /** Cible d'écoute des événements (injectable pour les tests). */
  target?: Pick<Window, 'addEventListener' | 'removeEventListener'>;
}

/**
 * Observe les changements de conversation et appelle `onChange(nouvelleClé)`
 * à chaque transition (jamais au démarrage : la clé initiale est lisible via
 * `currentKey()`).
 */
export function observeConversationChanges(
  onChange: (key: string) => void,
  options: SpaLifecycleOptions = {},
): SpaLifecycle {
  const getPath = options.getPath ?? (() => location.pathname);
  const hist = options.history ?? (typeof history !== 'undefined' ? history : undefined);
  const target = options.target ?? (typeof window !== 'undefined' ? window : undefined);

  let key = conversationKeyFromPath(getPath());

  const check = () => {
    const next = conversationKeyFromPath(getPath());
    if (next !== key) {
      key = next;
      try {
        onChange(next);
      } catch {
        // L'appelant ne doit jamais faire échouer la détection.
      }
    }
  };

  // Enveloppe pushState/replaceState pour capter la navigation programmatique.
  let origPush: History['pushState'] | null = null;
  let origReplace: History['replaceState'] | null = null;
  if (hist) {
    origPush = hist.pushState.bind(hist);
    origReplace = hist.replaceState.bind(hist);
    hist.pushState = function patchedPush(...args: Parameters<History['pushState']>) {
      const result = origPush!(...args);
      check();
      return result;
    };
    hist.replaceState = function patchedReplace(...args: Parameters<History['replaceState']>) {
      const result = origReplace!(...args);
      check();
      return result;
    };
  }
  target?.addEventListener('popstate', check);
  target?.addEventListener('hashchange', check);

  return {
    currentKey: () => key,
    poll: check,
    stop() {
      if (hist && origPush && origReplace) {
        hist.pushState = origPush;
        hist.replaceState = origReplace;
      }
      target?.removeEventListener('popstate', check);
      target?.removeEventListener('hashchange', check);
    },
  };
}
