/**
 * Client backend V0 — façade commune mock/api, JAMAIS bloquante (règle 3).
 *
 * - `withTimeout` : toute recommandation est bornée à 400 ms ; au-delà, `null`
 *   silencieux — l'appelant n'affiche rien, aucun toast, aucun crash.
 * - `createDebouncer` : 600 ms après la pause de saisie.
 * - Télémétrie fire-and-forget avec file de retry légère (3 tentatives max,
 *   puis abandon silencieux).
 * - Config distante : lue au démarrage, cachée, kill-switch respecté par
 *   l'appelant (`enabled === false` ⇒ extension inerte).
 *
 * Mode `api` et contrat : le backend v1.0 (contracts/openapi.yaml) ne connaît
 * pas encore le bloc `signals.conversation` — la RFC v1.1
 * (docs/rfc/RFC-0001-signals-conversation.md) propose son adoption. En
 * attendant, ce client mappe les signaux vers les `features` v1.0 : la
 * mémoire de conversation reste LOCALE et le mock (défaut V0) consomme, lui,
 * le bloc complet. Aucun champ hors contrat ne part vers l'API réelle.
 */
import {
  getExtensionConfig,
  postRecoEvent,
  postRecommend,
  type ApiSettings,
  type ExtensionConfig,
  type Features,
  type KeywordFlag,
  type RecoEvent,
} from './api';
import { MockClient, type RecoClientV0, type RecoV0 } from './mockClient';
import type { Signals } from './signals';
import type { StoredSettings } from './settings';

/** Timeout dur de la recommandation (règle 3 : jamais bloquant). */
export const RECOMMEND_TIMEOUT_MS = 400;

/** Pause de saisie avant appel (contrat UX de la V0). */
export const DEBOUNCE_MS = 600;

/** Tentatives de télémétrie (1 envoi + 2 retries), puis abandon silencieux. */
export const TELEMETRY_MAX_ATTEMPTS = 3;
const TELEMETRY_RETRY_DELAYS_MS = [1000, 5000];

// ---------------------------------------------------------------------------
// Garde-fous génériques.
// ---------------------------------------------------------------------------

/**
 * Borne une promesse : passé `ms`, retourne `null` (et l'échec — rejet —
 * devient aussi `null`). C'est LE garde-fou « jamais bloquant ».
 */
export async function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T | null> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<null>((resolve) => {
    timer = setTimeout(() => resolve(null), ms);
  });
  try {
    return await Promise.race([promise, timeout]);
  } catch {
    return null; // échec ⇒ silence (règle 3)
  } finally {
    clearTimeout(timer);
  }
}

/**
 * Throttle « trailing » : au plus UN appel par fenêtre de `ms` — garde-fou
 * perf pour l'observation des mutations DOM (boucle 5).
 */
export function createThrottle(callback: () => void, ms: number): () => void {
  let scheduled = false;
  return () => {
    if (scheduled) return;
    scheduled = true;
    setTimeout(() => {
      scheduled = false;
      callback();
    }, ms);
  };
}

/** Débounceur simple : `schedule()` réarme, `cancel()` annule. */
export function createDebouncer(
  callback: () => void,
  ms: number = DEBOUNCE_MS,
): { schedule: () => void; cancel: () => void } {
  let timer: ReturnType<typeof setTimeout> | undefined;
  return {
    schedule() {
      clearTimeout(timer);
      timer = setTimeout(callback, ms);
    },
    cancel() {
      clearTimeout(timer);
    },
  };
}

// ---------------------------------------------------------------------------
// Mode API — mapping signaux V0 → features v1.0 (aucun champ hors contrat).
// ---------------------------------------------------------------------------

/** Drapeaux v1.0 (liste fermée du contrat figé). */
const V1_FLAGS: readonly KeywordFlag[] = ['contrat', 'analyse', 'code', 'resume', 'traduction'];

/**
 * Signaux V0 → `Features` v1.0. Le bloc `conversation` n'est PAS transmis
 * (contrat figé — RFC v1.1 en cours) ; le drapeau `demonstration` (V0) est
 * retiré car hors liste fermée v1.0.
 */
