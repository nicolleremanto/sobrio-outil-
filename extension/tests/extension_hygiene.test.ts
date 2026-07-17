/**
 * Boucle 8 — revue automatique d'hygiène au niveau SOURCE (partie du gate de
 * test). Vérifie les règles non négociables par analyse statique :
 *  - règle 1 : aucun console.* de contenu (seul debugLog a un console.debug
 *    volontaire, filtré aux nombres/booléens) ;
 *  - réseau confiné : fetch/XHR/WebSocket/sendBeacon uniquement dans api.ts,
 *    et seuls les 3 endpoints du contrat sont appelés ;
 *  - nettoyage : content-main détache ses écouteurs/observers.
 */
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

const ROOT = process.cwd();

function collectSources(dir: string, acc: string[] = []): string[] {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) collectSources(full, acc);
    else if (entry.name.endsWith('.ts')) acc.push(full);
  }
  return acc;
}

const SRC_FILES = collectSources(join(ROOT, 'src'));
const ENTRY_FILES = collectSources(join(ROOT, 'entrypoints'));
const ALL_FILES = [...SRC_FILES, ...ENTRY_FILES];

describe('Règle 1 — aucun console de contenu', () => {
  it('seul debugLog.ts utilise console (console.debug filtré)', () => {
    for (const file of ALL_FILES) {
      const src = readFileSync(file, 'utf-8');
      const uses = /\bconsole\.\w+\(/.test(src);
      if (uses) {
        expect(file.endsWith('debugLog.ts'), `console interdit dans ${file}`).toBe(true);
        // Et uniquement console.debug (pas log/info/warn/error).
        expect(/console\.(log|info|warn|error)\(/.test(src)).toBe(false);
      }
    }
  });
});

describe('Réseau confiné', () => {
  it('fetch/XHR/WebSocket/sendBeacon uniquement dans api.ts', () => {
    for (const file of ALL_FILES) {
      const src = readFileSync(file, 'utf-8');
      const usesNetwork = /\b(fetch|XMLHttpRequest|WebSocket|sendBeacon)\s*\(/.test(src);
      if (usesNetwork) {
        expect(file.endsWith('api.ts'), `réseau hors api.ts : ${file}`).toBe(true);
      }
    }
  });

  it('api.ts n’appelle que les 3 endpoints du contrat', () => {
    const api = readFileSync(join(ROOT, 'src', 'api.ts'), 'utf-8');
    const paths = [...api.matchAll(/['"`](\/v1\/[^'"`?]+)/g)].map((m) => m[1]);
    const allowed = new Set(['/v1/recommend', '/v1/telemetry/reco_event', '/v1/extension/config']);
    for (const p of paths) {
      expect(allowed.has(p!), `endpoint hors contrat : ${p}`).toBe(true);
    }
    expect(paths.length).toBeGreaterThanOrEqual(3);
  });

  it('aucune URL absolue en dur (règle 4 : pas de secret/hôte figé)', () => {
    for (const file of ALL_FILES) {
      const src = readFileSync(file, 'utf-8');
      // http(s) en dur toléré uniquement pour claude.ai (matches) et exemples.
      const urls = [...src.matchAll(/https?:\/\/[^\s'"`]+/g)].map((m) => m[0]);
      for (const url of urls) {
        const ok =
          url.includes('claude.ai') ||
          url.includes('localhost') ||
          url.includes('sobrio.example') ||
          url.includes('wxt.dev') ||
          url.includes('schema');
        expect(ok, `URL en dur suspecte dans ${file} : ${url}`).toBe(true);
      }
    }
  });
});

describe('Nettoyage — aucun écouteur global fuyant', () => {
  it('content-main détache observers et écouteurs', () => {
    const content = readFileSync(join(ROOT, 'src', 'content-main.ts'), 'utf-8');
    expect(content).toContain('disconnect()');
    expect(content).toContain('removeEventListener');
    expect(content).toContain('pagehide');
  });
});
