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
  withTimeout,
  RECOMMEND_TIMEOUT_MS,
  type RecoClientV0,
} from './client';
import { ConversationMemory } from './conversationMemory';
import { mergeMessages, type Messages } from './messages';
import { removeBadge, removePanel, renderBadge, renderPanel } from './panel';
import { collectPageView, resolveInputArea } from './selectors';
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

/**
 * Observe le DOM (SPA : la zone de saisie apparaît/disparaît au fil de la
 * navigation) et attache l'écouteur de saisie dès qu'une zone est résolue.
 * Résolution `null` ⇒ on réessaie au prochain changement de DOM, sans erreur.
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
    if (!input) {
      removeBadge();
      return; // dégradation silencieuse (voir src/selectors.ts)
    }
    currentInput = input;
    renderBadge(deps.messages);
    // Écoute PASSIVE de la saisie — on lit, on ne modifie rien (règle 2).
    input.addEventListener('input', () => debouncer.schedule());
  };

  const observer = new MutationObserver(ensureAttached);
  observer.observe(document.documentElement, { childList: true, subtree: true });
  ensureAttached();
}
