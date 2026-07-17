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
  createDebouncer,
  createThrottle,
  withTimeout,
  RECOMMEND_TIMEOUT_MS,
  type RecoClientV0,
} from './client';
import { isVersionSupported, localVersion, resolveConfig } from './remoteConfig';
import { ConversationMemory } from './conversationMemory';
import { createConversationController } from './conversationController';
import { debugLog } from './debugLog';
import { mergeMessages, type Messages } from './messages';
import { applyModelInPage } from './modelSwitcher';
import { removeBadge, removePanel, renderBadge, renderPanel, repositionBadge } from './panel';
import {
  collectPageView,
  noteInputResolution,
  resolveInputArea,
  SELECTOR_BROKEN_THRESHOLD,
} from './selectors';
import { loadStoredSettings } from './settings';
import { computePromptSignals, type Signals } from './signals';
import { TelemetryQueue, telemetryAllowed } from './telemetryQueue';

/** Dépendances injectables — tests et démo utilisent les mêmes chemins. */
export interface FlowDeps {
  client: RecoClientV0;
  memory: ConversationMemory;
  config: ExtensionConfig | null;
  messages: Messages;
  /** Horloge injectable (horodatage ISO des événements). */
  now?: () => Date;
  /**
   * Application automatique du modèle dans la page hôte — présent UNIQUEMENT
   * si l'utilisateur a activé l'opt-in (amendement règle 2, 2026-07-16).
   * Absent ⇒ lecture seule stricte (comportement par défaut).
   */
  applyModel?: (model: string) => Promise<boolean>;
  /**
   * Émission d'un événement de télémétrie. Par défaut : `client.sendRecoEvent`
   * (capture mock). En production, la file persistante (bootstrap) est
   * branchée ici, et vaut noop si la télémétrie est interdite (kill-switch /
   * opt-out org).
   */
  sendEvent?: (event: RecoEvent) => void;
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
  const send = deps.sendEvent ?? ((event: RecoEvent) => deps.client.sendRecoEvent(event));

  renderPanel(reco, {
    modelsVisible: deps.config?.models_visible ?? [],
    messages: deps.messages,
    mode: deps.config?.mode,
    callbacks: {
      onFollow: () => {
        deps.memory.noteFollowed();
        send(buildRecoEvent(reco.reco_id, true, null, now));
        // Opt-in uniquement : action déclenchée par le clic de l'utilisateur,
        // fire-and-forget, échec silencieux (il garde la main).
        void deps.applyModel?.(reco.recommended_model);
      },
      onOverride: (model) => {
        deps.memory.noteDerogation(reco.recommended_model, model);
        send(buildRecoEvent(reco.reco_id, false, model, now));
        void deps.applyModel?.(model);
      },
    },
  });
  return reco;
}

