/**
 * Télémétrie industrialisée — file d'envoi PERSISTANTE (chrome.storage) avec
 * retry exponentiel (max 3 tentatives), puis abandon silencieux. La file
 * survit aux rechargements de page : les événements en attente sont repris au
 * prochain démarrage.
 *
 * RÈGLE 1 : schéma STRICT — un événement qui n'a pas exactement les 4 champs
 * du contrat (reco_id, followed, overridden_to, ts) est REJETÉ à l'entrée
 * (jamais mis en file, jamais envoyé). Aucun texte libre ne peut transiter.
 *
 * RÈGLE 3 : jamais bloquant — toute erreur est silencieuse.
 */
import { browser } from 'wxt/browser';

import type { ExtensionConfig, RecoEvent } from './api';

export const TELEMETRY_QUEUE_KEY = 'sobrio_telemetry_queue';
export const TELEMETRY_STATS_KEY = 'sobrio_telemetry_sent';
export const TELEMETRY_MAX_ATTEMPTS = 3;
/** Backoff exponentiel par numéro de tentative (ms) : immédiat, 2 s, 10 s. */
export const TELEMETRY_BACKOFF_MS = [0, 2000, 10000];

/** Zone de stockage minimale (injectable pour les tests). */
export interface StorageArea {
  get(key: string): Promise<Record<string, unknown>>;
  set(items: Record<string, unknown>): Promise<void>;
}

function defaultStorage(): StorageArea {
  return browser.storage.local as unknown as StorageArea;
}

interface QueueItem {
  event: RecoEvent;
  attempts: number;
  nextAttemptAt: number;
}

/**
 * Valide qu'un objet est un RecoEvent STRICT : exactement les 4 champs
 * attendus, aux bons types. Tout écart ⇒ rejet (garde-fou anti-fuite).
 */
export function isStrictRecoEvent(value: unknown): value is RecoEvent {
  if (typeof value !== 'object' || value === null) return false;
  const keys = Object.keys(value).sort();
  if (keys.join(',') !== 'followed,overridden_to,reco_id,ts') return false;
  const e = value as Record<string, unknown>;
  return (
    typeof e['reco_id'] === 'string' &&
    typeof e['followed'] === 'boolean' &&
    (e['overridden_to'] === null || typeof e['overridden_to'] === 'string') &&
    typeof e['ts'] === 'string'
  );
}

/** Télémétrie autorisée ? Non si kill-switch, non si l'org l'a désactivée. */
export function telemetryAllowed(config: ExtensionConfig | null): boolean {
  if (!config) return true; // aucune config ⇒ pas de restriction connue
  if (!config.enabled) return false; // kill-switch
  // Champ d'opt-out d'organisation (proposé RFC-0001) — lu défensivement,
  // absent ⇒ autorisé par défaut.
  const flag = (config as unknown as { telemetry_enabled?: unknown }).telemetry_enabled;
  return flag !== false;
}

export type DeliverFn = (event: RecoEvent) => Promise<boolean>;

export interface TelemetryQueueOptions {
  storage?: StorageArea;
  now?: () => number;
}

export class TelemetryQueue {
  private readonly storage: StorageArea;
  private readonly now: () => number;

  constructor(
    private readonly deliver: DeliverFn,
    options: TelemetryQueueOptions = {},
  ) {
    this.storage = options.storage ?? defaultStorage();
    this.now = options.now ?? Date.now;
  }

  private async readQueue(): Promise<QueueItem[]> {
    try {
      const stored = await this.storage.get(TELEMETRY_QUEUE_KEY);
      const queue = stored[TELEMETRY_QUEUE_KEY];
      return Array.isArray(queue) ? (queue as QueueItem[]) : [];
    } catch {
      return [];
    }
  }

  private async writeQueue(queue: QueueItem[]): Promise<void> {
    try {
      await this.storage.set({ [TELEMETRY_QUEUE_KEY]: queue });
    } catch {
      // Dégradation silencieuse.
    }
  }

  /** Nombre d'événements en attente. */
  async pending(): Promise<number> {
    return (await this.readQueue()).length;
  }

  /** Nombre d'événements livrés avec succès (compteur cumulé). */
  async sentCount(): Promise<number> {
    try {
      const stored = await this.storage.get(TELEMETRY_STATS_KEY);
      const n = stored[TELEMETRY_STATS_KEY];
      return typeof n === 'number' ? n : 0;
    } catch {
      return 0;
    }
  }

  private async bumpSent(count: number): Promise<void> {
    if (count <= 0) return;
    const current = await this.sentCount();
    try {
      await this.storage.set({ [TELEMETRY_STATS_KEY]: current + count });
    } catch {
      // Dégradation silencieuse.
    }
  }

  /**
   * Met un événement en file (après validation stricte) puis tente un envoi.
   * Événement non conforme ⇒ ignoré silencieusement (jamais envoyé).
   */
  async enqueue(event: RecoEvent): Promise<void> {
    if (!isStrictRecoEvent(event)) return;
    const queue = await this.readQueue();
    queue.push({ event, attempts: 0, nextAttemptAt: this.now() });
    await this.writeQueue(queue);
    await this.flush();
  }

  /**
   * Traite les événements dus (nextAttemptAt ≤ maintenant) : succès ⇒ retiré
   * et compté ; échec ⇒ tentative incrémentée + backoff exponentiel, abandon
   * après TELEMETRY_MAX_ATTEMPTS. Les événements non encore dus restent.
   */
  async flush(): Promise<void> {
    const queue = await this.readQueue();
    if (queue.length === 0) return;

    const remaining: QueueItem[] = [];
    let sent = 0;
    for (const item of queue) {
      if (item.nextAttemptAt > this.now()) {
        remaining.push(item); // pas encore dû
        continue;
      }
      let delivered = false;
      try {
        delivered = await this.deliver(item.event);
      } catch {
        // Échec de livraison : `delivered` reste false, on réessaiera.
      }
      if (delivered) {
        sent += 1;
        continue;
      }
      const attempts = item.attempts + 1;
      if (attempts >= TELEMETRY_MAX_ATTEMPTS) continue; // abandon silencieux
      remaining.push({
        event: item.event,
        attempts,
        nextAttemptAt: this.now() + (TELEMETRY_BACKOFF_MS[attempts] ?? 10000),
      });
    }
    await this.writeQueue(remaining);
    await this.bumpSent(sent);
  }
}
