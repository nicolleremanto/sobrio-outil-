/**
 * Garde de taille du bundle (boucle 8) — échoue si le build de production
 * dépasse le budget. Lancé après `wxt build` (voir le script `build`).
 */
import { readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

const OUTPUT_DIR = join(process.cwd(), '.output', 'chrome-mv3');
const MAX_BYTES = 2 * 1024 * 1024; // 2 Mo

function dirSize(dir) {
  let total = 0;
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name);
    total += entry.isDirectory() ? dirSize(full) : statSync(full).size;
  }
  return total;
}

let size;
try {
  size = dirSize(OUTPUT_DIR);
} catch {
  console.error(`[check:size] build introuvable dans ${OUTPUT_DIR} — lancez d'abord le build.`);
  process.exit(1);
}

const kb = (size / 1024).toFixed(1);
if (size > MAX_BYTES) {
  console.error(`[check:size] ÉCHEC : bundle ${kb} Ko > budget 2048 Ko.`);
  process.exit(1);
}
console.log(`[check:size] OK : bundle ${kb} Ko (budget 2048 Ko).`);
