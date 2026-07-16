/**
 * Boucle 2 — client backend : debounce, timeout, panne, retry télémétrie,
 * mapping v1.0, cache de config + kill-switch. Fake timers partout.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { RecoEvent } from '../src/api';
import {
  createConfigCache,
  createDebouncer,
  signalsToV1Features,
  withTimeout,
  CONFIG_CACHE_TTL_MS,
  DEBOUNCE_MS,
  RECOMMEND_TIMEOUT_MS,
} from '../src/client';
import { MockClient } from '../src/mockClient';
import { computePromptSignals, type Signals } from '../src/signals';

beforeEach(() => {
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
});

function makeSignals(text = 'Bonjour, quelle heure est-il ?'): Signals {
  return {
    prompt: computePromptSignals(text),
    conversation: {
      msg_count: 0,
      context_token_est: 0,
      seen_code: false,
      seen_math: false,
      seen_reasoning: false,
      current_model: null,
      recos_shown: 0,
      recos_followed: 0,
      derogations_up: 0,
    },
  };
}

describe('createDebouncer — 600 ms après la pause de saisie', () => {
  it("n'appelle qu'une fois après la dernière frappe", () => {
    const spy = vi.fn();
    const debouncer = createDebouncer(spy);
    debouncer.schedule();
    vi.advanceTimersByTime(DEBOUNCE_MS - 100);
    debouncer.schedule(); // nouvelle frappe : réarme
    vi.advanceTimersByTime(DEBOUNCE_MS - 100);
    expect(spy).not.toHaveBeenCalled();
    vi.advanceTimersByTime(100);
    expect(spy).toHaveBeenCalledTimes(1);
  });

  it('cancel() annule l’appel en attente', () => {
    const spy = vi.fn();
    const debouncer = createDebouncer(spy);
    debouncer.schedule();
    debouncer.cancel();
    vi.advanceTimersByTime(DEBOUNCE_MS * 2);
    expect(spy).not.toHaveBeenCalled();
  });
});

describe('withTimeout — règle 3, jamais bloquant', () => {
  it('retourne null passé le timeout (mock trop lent)', async () => {
    const slow = new MockClient({ latencyMs: 1000 });
    const pending = withTimeout(slow.recommend(makeSignals()), RECOMMEND_TIMEOUT_MS);
    await vi.advanceTimersByTimeAsync(RECOMMEND_TIMEOUT_MS + 1);
    await expect(pending).resolves.toBeNull();
  });

  it('retourne null en cas de panne (rejet) — silencieux, sans throw', async () => {
    const broken = new MockClient({ latencyMs: 0, failure: 'error' });
    const pending = withTimeout(broken.recommend(makeSignals()), RECOMMEND_TIMEOUT_MS);
    await vi.advanceTimersByTimeAsync(1);
    await expect(pending).resolves.toBeNull();
  });

  it('mode panne « mute » : null silencieux', async () => {
    const mute = new MockClient({ latencyMs: 10, failure: 'mute' });
    const pending = withTimeout(mute.recommend(makeSignals()), RECOMMEND_TIMEOUT_MS);
    await vi.advanceTimersByTimeAsync(20);
    await expect(pending).resolves.toBeNull();
  });

  it('laisse passer une réponse plus rapide que le timeout', async () => {
    const quick = new MockClient({ latencyMs: 50 });
    const pending = withTimeout(quick.recommend(makeSignals()), RECOMMEND_TIMEOUT_MS);
    await vi.advanceTimersByTimeAsync(60);
    const reco = await pending;
    expect(reco).not.toBeNull();
  });
});

describe('signalsToV1Features — contrat v1.0 strict (RFC v1.1 en attente)', () => {
  it("n'émet que les champs du schéma Features v1.0", () => {
    const features = signalsToV1Features(makeSignals('Analyse ce contrat, démontre la clause.'));
    expect(Object.keys(features).sort()).toEqual([
      'char_len',
      'has_attachment_hint',
      'has_code',
      'keyword_flags',
      'lang',
      'token_est',
    ]);
  });

  it("retire le drapeau V0 'demonstration' (hors liste fermée v1.0)", () => {
    const features = signalsToV1Features(makeSignals('démontre le théorème du contrat'));
    expect(features.keyword_flags).not.toContain('demonstration');
    expect(features.keyword_flags).toContain('contrat');
  });
});

describe('createConfigCache — cache + kill-switch', () => {
  it('met la config en cache pendant le TTL', async () => {
    const client = new MockClient({ latencyMs: 0 });
    const spy = vi.spyOn(client, 'getConfig');
    let clock = 0;
    const cache = createConfigCache(client, () => clock);

    const first = cache.get();
    await vi.advanceTimersByTimeAsync(1);
    expect((await first)?.enabled).toBe(true);

    clock += CONFIG_CACHE_TTL_MS - 1;
    const second = cache.get();
    await vi.advanceTimersByTimeAsync(1);
    await second;
    expect(spy).toHaveBeenCalledTimes(1); // servi depuis le cache

    clock += 2; // TTL dépassé
    const third = cache.get();
    await vi.advanceTimersByTimeAsync(1);
    await third;
    expect(spy).toHaveBeenCalledTimes(2);
  });

  it('kill-switch : la config enabled=false est bien restituée', async () => {
    const client = new MockClient({ latencyMs: 0, enabled: false });
    const cache = createConfigCache(client, () => 0);
    const pending = cache.get();
    await vi.advanceTimersByTimeAsync(1);
    expect((await pending)?.enabled).toBe(false);
  });

  it('un échec de lecture ne remplace pas une config déjà connue', async () => {
    const client = new MockClient({ latencyMs: 0 });
    let clock = 0;
    const cache = createConfigCache(client, () => clock);
    const warmup = cache.get();
    await vi.advanceTimersByTimeAsync(1);
    await warmup;

    vi.spyOn(client, 'getConfig').mockRejectedValue(new Error('panne'));
    clock += CONFIG_CACHE_TTL_MS + 1;
    const afterFailure = cache.get();
    await vi.advanceTimersByTimeAsync(RECOMMEND_TIMEOUT_MS + 1);
    expect((await afterFailure)?.enabled).toBe(true); // l'ancienne config survit
  });
});

describe('sendWithRetry — file de retry légère (3 tentatives max)', () => {
  it('retente après échec (1 s puis 5 s) et finit par livrer', async () => {
    const attempt = vi
      .fn()
      .mockResolvedValueOnce(false)
      .mockResolvedValueOnce(false)
      .mockResolvedValueOnce(true);
    const { sendWithRetry } = await import('../src/client');
    sendWithRetry(attempt);
    await vi.advanceTimersByTimeAsync(0);
    expect(attempt).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1000);
    expect(attempt).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(5000);
    expect(attempt).toHaveBeenCalledTimes(3);
  });

  it('abandon silencieux après 3 tentatives — jamais plus', async () => {
    const attempt = vi.fn().mockRejectedValue(new Error('panne réseau'));
    const { sendWithRetry } = await import('../src/client');
    sendWithRetry(attempt);
    await vi.advanceTimersByTimeAsync(60_000);
    expect(attempt).toHaveBeenCalledTimes(3);
  });
});

describe('MockClient — télémétrie capturée localement', () => {
  it('capture les événements envoyés (fire-and-forget local)', () => {
    const client = new MockClient({ latencyMs: 0 });
    const event: RecoEvent = {
      reco_id: 'mock-000001',
      followed: true,
      overridden_to: null,
      ts: '2026-07-16T12:00:00.000Z',
    };
    client.sendRecoEvent(event);
    expect(client.sentEvents).toEqual([event]);
  });
});
