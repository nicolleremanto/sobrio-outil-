/**
 * Styles du panneau + badge Sobrio — SOURCE UNIQUE (charte §4).
 *
 * Importé par `panel.ts` (injecté dans le Shadow DOM) et lu par le script de
 * captures `scripts/capture-visual.mjs` : une seule définition, aucune dérive
 * entre le rendu réel et le harnais visuel.
 *
 * Identité : sobre, précise, premium discret. Accent sauge unique, grille 8 px
 * stricte, thèmes clair ET sombre (prefers-color-scheme + attribut de thème
 * posé depuis la page hôte), contrastes AA.
 */
export const PANEL_CSS = `
  :host {
    all: initial;
    /* Thème clair par défaut (charte §4). */
    --bg: #FFFFFF;
    --text: #1A1A18;
    --secondary: #6B6B66;
    --accent: #0E7C66;
    --accent-contrast: #FFFFFF;
    --border: rgba(0, 0, 0, 0.06);
    --track: rgba(0, 0, 0, 0.08);
    --banner-bg: rgba(14, 124, 102, 0.08);
    --shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
    --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, system-ui, sans-serif;
  }
  /* Sombre : suit la préférence système, sauf thème clair explicite de l'hôte.
     Écart charte ASSUMÉ : l'ombre est renforcée (0.32 vs 0.08) car une ombre à
     0.08 est invisible sur fond sombre — le token clair reste 0.08. */
  @media (prefers-color-scheme: dark) {
    :host(:not([data-sobrio-theme="light"])) {
      --bg: #262521;
      --text: #ECEAE4;
      --secondary: #A8A69E;
      --accent: #4FB8A0;
      --accent-contrast: #1A1A18;
      --border: rgba(255, 255, 255, 0.08);
      --track: rgba(255, 255, 255, 0.10);
      --banner-bg: rgba(79, 184, 160, 0.12);
      --shadow: 0 4px 16px rgba(0, 0, 0, 0.32);
    }
  }
  /* Le thème posé par la page hôte (classe de thème claude.ai) prime. */
  :host([data-sobrio-theme="dark"]) {
    --bg: #262521;
    --text: #ECEAE4;
    --secondary: #A8A69E;
    --accent: #4FB8A0;
    --accent-contrast: #1A1A18;
    --border: rgba(255, 255, 255, 0.08);
    --track: rgba(255, 255, 255, 0.10);
    --banner-bg: rgba(79, 184, 160, 0.12);
    --shadow: 0 4px 16px rgba(0, 0, 0, 0.32);
  }
  :host([data-sobrio-theme="light"]) {
    --bg: #FFFFFF;
    --text: #1A1A18;
    --secondary: #6B6B66;
    --accent: #0E7C66;
    --accent-contrast: #FFFFFF;
    --border: rgba(0, 0, 0, 0.06);
    --track: rgba(0, 0, 0, 0.08);
    --banner-bg: rgba(14, 124, 102, 0.08);
    --shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
  }
  * { box-sizing: border-box; }

  .panel {
    position: fixed;
    right: 16px;
    bottom: 96px;
    z-index: 2147483646;
    width: 320px;
    max-width: 320px;
    padding: 16px;
    border: 1px solid var(--border);
    border-radius: 12px;
    background: var(--bg);
    color: var(--text);
    font: 12px/1.5 var(--font);
    font-variant-numeric: tabular-nums;
    box-shadow: var(--shadow);
    animation: sobrio-in 150ms ease-out;
  }
  @keyframes sobrio-in {
    from { opacity: 0; transform: translateY(4px); }
    to { opacity: 1; transform: translateY(0); }
  }

  /* En-tête : titre + fermeture, aligné sur la grille 8. */
  .header { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
  /* Écart charte ASSUMÉ : l'en-tête « SOBRIO » est un OVERLINE (eyebrow) —
     11px/600, majuscules, interlettrage 0.08em, couleur secondaire — et non le
     « titre 13px/600 » de la charte §4. Le titre 13px de la carte, c'est le nom
     du modèle (.model). L'eyebrow 11px est une convention premium sobre
     (surtitre discret), volontairement plus petit que le corps 12px. */
  .title {
    font-weight: 600; font-size: 11px; color: var(--secondary);
    letter-spacing: 0.08em; text-transform: uppercase; margin: 0;
  }
  .close {
    background: none; border: none; padding: 0; width: auto; height: 16px;
    color: var(--secondary); cursor: pointer; font-size: 16px; line-height: 1;
    border-radius: 4px;
  }
  .close:hover { color: var(--text); }

  .mode-note { color: var(--secondary); font-size: 12px; margin: 8px 0 0; }

  .model { font-size: 13px; font-weight: 600; margin: 8px 0 0; color: var(--text); }
  /* « recommandé » : corps 12 px explicite (sinon le <small> tomberait à
     ~10,8 px, hors de l'échelle typo 11/12/13 de la charte §4). */
  .model small { font-weight: 400; font-size: 12px; color: var(--secondary); }

  /* Jauges : 4 px arrondies, piste neutre, remplissage accent.
     Écart grille ASSUMÉ : marge basse 4 px (demi-pas) — appariement de
     proximité jauge↔légende (la légende colle à sa barre, 8 px vers le bloc
     suivant). Seule valeur hors 8/16 px, couplée à la hauteur imposée 4 px. */
  .gauge { height: 4px; border-radius: 2px; background: var(--track); overflow: hidden; margin: 8px 0 4px; }
  .gauge > div { height: 100%; border-radius: 2px; background: var(--accent); }
  .gauge-label { color: var(--secondary); font-size: 12px; }

  .range { margin: 8px 0 0; }
  .note { color: var(--secondary); font-style: italic; margin: 8px 0 0; font-size: 12px; }

  .banner {
    margin-top: 8px; padding: 8px; border-radius: 8px;
    background: var(--banner-bg); color: var(--text); font-size: 12px;
  }

  .actions { display: flex; flex-direction: column; gap: 8px; margin-top: 16px; }
  button, select {
    font: inherit; height: 28px; padding: 0 12px; border-radius: 8px;
    border: 1px solid var(--border); background: transparent; color: var(--text);
    cursor: pointer; width: 100%;
  }
  select { padding: 0 8px; }
  button.primary {
    background: var(--accent); color: var(--accent-contrast); border-color: var(--accent);
    font-weight: 600;
  }
  .hint { color: var(--secondary); font-size: 12px; margin: 0; }

  .why {
    background: none; border: none; padding: 0; margin: 8px 0 0; width: auto; height: auto;
    color: var(--accent); cursor: pointer; font-size: 12px; text-decoration: underline;
  }
  .why-text { display: none; }
  .why-text.visible { display: block; }
  .ack { font-style: italic; color: var(--accent); margin-top: 16px; font-size: 12px; }

  /* Focus clavier annulaire, visible sur les deux thèmes. */
  button:focus-visible, select:focus-visible, .close:focus-visible, .why:focus-visible {
    outline: 2px solid var(--accent); outline-offset: 2px;
  }

  /* Badge pastille 22 px. */
  .badge {
    position: fixed; right: 16px; bottom: 48px; z-index: 2147483646;
    width: 22px; height: 22px; border-radius: 50%; padding: 0;
    background: var(--bg); color: var(--text);
    border: 1px solid var(--border); cursor: pointer;
    font: 600 11px/20px var(--font); text-align: center;
    box-shadow: var(--shadow); opacity: 0.85;
    transition: opacity 120ms ease, transform 120ms ease;
  }
  .badge:hover { opacity: 1; transform: scale(1.06); }
  .badge:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

  /* Respect de la préférence système « mouvement réduit » (WCAG 2.3.3) :
     neutralise l'apparition du panneau et la transition du badge. */
  @media (prefers-reduced-motion: reduce) {
    .panel { animation: none; }
    .badge { transition: none; }
    .badge:hover { transform: none; }
  }
`;
