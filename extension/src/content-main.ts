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
import type { AssistMode, ExtensionConfig, RecoEvent } from './api';
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
import { applyModelInPage, readCurrentModel as readCurrentModelFromPage } from './modelSwitcher';
import {
  isPanelPresent,
  removeBadge,
  removePanel,
  renderBadge,
  renderPanel,
  repositionBadge,
} from './panel';
import {
  collectPageView,
  noteInputResolution,
  resolveInputArea,
  SELECTOR_BROKEN_THRESHOLD,
} from './selectors';
import { loadStoredSettings } from './settings';
import { computePromptSignals, type Signals } from './signals';
import { TelemetryQueue, telemetryAllowed } from './telemetryQueue';

/** Seuil de confiance par défaut de la bascule `auto` (RFC-0003). */
export const DEFAULT_AUTO_THRESHOLD = 0.75;

/**
 * Mode d'assistance EFFECTIF (RFC-0003) : intersection du consentement local et
 * de la politique org. L'opt-out local strict (`autoApplyModel=false`, règle 2)
 * force `guide` (aucun contact page) ; sinon la config org décide, `one_click`
 * par défaut. La config peut forcer `guide` (kill-switch prudence CGU).
 */
export function resolveAssistMode(
  config: ExtensionConfig | null,
  autoApplyEnabled: boolean,
): AssistMode {
  if (!autoApplyEnabled) return 'guide';
  return config?.assist_mode ?? 'one_click';
}

