/**
 * Réglages persistés de l'extension — browser.storage.local UNIQUEMENT
 * (règle 4 : aucun secret dans le bundle ; tout est saisi via le popup).
 *
 * `backend` commute le mode V0 :
 *  - 'mock' (défaut) : mockClient local, tout se démontre sans serveur ;
 *  - 'api'  : API Sobrio réelle (`make dev` du monorepo).
 */
import { browser } from 'wxt/browser';

export type BackendMode = 'mock' | 'api';

export interface StoredSettings {
  backend: BackendMode;
  apiUrl: string;
  orgId: string;
  token: string;
  /**
   * Application AUTOMATIQUE du modèle choisi dans la page hôte (amendement
   * opt-in de la règle 2, décision du 2026-07-16 — voir docs/decisions.md).
   * DÉSACTIVÉ par défaut : sans opt-in explicite de l'utilisateur,
   * l'extension reste en lecture seule. TODO(V1) : gating par politique org
   * (`allow_auto_apply`, proposé dans la RFC-0001).
   */
  autoApplyModel: boolean;
}

export const SETTINGS_KEY = 'sobrio_settings';

const DEFAULTS: StoredSettings = {
  backend: 'mock',
  apiUrl: '',
  orgId: '',
  token: '',
  autoApplyModel: false,
};

/** Lit les réglages (fusionnés avec les défauts) — ne throw jamais. */
export async function loadStoredSettings(): Promise<StoredSettings> {
  try {
    const stored = await browser.storage.local.get(SETTINGS_KEY);
    const raw = (stored[SETTINGS_KEY] ?? {}) as Partial<StoredSettings>;
    return {
      backend: raw.backend === 'api' ? 'api' : 'mock',
      apiUrl: raw.apiUrl ?? '',
      orgId: raw.orgId ?? '',
      token: raw.token ?? '',
      autoApplyModel: raw.autoApplyModel === true, // opt-in strict
    };
  } catch {
    return { ...DEFAULTS }; // dégradation silencieuse
  }
}

/** Écrit les réglages (popup). */
export async function saveStoredSettings(settings: StoredSettings): Promise<void> {
  await browser.storage.local.set({ [SETTINGS_KEY]: settings });
}
