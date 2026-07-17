/**
 * Génère le harnais visuel (test/visual/harness.html) et les captures
 * clair/sombre (test/visual/out/) via Chrome headless. La CSS provient de la
 * SOURCE UNIQUE src/panelStyle.ts (aucune dérive avec le rendu réel), et le
 * markup reproduit celui de src/panel.ts (mêmes classes/attributs). Chaque état
 * est un vrai Shadow DOM avec son thème — comme dans l'extension.
 *
 * Usage : node scripts/capture-visual.mjs
 */
import { execFileSync } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const ROOT = process.cwd();
const OUT_DIR = join(ROOT, 'test', 'visual', 'out');
const HARNESS = join(ROOT, 'test', 'visual', 'harness.html');
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';

// 1) CSS depuis la source unique.
const styleSrc = readFileSync(join(ROOT, 'src', 'panelStyle.ts'), 'utf-8');
const cssMatch = /export const PANEL_CSS = `([\s\S]*?)`;/.exec(styleSrc);
if (!cssMatch) {
  console.error('[capture] PANEL_CSS introuvable dans src/panelStyle.ts');
  process.exit(1);
}
const PANEL_CSS = cssMatch[1];

// 2) Markup d'un panneau — MIROIR de src/panel.ts renderPanel. Seule la CSS
// (PANEL_CSS) est garantie sans dérive ; ce markup est un instantané visuel de
// démonstration (libellés alignés sur src/messages.ts). Le harnais généré
// (test/visual/harness.html) est un artefact non versionné (cf. .gitignore).
function panelMarkup(state) {
  // MIROIR de src/panel.ts formatRange : mêmes décimales (virgule FR + tiret
  // demi-cadratin sans espaces), pour que le harnais reflète le rendu réel.
  const formatRange = (min, max) => {
    const digits = max < 0.01 ? 4 : max < 1 ? 3 : 1;
    const fr = (n) => n.toFixed(digits).replace('.', ',');
    return `${fr(min)}–${fr(max)}`;
  };
  const parts = [];
  parts.push(`<div class="header"><div class="title">Sobrio</div>
    <button class="close" type="button" aria-label="Fermer le panneau">×</button></div>`);
  if (state.mode) {
    parts.push(
      `<div class="mode-note">Équilibre coût / qualité : le modèle proposé vise le juste nécessaire.</div>`,
    );
  }
  parts.push(`<div class="model">${state.model} <small>recommandé</small></div>`);
  parts.push(`<div class="gauge" role="progressbar"><div style="width:${Math.round(state.confidence * 100)}%"></div></div>
    <div class="gauge-label">Confiance : ${Math.round(state.confidence * 100)} %</div>`);
  if (state.confidence < 0.65) {
    parts.push(
      `<p class="note">Signal ambigu — si cette conversation demande un raisonnement complexe, préférez un modèle plus capable.</p>`,
    );
  }
  parts.push(
    `<div class="range">Coût estimé : ${formatRange(state.costMin, state.costMax)} € / appel</div>`,
  );
  parts.push(
    `<div class="range">Énergie estimée : ${formatRange(state.energyMin, state.energyMax)} Wh · périmètre : inférence</div>`,
  );
  if (state.budget) {
    parts.push(`<div class="gauge" data-sobrio-budget><div style="width:42%"></div></div>
      <div class="gauge-label">Budget Équipe démo : 42 % utilisé</div>`);
  }
  if (state.banner) {
    parts.push(
      `<div class="banner">Conversation longue — repartir d'une nouvelle conversation coûtera probablement moins.</div>`,
    );
  }
  parts.push(`<button class="why" type="button">Pourquoi ?</button>
    <p class="note why-text${state.why ? ' visible' : ''}">Votre demande semble courte et simple : un modèle léger suffit probablement.</p>`);
  if (state.ack) {
    parts.push(`<div class="actions"><div class="ack">Merci, c'est noté.</div></div>`);
  } else {
    const opts = state.others.map((m) => `<option>${m}</option>`).join('');
    parts.push(`<div class="actions">
      <button class="primary" type="button">Utiliser ${state.model}</button>
      <p class="hint">Note votre intention.</p>
      <select aria-label="Choisir un autre modèle">${state.others.length ? `<option>Choisir un autre modèle…</option>${opts}` : ''}</select>
    </div>`);
  }
  return parts.join('\n');
}

