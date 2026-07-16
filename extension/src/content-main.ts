/**
 * Orchestration du content script Sobrio V0 — partagée entre l'entrypoint de
 * production (claude.ai) et celui de développement (page d'entraînement).
 *
 * RÈGLE 1 : le texte (prompt, bulles) reste LOCAL — réduit en `signals`
 * (nombres + drapeaux) avant tout appel. RÈGLE 2 : lecture seule de la page
 * hôte — on n'injecte QUE notre badge/panneau (Shadow DOM). RÈGLE 3 : jamais
 * bloquant — échec/timeout ⇒ rien ne s'affiche, aucun toast, aucun crash.
 * RÈGLE 4 : aucun secret dans le bundle — réglages via storage (popup).
 */
import type { ExtensionConfig, RecoEvent } from './api';
import {
  createClient,
  createConfigCache,
  createDebouncer,
  createThrottle,
  withTimeout,
  RECOMMEND_TIMEOUT_MS,
  type RecoClientV0,
} from './client';
import { ConversationMemory } from './conversationMemory';
import { debugLog } from './debugLog';
import { mergeMessages, type Messages } from './messages';
import { removeBadge, removePanel, renderBadge, renderPanel } from './panel';
import {
  collectPageView,
  noteInputResolution,
  resolveInputArea,
  SELECTOR_BROKEN_THRESHOLD,
} from './selectors';
import { loadStoredSettings } from './settings';
import { computePromptSignals, type Signals } from './signals';

/** Dépendances injectables — tests et démo utilisent les mêmes chemins. */
export interface FlowDeps {
  client: RecoClientV0;
  memory: ConversationMemory;
  config: ExtensionConfig | null;
  messages: Messages;
  /** Horloge injectable (horodatage ISO des événements). */
  now?: () => Date;
}

/** Construit le bloc `signals` complet : prompt + mémoire de conversation. */
export function buildSignals(text: string, memory: ConversationMemory): Signals {
  return { prompt: computePromptSignals(text), conversation: memory.toSignals() };
}

/** Télémétrie STRICTE : exactement les 4 champs du contrat, rien d'autre. */
export function buildRecoEvent(
  recoId: string,
  followed: boolean,
  overriddenTo: string | null,
  now: () => Date = () => new Date(),
): RecoEvent {
  return { reco_id: recoId, followed, overridden_to: overriddenTo, ts: now().toISOString() };
}

/**
 * Cœur du flux : texte saisi → signals → reco (bornée 400 ms) → panneau.
 * Retourne la reco affichée, ou null si rien n'a été montré (silence).
 */
export async function runRecommendationFlow(text: string, deps: FlowDeps) {
  if (deps.config && !deps.config.enabled) return null; // kill-switch : inerte

  if (text.trim().length === 0) {
    removePanel();
    return null;
  }

  const signals = buildSignals(text, deps.memory);
  const reco = await withTimeout(deps.client.recommend(signals), RECOMMEND_TIMEOUT_MS);
  if (!reco) return null; // échec/timeout ⇒ NE RIEN AFFICHER (règle 3)

  deps.memory.noteRecoShown();
  const now = deps.now ?? (() => new Date());

  renderPanel(reco, {
    modelsVisible: deps.config?.models_visible ?? [],
    messages: deps.messages,
    callbacks: {
      onFollow: () => {
        deps.memory.noteFollowed();
        deps.client.sendRecoEvent(buildRecoEvent(reco.reco_id, true, null, now));
      },
      onOverride: (model) => {
        deps.memory.noteDerogation(reco.recommended_model, model);
        deps.client.sendRecoEvent(buildRecoEvent(reco.reco_id, false, model, now));
      },
    },
  });
  return reco;
}

/** Point d'entrée du content script. */
export async function bootstrap(): Promise<void> {
  const settings = await loadStoredSettings();
  const client = createClient(settings);
  const configCache = createConfigCache(client);

  // Config au démarrage (cachée). Kill-switch : on ne s'arrête que sur un
  // enabled=false EXPLICITE — un échec réseau ne désactive pas l'extension.
  const config = await configCache.get();
  if (config && !config.enabled) return;

  const messages = mergeMessages(config?.messages?.fr as Record<string, unknown> | undefined);
  const memory = new ConversationMemory();

  observeInputArea({ client, memory, config, messages });
}

/** Fenêtre du throttle d'observation DOM (garde-fou perf, boucle 5). */
const OBSERVER_THROTTLE_MS = 300;

/**
 * Observe le DOM (SPA : la zone de saisie apparaît/disparaît au fil de la
 * navigation) et attache l'écouteur de saisie dès qu'une zone est résolue.
 * Résolution `null` ⇒ on réessaie au prochain changement de DOM, sans erreur.
 * Après SELECTOR_BROKEN_THRESHOLD échecs consécutifs : flag local + UN signal
 * de santé léger (`selector_broken`, sans autre donnée) — puis silence.
 */
function observeInputArea(deps: FlowDeps): void {
  let currentInput: HTMLElement | null = null;

  const onPause = () => {
    if (!currentInput?.isConnected) return;
    // Mise à jour de la mémoire depuis la page (texte réduit localement).
    deps.memory.updateFromPage(collectPageView());
    const text =
      currentInput instanceof HTMLTextAreaElement
        ? currentInput.value
        : (currentInput.textContent ?? '');
    void runRecommendationFlow(text, deps);
  };

  const debouncer = createDebouncer(onPause);

  const ensureAttached = () => {
    if (currentInput?.isConnected) return;
    const input = resolveInputArea();
    if (noteInputResolution(Boolean(input))) {
      // Seuil franchi À L'INSTANT : un seul log debug, un seul signal.
      debugLog('selector_broken', { failures: SELECTOR_BROKEN_THRESHOLD });
      deps.client.sendHealthSignal?.('selector_broken');
    }
    if (!input) {
      removeBadge();
      return; // dégradation silencieuse (voir src/selectors.ts)
    }
    currentInput = input;
    renderBadge(deps.messages);
    // Écoute PASSIVE de la saisie — on lit, on ne modifie rien (règle 2).
    input.addEventListener('input', () => debouncer.schedule());
  };

  // Throttle : au plus une résolution par fenêtre de 300 ms, même si la page
  // mute en continu. Observer unique, déconnecté à la fermeture (zéro fuite).
  const observer = new MutationObserver(createThrottle(ensureAttached, OBSERVER_THROTTLE_MS));
  observer.observe(document.documentElement, { childList: true, subtree: true });
  window.addEventListener(
    'pagehide',
    () => {
      observer.disconnect();
      debouncer.cancel();
      removePanel();
      removeBadge();
    },
    { once: true },
  );
  ensureAttached();
}
