/**
 * Client typé de l'API Sobrio — 3 endpoints du contrat `contracts/openapi.yaml` (v1.0).
 *
 * Règles encodées ici :
 * - Règle n°1 : `prompt_text` n'est JAMAIS envoyé en v0 (champ omis du corps).
 *   TODO(LotA) : ne l'envoyer que si `config.send_prompt_text === true` ET que la
 *   politique de l'organisation l'autorise explicitement.
 * - Règle n°2 : aucun secret dans le bundle — URL API, org_id et token sont lus
 *   depuis `browser.storage.local` (renseignés via le popup).
 * - Dégradation silencieuse : tout échec réseau/timeout retourne `null`/`false`,
 *   ne throw jamais vers l'appelant, ne logge jamais de contenu.
 */
import { browser } from 'wxt/browser';

// ---------------------------------------------------------------------------
// Types fidèles à contracts/openapi.yaml (v1.0) — ne pas modifier sans RFC.
// ---------------------------------------------------------------------------

export type Lang = 'fr' | 'en' | 'other';

/** Liste FERMÉE du contrat (schéma Features.keyword_flags). */
export type KeywordFlag = 'contrat' | 'analyse' | 'code' | 'resume' | 'traduction';

/** Caractéristiques calculées localement — aucun contenu textuel. */
export interface Features {
  char_len: number;
  token_est: number;
  lang: Lang;
  has_code: boolean;
  has_attachment_hint: boolean;
  keyword_flags: KeywordFlag[];
}

export interface RecommendRequest {
  org_id: string;
  surface: 'claude_web';
  features: Features;
  /**
   * OPTIONNEL, v1 uniquement — JAMAIS envoyé en v0 (champ omis).
   * TODO(LotA) : opt-in explicite via config org (`send_prompt_text`).
   */
  prompt_text?: string | null;
}

export interface Alternative {
  model: string;
  delta_cost_eur_per_call_min: number;
  delta_cost_eur_per_call_max: number;
}

/** Fourchettes uniquement — jamais de valeur unique (règle n°3). */
export interface ImpactEstimate {
  energy_wh_min: number;
  energy_wh_max: number;
  cost_eur_min: number;
  cost_eur_max: number;
}

export interface Budget {
  team_label: string;
  pct_used: number;
}

export interface RecommendResponse {
  reco_id: string;
  recommended_model: string;
  confidence: number;
  rule: string;
  alternatives: Alternative[];
  impact_estimate: ImpactEstimate;
  budget: Budget | null;
}

/** Schéma STRICT côté API : tout champ supplémentaire ⇒ 422 (anti-fuite). */
export interface RecoEvent {
  reco_id: string;
  followed: boolean;
  overridden_to: string | null;
  ts: string; // date-time ISO 8601
}

export type ExtensionMode = 'eco' | 'equilibre' | 'qualite';

export interface ExtensionConfig {
  enabled: boolean; // kill-switch à distance
  mode: ExtensionMode;
  models_visible: string[];
  send_prompt_text: boolean;
  messages: { fr: Record<string, unknown> };
  min_extension_version: string;
}

// ---------------------------------------------------------------------------
// Réglages locaux (browser.storage.local) — jamais en dur dans le bundle.
// ---------------------------------------------------------------------------

export interface ApiSettings {
  apiUrl: string;
  orgId: string;
  token: string;
}

const SETTINGS_KEY = 'sobrio_settings';

/** Timeout court : la reco ne doit JAMAIS ralentir l'utilisateur (400 ms). */
export const DEFAULT_TIMEOUT_MS = 400;

/** Lit les réglages depuis storage.local ; `null` si absents/incomplets. */
export async function loadSettings(): Promise<ApiSettings | null> {
  try {
    const stored = await browser.storage.local.get(SETTINGS_KEY);
    const raw = stored[SETTINGS_KEY] as Partial<ApiSettings> | undefined;
    if (!raw || !raw.apiUrl || !raw.orgId || !raw.token) return null;
    return { apiUrl: raw.apiUrl, orgId: raw.orgId, token: raw.token };
  } catch {
    return null; // dégradation silencieuse
  }
}

/** Écrit les réglages dans storage.local (utilisé par le popup). */
export async function saveSettings(settings: ApiSettings): Promise<void> {
  await browser.storage.local.set({ [SETTINGS_KEY]: settings });
}

// ---------------------------------------------------------------------------
// Requêtes — AbortController + timeout, Authorization: Bearer, échec ⇒ null.
// ---------------------------------------------------------------------------

async function request(
  settings: ApiSettings,
  path: string,
  init: RequestInit,
  timeoutMs: number,
): Promise<Response | null> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const base = settings.apiUrl.replace(/\/+$/, '');
    const response = await fetch(`${base}${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${settings.token}`,
        ...init.headers,
      },
      signal: controller.signal,
    });
    return response.ok ? response : null;
  } catch {
    // Échec réseau, CORS ou timeout : dégradation silencieuse, rien n'est loggé.
    return null;
  } finally {
    clearTimeout(timer);
  }
}

/**
 * POST /v1/recommend — envoie UNIQUEMENT les features (jamais le texte).
 * Retourne `null` en cas d'échec/timeout : l'appelant n'affiche alors rien.
 */
export async function postRecommend(
  settings: ApiSettings,
  features: Features,
  timeoutMs: number = DEFAULT_TIMEOUT_MS,
): Promise<RecommendResponse | null> {
  const body: RecommendRequest = {
    org_id: settings.orgId,
    surface: 'claude_web',
    features,
    // prompt_text : volontairement OMIS (v0). TODO(LotA) : opt-in org.
  };
  const response = await request(
    settings,
    '/v1/recommend',
    { method: 'POST', body: JSON.stringify(body) },
    timeoutMs,
  );
  if (!response) return null;
  try {
    return (await response.json()) as RecommendResponse;
  } catch {
    return null;
  }
}

/**
 * POST /v1/telemetry/reco_event — suite donnée à une recommandation.
 * Corps STRICT (contrat) : exactement reco_id/followed/overridden_to/ts.
 */
export async function postRecoEvent(
  settings: ApiSettings,
  event: RecoEvent,
  timeoutMs: number = DEFAULT_TIMEOUT_MS,
): Promise<boolean> {
  const response = await request(
    settings,
    '/v1/telemetry/reco_event',
    { method: 'POST', body: JSON.stringify(event) },
    timeoutMs,
  );
  return response !== null;
}

/**
 * GET /v1/extension/config?org=… — configuration distante (kill-switch inclus).
 */
export async function getExtensionConfig(
  settings: ApiSettings,
  timeoutMs: number = DEFAULT_TIMEOUT_MS,
): Promise<ExtensionConfig | null> {
  const response = await request(
    settings,
    `/v1/extension/config?org=${encodeURIComponent(settings.orgId)}`,
    { method: 'GET' },
    timeoutMs,
  );
  if (!response) return null;
  try {
    return (await response.json()) as ExtensionConfig;
  } catch {
    return null;
  }
}