// Nombres BRUTS (min–max) ; le format (décimales/virgule/tiret) est produit par
// formatRange dans panelMarkup, comme dans le vrai panneau (aucune dérive).
const STATES = [
  {
    key: 'reco-simple',
    model: 'Claude Haiku 4.5',
    confidence: 0.8,
    costMin: 0.0004,
    costMax: 0.0006,
    energyMin: 0.05,
    energyMax: 0.21,
    budget: true,
    others: ['Claude Sonnet 5', 'Claude Opus 4.8'],
  },
  {
    key: 'derogation',
    model: 'Claude Haiku 4.5',
    confidence: 0.8,
    costMin: 0.0004,
    costMax: 0.0006,
    energyMin: 0.05,
    energyMax: 0.21,
    budget: true,
    why: true,
    others: ['Claude Sonnet 5', 'Claude Opus 4.8'],
  },
  {
    key: 'budget-absent',
    model: 'Claude Sonnet 5',
    confidence: 0.7,
    costMin: 0.002,
    costMax: 0.004,
    energyMin: 0.4,
    energyMax: 1.8,
    budget: false,
    others: ['Claude Haiku 4.5', 'Claude Opus 4.8'],
  },
  {
    key: 'suggestion',
    model: 'Claude Opus 4.8',
    confidence: 0.65,
    costMin: 0.006,
    costMax: 0.012,
    energyMin: 0.8,
    energyMax: 3.2,
    budget: true,
    banner: true,
    others: ['Claude Haiku 4.5', 'Claude Sonnet 5'],
  },
  {
    key: 'ambigu',
    model: 'Claude Sonnet 5',
    confidence: 0.55,
    costMin: 0.002,
    costMax: 0.004,
    energyMin: 0.4,
    energyMax: 1.8,
    mode: true,
    others: ['Claude Haiku 4.5', 'Claude Opus 4.8'],
  },
  {
    key: 'basculee',
    model: 'Claude Sonnet 5',
    confidence: 0.75,
    costMin: 0.002,
    costMax: 0.004,
    energyMin: 0.4,
    energyMax: 1.8,
    ack: true,
    others: [],
  },
];

// 3) Harnais : deux colonnes (clair / sombre), un vrai Shadow DOM par état.
// Première cellule = le badge « S » (charte §4 : pastille 22 px), puis les 6
// états du panneau. Le badge est rendu depuis la même PANEL_CSS (source unique).
const cells = (theme) =>
  [
    `<div class="cell"><span class="lbl">badge</span><div class="host" data-kind="badge" data-theme="${theme}"></div></div>`,
    ...STATES.map(
      (s) =>
        `<div class="cell"><span class="lbl">${s.key}</span><div class="host" data-theme="${theme}" data-state='${JSON.stringify(s).replace(/'/g, '&#39;')}'></div></div>`,
    ),
  ].join('\n');

const HTML = `<!doctype html><html lang="fr"><head><meta charset="utf-8">
<style>
  body { margin: 0; font: 12px system-ui; }
  .grid { display: flex; gap: 0; }
  .col { flex: 1; padding: 24px 16px; }
  .col.light { background: #E9E7E2; }
  .col.dark { background: #14130F; }
  .col h2 { font: 600 13px system-ui; margin: 0 0 16px; }
  .col.light h2 { color: #1A1A18; }
  .col.dark h2 { color: #ECEAE4; }
  .cell { margin-bottom: 28px; }
  .lbl { display: block; font: 11px system-ui; opacity: .55; margin-bottom: 6px; }
  .col.dark .lbl { color: #ECEAE4; }
  /* Neutralise le position:fixed du panneau pour empiler les états. */
  .host { position: relative; min-height: 8px; }
</style></head><body>
<div class="grid">
  <div class="col light"><h2>Thème clair</h2>${cells('light')}</div>
  <div class="col dark"><h2>Thème sombre</h2>${cells('dark')}</div>
</div>
<script>
  const CSS = ${JSON.stringify(PANEL_CSS)};
  const LAYOUT = '.panel,.badge{position:static !important;right:auto;bottom:auto;animation:none;margin:0}';
  function markup(s){ ${panelMarkup.toString()}; return panelMarkup(s); }
  for (const host of document.querySelectorAll('.host')) {
    host.setAttribute('data-sobrio-theme', host.getAttribute('data-theme'));
    const root = host.attachShadow({ mode: 'open' });
    const style = document.createElement('style'); style.textContent = CSS + LAYOUT; root.appendChild(style);
    if (host.getAttribute('data-kind') === 'badge') {
      const badge = document.createElement('button'); badge.className = 'badge'; badge.type = 'button'; badge.textContent = 'S';
      root.appendChild(badge);
      continue;
    }
    const s = JSON.parse(host.getAttribute('data-state'));
    const panel = document.createElement('div'); panel.className = 'panel'; panel.innerHTML = markup(s); root.appendChild(panel);
  }
  document.title = 'ready';
</script></body></html>`;

mkdirSync(join(ROOT, 'test', 'visual'), { recursive: true });
mkdirSync(OUT_DIR, { recursive: true });
writeFileSync(HARNESS, HTML);
console.log('[capture] harnais écrit :', HARNESS);

// 4) Capture Chrome headless (pleine page, densité 2x).
const out = join(OUT_DIR, 'panneau-clair-sombre.png');
execFileSync(
  CHROME,
  [
    '--headless=new',
    '--disable-gpu',
    '--hide-scrollbars',
    '--force-device-scale-factor=2',
    // Fenêtre assez HAUTE pour contenir le badge + les 6 états empilés :
    // `--screenshot` clippe au viewport, donc la hauteur doit couvrir toute
    // la colonne.
    '--window-size=800,2900',
    `--screenshot=${out}`,
    `file://${HARNESS}`,
  ],
  { stdio: 'ignore', timeout: 60000 },
);
console.log('[capture] capture écrite :', out);
