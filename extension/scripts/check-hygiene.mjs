/**
 * Revue automatique d'hygiène (boucle 8) — échoue si le manifest de production
 * expose plus que le minimum (règle 6). Complète le test vitest
 * `extension_hygiene.test.ts` (qui couvre le niveau source). Lancé après build.
 */
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const manifestPath = join(process.cwd(), '.output', 'chrome-mv3', 'manifest.json');

let manifest;
try {
  manifest = JSON.parse(readFileSync(manifestPath, 'utf-8'));
} catch {
  console.error('[check:hygiene] manifest introuvable — lancez d’abord le build.');
  process.exit(1);
}

const problems = [];

const permissions = manifest.permissions ?? [];
if (permissions.length !== 1 || permissions[0] !== 'storage') {
  problems.push(`permissions attendues ["storage"], trouvées ${JSON.stringify(permissions)}`);
}
if (manifest.host_permissions && manifest.host_permissions.length > 0) {
  problems.push(`host_permissions non vide : ${JSON.stringify(manifest.host_permissions)}`);
}
const matches = (manifest.content_scripts ?? []).flatMap((cs) => cs.matches ?? []);
const forbidden = matches.filter((m) => m !== 'https://claude.ai/*');
if (forbidden.length > 0) {
  problems.push(`content_scripts hors claude.ai : ${JSON.stringify(forbidden)}`);
}

if (problems.length > 0) {
  console.error('[check:hygiene] ÉCHEC :');
  for (const p of problems) console.error('  - ' + p);
  process.exit(1);
}
console.log('[check:hygiene] OK : permissions minimales, claude.ai uniquement.');
