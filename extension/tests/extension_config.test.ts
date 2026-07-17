/**
 * Boucle 6 — config distante industrialisée : cache persistant TTL 1 h,
 * kill-switch, version obsolète, hors-ligne (dernier état connu), premier
 * lancement sans réseau (inertie propre).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

// Storage d'extension factice, en mémoire.
const memoryStore = new Map<string, unknown>();
vi.mock('wxt/browser', () => ({
  browser: {
    storage: {
      local: {
        get: (key: string) => Promise.resolve({ [key]: memoryStore.get(key) }),
        set: (items: Record<string, unknown>) => {
          for (const [k, v] of Object.entries(items)) memoryStore.set(k, v);
          return Promise.resolve();
        },
      },
    },
    runtime: { getManifest: () => ({ version: '1.0.0' }) },
  },
}));

import type { ExtensionConfig } from '../src/api';
import {
  CONFIG_TTL_MS,
  compareVersions,
  isVersionSupported,
  localVersion,
  resolveConfig,
  type ConfigSource,
} from '../src/remoteConfig';

const CONFIG: ExtensionConfig = {
  enabled: true,
  mode: 'equilibre',
  models_visible: ['claude-haiku-4-5', 'claude-sonnet-5', 'claude-opus-4-8'],
  send_prompt_text: false,
  messages: { fr: {} },
  min_extension_version: '1.0.0',
};

function source(config: ExtensionConfig | null): ConfigSource & { calls: number } {
  return {
    calls: 0,
    async getConfig() {
      this.calls += 1;
      return config;
    },
  };
}

beforeEach(() => {
  memoryStore.clear();
});

describe('resolveConfig — cache persistant + rafraîchissement', () => {
  it('premier appel : va chercher la config et la persiste', async () => {
    const src = source(CONFIG);
    const r = await resolveConfig(src, { now: () => 1000 });
    expect(r.config?.mode).toBe('equilibre');
    expect(r.fromCache).toBe(false);
    expect(src.calls).toBe(1);
    // Persistée : un second appel dans le TTL ne re-sollicite pas la source.
    const r2 = await resolveConfig(src, { now: () => 1000 + CONFIG_TTL_MS - 1 });
    expect(r2.fromCache).toBe(true);
    expect(src.calls).toBe(1);
  });

  it('au-delà du TTL : rafraîchissement silencieux', async () => {
    const src = source(CONFIG);
    await resolveConfig(src, { now: () => 0 });
    await resolveConfig(src, { now: () => CONFIG_TTL_MS + 1 });
    expect(src.calls).toBe(2);
  });
});

describe('resolveConfig — hors-ligne / dernier état connu', () => {
  it('réseau muet après un état connu : sert la config périmée (stale)', async () => {
    await resolveConfig(source(CONFIG), { now: () => 0 }); // amorce le cache
    const r = await resolveConfig(source(null), { now: () => CONFIG_TTL_MS + 10 });
    expect(r.config?.mode).toBe('equilibre');
    expect(r.stale).toBe(true);
  });

  it('premier lancement sans réseau : config null, inertie propre', async () => {
    const r = await resolveConfig(source(null), { now: () => 0 });
    expect(r.config).toBeNull();
    expect(r.stale).toBe(false);
  });
});

describe('kill-switch', () => {
  it('enabled=false est restitué tel quel (le content s’auto-désactive)', async () => {
    const r = await resolveConfig(source({ ...CONFIG, enabled: false }), { now: () => 0 });
    expect(r.config?.enabled).toBe(false);
  });
});

describe('contrôle de version', () => {
  it('compareVersions ordonne correctement', () => {
    expect(compareVersions('1.0.0', '1.0.0')).toBe(0);
    expect(compareVersions('1.0.0', '1.2.0')).toBe(-1);
    expect(compareVersions('2.0.0', '1.9.9')).toBe(1);
    expect(compareVersions('1.0', '1.0.1')).toBe(-1);
  });

  it('isVersionSupported : local ≥ min, min absent ⇒ toléré', () => {
    expect(isVersionSupported('1.0.0', '1.0.0')).toBe(true);
    expect(isVersionSupported('1.0.0', '1.1.0')).toBe(false);
    expect(isVersionSupported('1.2.0', '1.1.0')).toBe(true);
    expect(isVersionSupported('0.9.0', undefined)).toBe(true);
  });

  it('localVersion lit le manifest (1.0.0)', () => {
    expect(localVersion()).toBe('1.0.0');
  });
});
