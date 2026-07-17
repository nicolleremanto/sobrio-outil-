/**
 * Chargeur de fixtures DOM headless — remplace l'ancienne page d'entraînement.
 * Injecte le <body> d'une fixture dans le document happy-dom et expose le
 * chemin d'URL simulé (attribut data-sim-path) pour les tests SPA.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

export type FixtureName = 'nominal' | 'alt1' | 'alt2' | 'broken';

/** Charge une fixture ; retourne le chemin d'URL simulé qu'elle déclare. */
export function loadFixture(name: FixtureName): string {
  // process.cwd() = extension/ (vitest y tourne, localement comme en CI).
  const path = join(process.cwd(), 'test', 'fixtures', `fixture_${name}.html`);
  const html = readFileSync(path, 'utf-8');
  const body = /<body[^>]*>([\s\S]*)<\/body>/.exec(html)?.[1] ?? '';
  document.body.innerHTML = body;
  const simPath = /<body[^>]*\sdata-sim-path="([^"]+)"/.exec(html)?.[1];
  return simPath ?? '/';
}