/** Point d'entrée du content script. */
export async function bootstrap(): Promise<void> {
  const settings = await loadStoredSettings();
  const client = createClient(settings);

  // Config au démarrage : cache persistant TTL 1 h, rafraîchissement
  // silencieux, dernier état connu conservé hors-ligne (voir remoteConfig.ts).
  const { config } = await resolveConfig(client);

  // Kill-switch : on ne s'arrête que sur un enabled=false EXPLICITE — un échec
  // réseau ne désactive pas l'extension (le dernier état connu prévaut).
  if (config && !config.enabled) return;

  // Version obsolète : l'extension s'auto-désactive (le popup guide la mise à
  // jour) — aucune gêne dans la page (règle 3).
  if (config && !isVersionSupported(localVersion(), config.min_extension_version)) {
    return;
  }

  const messages = mergeMessages(config?.messages?.fr as Record<string, unknown> | undefined);

  // Registre multi-conversations + détection de navigation SPA : chaque fil a
  // sa propre mémoire, restituée en revenant dessus, reconstruite à l'arrivée
  // au milieu d'un fil existant. Changement de conversation ⇒ panneau retiré.
  const controller = createConversationController({
    onConversationChange: () => removePanel(),
  });

  // Application automatique du modèle : OPT-IN STRICT (popup), sinon absent
  // ⇒ lecture seule (amendement règle 2 du 2026-07-16, docs/decisions.md).
  const applyModel = settings.autoApplyModel
    ? (model: string) => applyModelInPage(model)
    : undefined;

  // Télémétrie : file persistante avec retry. Reprise des événements en
  // attente au démarrage. Interdite (noop) si kill-switch ou opt-out org.
  const telemetry = new TelemetryQueue((event) => Promise.resolve(client.deliverRecoEvent(event)));
  void telemetry.flush(); // reprend les envois en attente d'une session passée
  const sendEvent = telemetryAllowed(config)
    ? (event: RecoEvent) => void telemetry.enqueue(event)
    : () => {};

  const baseDeps: FlowDeps = {
    client,
    memory: controller.currentMemory(),
    config,
    messages,
    applyModel,
    sendEvent,
  };
  observeInputArea(baseDeps, () => controller.currentMemory(), controller.stop);
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
function observeInputArea(
  baseDeps: FlowDeps,
  getMemory: () => ConversationMemory = () => baseDeps.memory,
  onStop?: () => void,
): void {
  let currentInput: HTMLElement | null = null;

  const onPause = () => {
    if (!currentInput?.isConnected) return;
    // Mémoire de la conversation ACTIVE (le fil a pu changer sans rechargement).
    const memory = getMemory();
    // Mise à jour de la mémoire depuis la page (texte réduit localement) :
    // reconstruit aussi la mémoire à l'arrivée au milieu d'un fil existant.
    memory.updateFromPage(collectPageView());
    const text =
      currentInput instanceof HTMLTextAreaElement
        ? currentInput.value
        : (currentInput.textContent ?? '');
    void runRecommendationFlow(text, { ...baseDeps, memory });
  };

  const debouncer = createDebouncer(onPause);

  const ensureAttached = () => {
    if (currentInput?.isConnected) {
      repositionBadge(); // la barre a pu bouger (layout, panneau latéral…)
      return;
    }
    const input = resolveInputArea();
    if (noteInputResolution(Boolean(input))) {
      // Seuil franchi À L'INSTANT : un seul log debug, un seul signal.
      debugLog('selector_broken', { failures: SELECTOR_BROKEN_THRESHOLD });
      baseDeps.client.sendHealthSignal?.('selector_broken');
    }
    if (!input) {
      removeBadge();
      return; // dégradation silencieuse (voir src/selectors.ts)
    }
    currentInput = input;
    // Badge ancré sur la barre de saisie (overlay — règle 2).
    renderBadge(baseDeps.messages, input);
    // Écoute PASSIVE de la saisie — on lit, on ne modifie rien (règle 2).
    input.addEventListener('input', () => debouncer.schedule());
  };

  // Throttle : au plus une résolution par fenêtre de 300 ms, même si la page
  // mute en continu. Observer unique, déconnecté à la fermeture (zéro fuite).
  const observer = new MutationObserver(createThrottle(ensureAttached, OBSERVER_THROTTLE_MS));
  observer.observe(document.documentElement, { childList: true, subtree: true });
  // Le badge suit la barre de saisie au scroll et au redimensionnement.
  const throttledReposition = createThrottle(repositionBadge, 100);
  window.addEventListener('resize', throttledReposition, { passive: true });
  document.addEventListener('scroll', throttledReposition, { capture: true, passive: true });
  window.addEventListener(
    'pagehide',
    () => {
      observer.disconnect();
      debouncer.cancel();
      window.removeEventListener('resize', throttledReposition);
      document.removeEventListener('scroll', throttledReposition, { capture: true });
      onStop?.(); // détache le contrôleur SPA (aucune fuite)
      removePanel();
      removeBadge();
    },
    { once: true },
  );
  ensureAttached();
}