export function signalsToV1Features(signals: Signals): Features {
  return {
    char_len: signals.prompt.char_len,
    token_est: signals.prompt.token_est,
    lang: signals.prompt.lang,
    has_code: signals.prompt.has_code,
    has_attachment_hint: false,
    keyword_flags: signals.prompt.keyword_flags.filter((flag): flag is KeywordFlag =>
      (V1_FLAGS as readonly string[]).includes(flag),
    ),
  };
}

class ApiClientV0 implements RecoClientV0 {
  constructor(private readonly settings: ApiSettings) {}

  async recommend(signals: Signals): Promise<RecoV0 | null> {
    const response = await postRecommend(
      this.settings,
      signalsToV1Features(signals),
      RECOMMEND_TIMEOUT_MS,
    );
    if (!response) return null;
    return {
      reco_id: response.reco_id,
      recommended_model: response.recommended_model,
      confidence: response.confidence,
      rule: response.rule,
      impact_estimate: response.impact_estimate,
      budget: response.budget,
      // Absent du contrat v1.0 — proposé par la RFC v1.1. Jamais inventé.
      suggest_new_conversation: false,
    };
  }

  sendRecoEvent(event: RecoEvent): void {
    sendWithRetry(() => postRecoEvent(this.settings, event));
  }

  deliverRecoEvent(event: RecoEvent): Promise<boolean> {
    // Un seul essai borné : la file de télémétrie gère le retry persistant.
    return postRecoEvent(this.settings, event, RECOMMEND_TIMEOUT_MS);
  }

  async getConfig(): Promise<ExtensionConfig | null> {
    return getExtensionConfig(this.settings);
  }
}

/**
 * Fire-and-forget avec retry léger : 3 tentatives au total (délais 1 s puis
 * 5 s), puis abandon SILENCIEUX — la télémétrie ne gêne jamais l'utilisateur.
 * (Exporté pour le test dédié de la boucle 2.)
 */
export function sendWithRetry(attempt: () => Promise<boolean>, attemptIndex = 0): void {
  void attempt()
    .catch(() => false)
    .then((delivered) => {
      if (delivered || attemptIndex + 1 >= TELEMETRY_MAX_ATTEMPTS) return;
      const delay = TELEMETRY_RETRY_DELAYS_MS[attemptIndex] ?? 5000;
      setTimeout(() => sendWithRetry(attempt, attemptIndex + 1), delay);
    });
}

// ---------------------------------------------------------------------------
// Fabrique + cache de configuration (kill-switch).
// ---------------------------------------------------------------------------

/** Fabrique le client selon les réglages ('mock' par défaut en V0). */
export function createClient(settings: StoredSettings): RecoClientV0 {
  if (settings.backend === 'api' && settings.apiUrl && settings.orgId && settings.token) {
    return new ApiClientV0({
      apiUrl: settings.apiUrl,
      orgId: settings.orgId,
      token: settings.token,
    });
  }
  return new MockClient();
}

/** Durée de vie du cache de config (rafraîchi au-delà, jamais bloquant). */
export const CONFIG_CACHE_TTL_MS = 5 * 60 * 1000;

export interface CachedConfig {
  get(): Promise<ExtensionConfig | null>;
  invalidate(): void;
}

/**
 * Cache de configuration distante : première lecture au démarrage, puis
 * réutilisation pendant CONFIG_CACHE_TTL_MS. Un échec ne remplace jamais une
 * config valide déjà connue (dégradation silencieuse).
 */
export function createConfigCache(
  client: RecoClientV0,
  now: () => number = Date.now,
): CachedConfig {
  let cached: ExtensionConfig | null = null;
  let fetchedAt = -Infinity;
  return {
    async get() {
      if (cached && now() - fetchedAt < CONFIG_CACHE_TTL_MS) return cached;
      const fresh = await withTimeout(client.getConfig(), RECOMMEND_TIMEOUT_MS);
      if (fresh) {
        cached = fresh;
        fetchedAt = now();
      }
      return cached;
    },
    invalidate() {
      cached = null;
      fetchedAt = -Infinity;
    },
  };
}

export type { RecoClientV0, RecoV0 };
