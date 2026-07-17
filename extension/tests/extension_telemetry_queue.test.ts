/**
 * Boucle 7 — télémétrie industrialisée : file persistante, retry exponentiel,
 * schéma strict, opt-in/kill-switch, compteurs. Storage injecté (Map).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ExtensionConfig, RecoEvent } from '../src/api';
import {
  isStrictRecoEvent,
  telemetryAllowed,
  TelemetryQueue,
  TELEMETRY_MAX_ATTEMPTS,
  type StorageArea,
} from '../src/telemetryQueue';

/** Storage factice en mémoire. */
function fakeStorage(): StorageArea {
  const map = new Map<string, unknown>();
  return {
    get: (key: string) => Promise.resolve({ [key]: map.get(key) }),
    set: (items: Record<string, unknown>) => {
      for (const [k, v] of Object.entries(items)) map.set(k, structuredClone(v));
      return Promise.resolve();
    },
  };
}

const EVENT: RecoEvent = {
  reco_id: 'mock-000001',
  followed: true,
  overridden_to: null,
  ts: '2026-07-17T10:00:00.000Z',
};

beforeEach(() => {
  vi.restoreAllMocks();
});

describe('isStrictRecoEvent — garde-fou schéma', () => {
  it('accepte exactement les 4 champs du contrat', () => {
    expect(isStrictRecoEvent(EVENT)).toBe(true);
  });
  it('rejette tout champ en trop (ex. prompt_text) ou manquant', () => {
    expect(isStrictRecoEvent({ ...EVENT, prompt_text: 'fuite' })).toBe(false);
    expect(isStrictRecoEvent({ reco_id: 'x', followed: true })).toBe(false);
    expect(isStrictRecoEvent({ ...EVENT, followed: 'oui' })).toBe(false);
    expect(isStrictRecoEvent(null)).toBe(false);
  });
});

describe('telemetryAllowed — kill-switch et opt-out org', () => {
  const base: ExtensionConfig = {
    enabled: true,
    mode: 'equilibre',
    models_visible: [],
    send_prompt_text: false,
    messages: { fr: {} },
    min_extension_version: '1.0.0',
  };
  it('autorisée par défaut ; interdite si kill-switch', () => {
    expect(telemetryAllowed(base)).toBe(true);
    expect(telemetryAllowed({ ...base, enabled: false })).toBe(false);
    expect(telemetryAllowed(null)).toBe(true);
  });
  it('interdite si l’org pose telemetry_enabled=false', () => {
    expect(telemetryAllowed({ ...base, telemetry_enabled: false } as ExtensionConfig)).toBe(false);
  });
});

describe('TelemetryQueue — file persistante', () => {
  it('enqueue livre et compte les succès', async () => {
    const storage = fakeStorage();
    const deliver = vi.fn().mockResolvedValue(true);
    const queue = new TelemetryQueue(deliver, { storage, now: () => 0 });
    await queue.enqueue(EVENT);
    expect(deliver).toHaveBeenCalledWith(EVENT);
    expect(await queue.pending()).toBe(0);
    expect(await queue.sentCount()).toBe(1);
  });

  it('événement non conforme : jamais mis en file, jamais livré', async () => {
    const storage = fakeStorage();
    const deliver = vi.fn().mockResolvedValue(true);
    const queue = new TelemetryQueue(deliver, { storage, now: () => 0 });
    await queue.enqueue({ ...EVENT, prompt_text: 'SECRET' } as RecoEvent);
    expect(deliver).not.toHaveBeenCalled();
    expect(await queue.pending()).toBe(0);
  });

  it('échec : reste en file avec backoff, réessaie plus tard', async () => {
    const storage = fakeStorage();
    const deliver = vi.fn().mockResolvedValue(false);
    let clock = 0;
    const queue = new TelemetryQueue(deliver, { storage, now: () => clock });

    await queue.enqueue(EVENT); // tentative 1 échoue
    expect(await queue.pending()).toBe(1);
    expect(deliver).toHaveBeenCalledTimes(1);

    // Pas encore dû (backoff) : flush sans effet.
    await queue.flush();
    expect(deliver).toHaveBeenCalledTimes(1);

    // Après le backoff : nouvelle tentative.
    clock = 5000;
    await queue.flush();
    expect(deliver).toHaveBeenCalledTimes(2);
  });

  it('abandon silencieux après TELEMETRY_MAX_ATTEMPTS', async () => {
    const storage = fakeStorage();
    const deliver = vi.fn().mockResolvedValue(false);
    let clock = 0;
    const queue = new TelemetryQueue(deliver, { storage, now: () => clock });
    await queue.enqueue(EVENT);
    for (let i = 0; i < TELEMETRY_MAX_ATTEMPTS + 2; i += 1) {
      clock += 20000;
      await queue.flush();
    }
    expect(deliver).toHaveBeenCalledTimes(TELEMETRY_MAX_ATTEMPTS);
    expect(await queue.pending()).toBe(0); // abandonné, file vidée
    expect(await queue.sentCount()).toBe(0);
  });

  it('persistance : reprise par une nouvelle instance sur le même storage', async () => {
    const storage = fakeStorage();
    // 1re instance : échec, événement laissé en file.
    const q1 = new TelemetryQueue(() => Promise.resolve(false), { storage, now: () => 0 });
    await q1.enqueue(EVENT);
    expect(await q1.pending()).toBe(1);

    // 2e instance (nouveau chargement de page) : livraison réussit à la reprise.
    const deliver2 = vi.fn().mockResolvedValue(true);
    const q2 = new TelemetryQueue(deliver2, { storage, now: () => 5000 });
    await q2.flush();
    expect(deliver2).toHaveBeenCalledWith(EVENT);
    expect(await q2.pending()).toBe(0);
    expect(await q2.sentCount()).toBe(1);
  });
});
