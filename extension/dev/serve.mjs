/**
 * Serveur statique ZÉRO dépendance pour la page d'entraînement (pnpm dev:page).
 * Sert extension/dev/testpage/ sur http://localhost:8788 — terrain de jeu de
 * toutes les boucles : on ne dépend jamais de claude.ai pour développer.
 */
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), 'testpage');
const PORT = Number(process.env.PORT ?? 8788);

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.json': 'application/json; charset=utf-8',
};

const server = createServer((req, res) => {
  void (async () => {
    const url = new URL(req.url ?? '/', `http://localhost:${PORT}`);
    let pathname = decodeURIComponent(url.pathname);
    if (pathname.endsWith('/')) pathname += 'index.html';
    // Anti-traversée : on reste dans ROOT.
    const filePath = normalize(join(ROOT, pathname));
    if (!filePath.startsWith(ROOT)) {
      res.writeHead(403).end('403');
      return;
    }
    try {
      const body = await readFile(filePath);
      res.writeHead(200, {
        'Content-Type': MIME[extname(filePath)] ?? 'application/octet-stream',
      });
      res.end(body);
    } catch {
      res.writeHead(404).end('404');
    }
  })();
});

server.listen(PORT, () => {
  console.log(`Page d'entraînement Sobrio : http://localhost:${PORT}/`);
  console.log('Variantes robustesse : /variant-b.html · /variant-broken.html');
});