/** Dépendances injectables — tests et démo utilisent les mêmes chemins. */
export interface FlowDeps {
  client: RecoClientV0;
  memory: ConversationMemory;
  config: ExtensionConfig | null;
  messages: Messages;
  /** Horloge injectable (horodatage ISO des événements). */
  now?: () => Date;
  /**
   * Application du modèle dans la page hôte. Présent en `auto`/`one_click`,
   * ABSENT en `guide` (aucun contact page) — voir `resolveAssistMode`.
   * `isCurrent` (optionnel) est propagé jusqu'au clic terminal : la sélection
   * s'abandonne si la conversation a changé pendant la navigation des menus.
   */
  applyModel?: (model: string, isCurrent?: () => boolean) => Promise<boolean>;
  /**
   * Lecture (seule) du modèle courant de la page — requise par la bascule
   * `auto` pour pouvoir Annuler (restaurer le précédent). Absent ⇒ pas d'auto.
   */
  readCurrentModel?: () => string | null;
  /** Mode d'assistance effectif (RFC-0003). Absent ⇒ 'one_click'. */
  assistMode?: AssistMode;
  /** Seuil de bascule auto. Absent ⇒ DEFAULT_AUTO_THRESHOLD. */
  autoThreshold?: number;
  /**
   * Vrai si la conversation d'origine du flux est TOUJOURS active. Empêche
   * d'afficher ou de basculer sur un fil dont l'utilisateur est déjà parti
   * (navigation SPA pendant l'appel réseau). Absent ⇒ toujours courant.
   */
  isCurrent?: () => boolean;
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

/**
 * Acceptation d'une bascule auto EN ATTENTE de confirmation. Committée (une
 * seule fois) quand l'utilisateur écarte le panneau sans annuler, change de
 * conversation, ou déclenche un flux suivant. Module-level : au plus une
 * bascule auto en attente à la fois (le panneau de reco est unique).
 */
let pendingAutoAccept: (() => void) | null = null;

/** Committe l'acceptation auto en attente, s'il y en a une (idempotent). */
export function flushPendingAutoAccept(): void {
  const commit = pendingAutoAccept;
  pendingAutoAccept = null;
  commit?.();
}

/**
 * Génération de flux : un `runRecommendationFlow` qui affiche un panneau
 * incrémente ce compteur et devient « le plus récent ». Un flux plus ancien,
 * dont la bascule lente se résout APRÈS qu'un flux plus récent l'a supplanté
 * (debounce 600 ms < bascule ~2,7 s), le détecte et committe son acceptation
 * immédiatement plutôt que d'écraser le pending du plus récent (anti-orphelin).
 */
let flowGeneration = 0;

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
    flushPendingAutoAccept(); // panneau retiré = l'auto précédent est accepté
    removePanel();
    return null;
  }

  const signals = buildSignals(text, deps.memory);
  const reco = await withTimeout(deps.client.recommend(signals), RECOMMEND_TIMEOUT_MS);
  if (!reco) return null; // échec/timeout ⇒ NE RIEN AFFICHER (règle 3)

  // La conversation a pu changer PENDANT l'appel réseau : ne rien afficher ni
  // basculer sur un fil qui n'est plus actif (anti-fuite inter-conversations).
  const isCurrent = deps.isCurrent ?? (() => true);
  if (!isCurrent()) return null;

  // Ce flux devient le plus récent (supersession des flux concurrents antérieurs).
  const generation = ++flowGeneration;
  const isLatest = () => generation === flowGeneration;

  deps.memory.noteRecoShown();
  const now = deps.now ?? (() => new Date());
  const send = deps.sendEvent ?? ((event: RecoEvent) => deps.client.sendRecoEvent(event));

  const assistMode = deps.assistMode ?? 'one_click';
  const threshold = deps.autoThreshold ?? DEFAULT_AUTO_THRESHOLD;

  // Applique le modèle et, en cas d'échec des sélecteurs, émet UN signal de
  // santé (`selector_broken`) — repli silencieux, jamais bloquant (règle 3).
  const applyAndReport = async (model: string): Promise<boolean> => {
    if (!deps.applyModel) return false; // mode guide : aucun contact page
    try {
      const ok = await deps.applyModel(model, isCurrent);
      if (!ok) deps.client.sendHealthSignal?.('selector_broken');
      return ok;
    } catch {
      // applyModel ne devrait JAMAIS rejeter (l'impl réelle renvoie false), mais
      // ceinture+bretelles : aucun rejet non géré, jamais bloquant (règle 3).
      deps.client.sendHealthSignal?.('selector_broken');
      return false;
    }
  };

  // Décision de bascule AUTO : mode auto + confiance ≥ seuil + modèle courant
  // LISIBLE (pour pouvoir Annuler) + il diffère de la reco. Sinon → one_click.
  let previousModel: string | null = null;
  let autoSwitch = false;
  if (
    assistMode === 'auto' &&
    deps.applyModel &&
    deps.readCurrentModel &&
    reco.confidence >= threshold
  ) {
    previousModel = deps.readCurrentModel();
    // Modèle courant illisible = sélecteur cassé → signal de santé + repli
    // one_click (on ne saurait pas restaurer, donc pas de bascule auto).
    if (previousModel === null) deps.client.sendHealthSignal?.('selector_broken');
    autoSwitch = previousModel !== null && previousModel !== reco.recommended_model;
  }
  // Auto mais DÉJÀ sur le modèle recommandé : rien à basculer — on l'indique
  // plutôt que d'afficher « Utiliser {modèle} » pour un modèle déjà sélectionné.
  // Choix ASSUMÉ : aucun reco_event n'est émis pour cet état (ni bascule, ni
  // dérogation, ni clic) — `recos_shown` le compte, l'issue est neutre. Ne pas
  // émettre un followed:true fantôme pour une reco qui n'a rien déclenché.
  const autoAlreadyCurrent =
    assistMode === 'auto' && previousModel !== null && previousModel === reco.recommended_model;

  // ACCEPTATION DIFFÉRÉE (garantie : UN SEUL événement net par reco). En auto,
  // la bascule est faite immédiatement mais l'issue reste EN ATTENTE tant
  // qu'Annuler est offert. On committe :
  //   - REJET (followed=false, overridden_to=précédent) au clic Annuler ;
  //   - ACCEPTATION (followed=true) quand l'utilisateur écarte le panneau sans
  //     annuler (fermeture, Échap, changement de conversation, flux suivant).
  // `outcomeCommitted` garantit l'exclusivité ; `switchInFlight` sérialise la
  // restauration APRÈS la bascule (jamais deux sélections concurrentes → modèle
  // final déterministe).
  let outcomeCommitted = false;
  let switchInFlight: Promise<boolean> | null = null;

  const commitAccept = () => {
    if (outcomeCommitted) return;
    outcomeCommitted = true;
    if (pendingAutoAccept === commitAccept) pendingAutoAccept = null;
    deps.memory.noteFollowed();
    send(buildRecoEvent(reco.reco_id, true, null, now));
  };
  const commitReject = () => {
    if (outcomeCommitted || previousModel === null) return;
    outcomeCommitted = true;
    if (pendingAutoAccept === commitAccept) pendingAutoAccept = null;
    deps.memory.noteDerogation(reco.recommended_model, previousModel);
    send(buildRecoEvent(reco.reco_id, false, previousModel, now));
    const restore = () => applyAndReport(previousModel!);
    void (switchInFlight ? switchInFlight.then(restore, restore) : restore());
  };

  const renderOptions = (switched: boolean) => ({
    modelsVisible: deps.config?.models_visible ?? [],
    messages: deps.messages,
    mode: deps.config?.mode,
    assistMode,
    autoSwitched: switched,
    alreadyOnModel: autoAlreadyCurrent,
    callbacks: {
      onFollow: () => {
        deps.memory.noteFollowed();
        send(buildRecoEvent(reco.reco_id, true, null, now));
        // Action déclenchée par le clic de l'utilisateur ; échec silencieux.
        void applyAndReport(reco.recommended_model);
      },
      onOverride: (model: string) => {
        deps.memory.noteDerogation(reco.recommended_model, model);
        send(buildRecoEvent(reco.reco_id, false, model, now));
        void applyAndReport(model);
      },
      onCancel: commitReject,
      // Écarter le panneau « basculé » SANS annuler = accepter la bascule auto.
      // On committe le PENDING (posé seulement après une bascule RÉUSSIE) : si
      // la bascule est encore en vol ou a échoué, rien n'est committé (l'issue
      // reflète le succès mécanique, pas la seule fermeture).
      onDismiss: switched ? flushPendingAutoAccept : undefined,
    },
  });

  // Un nouveau panneau remplace le précédent : committe l'acceptation d'une
  // bascule auto antérieure encore en attente (l'utilisateur est passé à autre).
  flushPendingAutoAccept();

  // UI OPTIMISTE : en auto, on montre immédiatement l'état « basculé » (< 300 ms
  // perçu) ; la bascule réelle suit et corrige l'UI si elle échoue.
  renderPanel(reco, renderOptions(autoSwitch));

  if (autoSwitch) {
    switchInFlight = applyAndReport(reco.recommended_model);
    const ok = await switchInFlight;
    // Issue déjà tranchée (Annuler en vol), ou conversation quittée pendant la
    // bascule : on ne committe rien. Le drop d'acceptation sur une nav en cours
    // de bascule est un choix ASSUMÉ (sens sûr : sous-comptage, jamais un
    // followed=true sur un fil que l'utilisateur a quitté).
    if (outcomeCommitted || !isCurrent()) return reco;
    if (ok) {
      if (isLatest() && isPanelPresent()) {
        // Panneau encore visible et flux le plus récent : l'acceptation reste EN
        // ATTENTE (Annuler encore possible) — committée à la fermeture/nav ou au
        // flux suivant.
        pendingAutoAccept = commitAccept;
      } else {
        // Supplanté par un flux plus récent, OU panneau déjà écarté PENDANT la
        // bascule (fermeture/badge/nav) : la bascule a réussi → on accepte
        // maintenant (sinon acceptation orpheline / armée sur un panneau absent).
        commitAccept();
      }
    } else if (isLatest() && isPanelPresent()) {
      // Repli one_click — uniquement si ce flux est encore le panneau affiché
      // (ni supplanté par un flux plus récent, ni retiré par une nav SPA).
      renderPanel(reco, renderOptions(false));
    }
  }

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
    onConversationChange: () => {
      // Quitter un fil = accepter une éventuelle bascule auto en attente, puis
      // retirer le panneau obsolète (anti-fuite inter-conversations).
      flushPendingAutoAccept();
      removePanel();
    },
  });

  // Mode d'assistance EFFECTIF (RFC-0003) : opt-in local ∧ politique org.
  const assistMode = resolveAssistMode(config, settings.autoApplyModel);
  // guide ⇒ aucun contact page (applyModel absent, lecture seule stricte).
  // auto/one_click ⇒ applyModel présent (bascule encadrée, résultat vérifié).
  const applyModel =
    assistMode === 'guide'
      ? undefined
      : (model: string, isCurrent?: () => boolean) => applyModelInPage(model, { isCurrent });
  // La lecture du modèle courant n'est utile qu'à la bascule auto (pour Annuler).
  const readCurrentModel = assistMode === 'auto' ? readCurrentModelFromPage : undefined;
  const autoThreshold = config?.auto_confidence_threshold ?? DEFAULT_AUTO_THRESHOLD;

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
    readCurrentModel,
    assistMode,
    autoThreshold,
    sendEvent,
  };
  observeInputArea(
    baseDeps,
    () => controller.currentMemory(),
    controller.stop,
    () => controller.currentKey(),
  );
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
  currentKey: () => string = () => '',
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
    // Fige la conversation d'origine : le flux ne s'affichera/basculera QUE si
    // ce fil est encore actif à l'arrivée de la reco (anti-fuite SPA).
    const flowKey = currentKey();
    const isCurrent = () => currentKey() === flowKey;
    void runRecommendationFlow(text, { ...baseDeps, memory, isCurrent });
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
    // Badge ancré sur la barre de saisie (overlay — règle 2). Titre honnête
    // selon le mode ; clic = écarter (committe une acceptation auto en attente).
    renderBadge(baseDeps.messages, input, {
      assistMode: baseDeps.assistMode,
      onDismiss: flushPendingAutoAccept,
    });
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
      flushPendingAutoAccept(); // committe une acceptation auto en attente
      removePanel();
      removeBadge();
    },
    { once: true },
  );
  ensureAttached();
}
