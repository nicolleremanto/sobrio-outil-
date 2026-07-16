/**
 * Boucle 4 — télémétrie STRICTEMENT conforme au contrat + storage des
 * réglages (mock du storage d'extension) + journal de debug sans contenu.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

// Storage d'extension factice, en mémoire — remplace wxt/browser.
const memoryStore = new Map<string, unknown>();
vi.mock('wxt/browser', () => ({
  browser: {
    storage: {
      local: {
        get: (key: string) => Promise.resolve({ [key]: memoryStore.get(key) }),
        set: (items: Record<string, unknown>) => {
          for (const [key, value] of Object.entries(items)) memoryStore.set(key, value);
          return Promise.resolve();
        },
      },
    },
    runtime: { getManifest: () => ({ version: '0.1.0' }) },
  },
}));

import { buildRecoEvent } from '../src/content-main';
import { debugLog, setDebugLogEnabled } from '../src/debugLog';
import { loadStoredSettings, saveStoredSettings } from '../src/settings';

beforeEach(() => {
  memoryStore.clear();
});

describe('Télémétrie — schéma STRICT du contrat', () => {
  it('exactement 4 champs : reco_id, followed, overridden_to, ts — rien de plus', () => {
    const event = buildRecoEvent('mock-000001', true, null);
    expect(Object.keys(event).sort()).toEqual(['followed', 'overridden_to', 'reco_id', 'ts']);
  });

  it('horodatage ISO 8601 (UTC), dérogation portée par overridden_to', () => {
    const event = buildRecoEvent(
      'mock-000002',
      false,
      'opus-4-8',
      () => new Date('2026-07-16T12:34:56.789Z'),
    );
    expect(event.ts).toBe('2026-07-16T12:34:56.789Z');
    expect(event.followed).toBe(false);
    expect(event.overridden_to).toBe('opus-4-8');
  });

  it("aucun champ texte libre : le JSON de l'événement ne contient que le contrat", () => {
    const serialized = JSON.stringify(buildRecoEvent('mock-000003', true, null));
    const parsed = JSON.parse(serialized) as Record<string, unknown>;
    for (const value of Object.values(parsed)) {
      if (typeof value === 'string') expect(value.length).toBeLessThanOrEqual(24);
    }
  });
});

describe('Storage des réglages (règle 4 : rien dans le bundle)', () => {
  it('aller-retour save/load, backend par défaut mock', async () => {
    expect((await loadStoredSettings()).backend).toBe('mock');
    await saveStoredSettings({
      backend: 'api',
      apiUrl: 'http://localhost:8010',
      orgId: 'demo',
      token: 'demo-token-not-a-secret',
      autoApplyModel: false,
    });
    const loaded = await loadStoredSettings();
    expect(loaded.backend).toBe('api');
    expect(loaded.apiUrl).toBe('http://localhost:8010');
    expect(loaded.token).toBe('demo-token-not-a-secret');
  });

  it('valeurs corrompues → défauts sûrs (jamais de throw)', async () => {
    memoryStore.set('sobrio_settings', { backend: 'n-importe-quoi' });
    const loaded = await loadStoredSettings();
    expect(loaded.backend).toBe('mock');
    expect(loaded.apiUrl).toBe('');
  });
});

describe('Journal de debug — structurellement sans contenu', () => {
  it("n'imprime que nombres et booléens, jamais les strings passées en douce", () => {
    const spy = vi.spyOn(console, 'debug').mockImplementation(() => {});
    setDebugLogEnabled(true);
    // Contournement volontaire du type pour vérifier le filtre runtime.
    debugLog('reco_affichee', {
      token_est: 42,
      followed: true,
      fuite: 'texte du prompt',
    } as never);
    expect(spy).toHaveBeenCalledTimes(1);
    const [, data] = spy.mock.calls[0]!;
    expect(data).toEqual({ token_est: 42, followed: true });
    setDebugLogEnabled(false);
    spy.mockRestore();
  });

  it('désactivé par défaut : aucune sortie console', () => {
    const spy = vi.spyOn(console, 'debug').mockImplementation(() => {});
    debugLog('jamais_vu', { n: 1 });
    expect(spy).not.toHaveBeenCalled();
    spy.mockRestore();
  });
});
