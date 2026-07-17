/**
 * Config distante industrialisée — chargement au démarrage, cache TTL 1 h
 * PERSISTANT (chrome.storage : le dernier état connu survit aux rechargements
 * et au hors-ligne), rafraîchissement silencieux, kill-switch, et contrôle de
 * `min_extension_version`.
 *
 * RÈGLE 3 : jamais bloquant. Un échec réseau ne remplace jamais un état connu
 * et ne lève jamais d'erreur — on retombe sur le dernier état, ou sur `null`
 * (extension inerte mais silencieuse) au tout premier lancement hors-ligne.
 */
import { browser } from 'wxt/browser';

import type { ExtensionConfig } from './api';
import { RECOMMEND_TIMEOUT_MS, withTimeout } from './client';

/** Source de configuration (le client mock ou l'API réelle). */
export interface ConfigSource {
  getConfig(): Promise<ExtensionConfig | null>;
}

/** TTL du cache de configuration : 1 heure. */
export const CONFIG_TTL_MS = 60 * 60 * 1000;

/** Clé de persistance du dernier état connu. */
export const CONFIG_CACHE_KEY = 'sobrio_config_cache';

interface CachedConfigEntry {
  config: ExtensionConfig;
  fetchedAt: number;
}

/** Lit le dernier état connu depuis le storage (ou `null`). */
export async function readCachedConfig(): Promise<CachedConfigEntry | null> {
  try {
    const stored = await browser.storage.local.get(CONFIG_CACHE_KEY);
    const entry = stored[CONFIG_CACHE_KEY] as CachedConfigEntry | undefined;
    if (entry && entry.config && typeof entry.fetchedAt === 'number') return entry;
  } catch {
    // Dégradation silencieuse.
  }
  return null;
}

/** Persiste le dernier état connu. */
export async function writeCachedConfig(config: ExtensionConfig, at: number): Promise<void> {
  try {
    await browser.storage.local.set({ [CONFIG_CACHE_KEY]: { config, fetchedAt: at } });
  } catch {
    // Dégradation silencieuse.
  }
}

export interface ResolvedConfig {
  /** Config effective (ou `null` si aucune n'a jamais pu être obtenue). */
  config: ExtensionConfig | null;
  /** Vrai si la valeur provient du cache (réseau non re-sollicité ou muet). */
  fromCache: boolean;
  /** Vrai si la valeur est périmée (servie faute de réseau). */
  stale: boolean;
}

export interface ResolveConfigOptions {
  now?: () => number;
  ttlMs?: number;
  timeoutMs?: number;
}

/**
 * Résout la configuration : cache frais (< TTL) servi tel quel ; sinon
 * rafraîchissement silencieux via la source (client mock ou API) ; en cas
 * d'échec/muet, dernier état connu (périmé) ou `null`. Ne throw jamais.
 */
export async function resolveConfig(
  source: ConfigSource,
  options: ResolveConfigOptions = {},
): Promise<ResolvedConfig> {
  const now = options.now ?? Date.now;
  const ttl = options.ttlMs ?? CONFIG_TTL_MS;
  const timeout = options.timeoutMs ?? RECOMMEND_TIMEOUT_MS;

  const cached = await readCachedConfig();
  if (cached && now() - cached.fetchedAt < ttl) {
    return { config: cached.config, fromCache: true, stale: false };
  }

  const fresh = await withTimeout(source.getConfig(), timeout);
  if (fresh) {
    await writeCachedConfig(fresh, now());
    return { config: fresh, fromCache: false, stale: false };
  }

  // Réseau muet : on garde le dernier état connu (périmé), sinon rien.
  if (cached) return { config: cached.config, fromCache: true, stale: true };
  return { config: null, fromCache: false, stale: false };
}

// ---------------------------------------------------------------------------
// Contrôle de version (min_extension_version).
// ---------------------------------------------------------------------------

/** Compare deux versions « x.y.z » : -1 si a<b, 0 si égal, 1 si a>b. */
export function compareVersions(a: string, b: string): number {
  const pa = a.split('.').map((n) => parseInt(n, 10) || 0);
  const pb = b.split('.').map((n) => parseInt(n, 10) || 0);
  const len = Math.max(pa.length, pb.length);
  for (let i = 0; i < len; i += 1) {
    const x = pa[i] ?? 0;
    const y = pb[i] ?? 0;
    if (x < y) return -1;
    if (x > y) return 1;
  }
  return 0;
}

/** Vrai si la version locale satisfait le minimum requis. */
export function isVersionSupported(local: string, min: string | undefined): boolean {
  if (!min) return true;
  return compareVersions(local, min) >= 0;
}

/** Version locale de l'extension (depuis le manifest), '0.0.0' en repli. */
export function localVersion(): string {
  try {
    return browser.runtime.getManifest().version ?? '0.0.0';
  } catch {
    return '0.0.0';
  }
}
