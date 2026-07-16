/**
 * Panneau de recommandation Sobrio — hôte dédié + Shadow DOM.
 *
 * Règle n°2 (non négociable) : le panneau est un élément À NOUS, ajouté à côté
 * du contenu de claude.ai (append sur un point d'ancrage), avec un Shadow DOM
 * fermé sur ses styles. Il AFFICHE la recommandation ; il ne clique jamais à
 * la place de l'utilisateur, ne pré-sélectionne aucun modèle dans claude.ai,
 * et ne modifie JAMAIS le DOM fonctionnel de la page.
 *
 * Règle n°3 : les chiffres affichés sont des fourchettes min–max avec leur
 * périmètre — jamais d'équivalents grand public (litres, arbres, km).
 *
 * TODO(LotA) : UX finale (design, i18n via config.messages, accessibilité,
 * position configurable, animation discrète).
 */
import type { RecommendResponse } from './api';
import { resolvePanelAnchor } from './selectors';

const HOST_ID = 'sobrio-reco-host';

/** Callbacks de télémétrie branchés par le content script. */
export interface PanelCallbacks {
  /** L'utilisateur déclare suivre la recommandation (followed=true). */
  onFollow: () => void;
  /** L'utilisateur déroge et indique le modèle choisi (followed=false). */
  onOverride: (model: string) => void;
}

const PANEL_STYLE = `
  :host { all: initial; }
  .sobrio-panel {
    position: fixed;
    right: 16px;
    bottom: 96px;
    z-index: 2147483646;
    max-width: 320px;
    padding: 12px 14px;
    border: 1px solid #d5d0c8;
    border-radius: 10px;
    background: #faf8f5;
    color: #2b2a27;
    font: 13px/1.45 system-ui, sans-serif;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  }
  .sobrio-title { font-weight: 600; margin-bottom: 4px; }
  .sobrio-model { font-size: 15px; font-weight: 700; }
  .sobrio-meta { color: #6b675f; margin: 4px 0; }
  .sobrio-range { margin: 2px 0; }
  .sobrio-actions { display: flex; gap: 8px; margin-top: 8px; align-items: center; }
  button, select {
    font: inherit;
    padding: 4px 10px;
    border-radius: 6px;
    border: 1px solid #b8b2a7;
    background: #fff;
    cursor: pointer;
  }
  button.primary { background: #2b2a27; color: #faf8f5; border-color: #2b2a27; }
  .sobrio-ack { font-style: italic; color: #6b675f; }
`;

/** Retire le panneau s'il est présent (sans jamais throw). */
export function removePanel(): void {
  try {
    document.getElementById(HOST_ID)?.remove();
  } catch {
    // Dégradation silencieuse.
  }
}

/** Formate une fourchette min–max (règle n°3 : jamais de valeur unique). */
function formatRange(min: number, max: number, unit: string): string {
  return `${min.toFixed(4)} – ${max.toFixed(4)} ${unit}`;
}

/**
 * Affiche (ou remplace) le panneau de recommandation.
 * Ne throw jamais : en cas de problème DOM, on n'affiche simplement rien.
 */
export function renderPanel(reco: RecommendResponse, callbacks: PanelCallbacks): void {
  try {
    removePanel();
    const anchor = resolvePanelAnchor();
    if (!anchor) return; // dégradation silencieuse

    const host = document.createElement('div');
    host.id = HOST_ID;
    const shadow = host.attachShadow({ mode: 'open' });

    const style = document.createElement('style');
    style.textContent = PANEL_STYLE;
    shadow.appendChild(style);

    const panel = document.createElement('div');
    panel.className = 'sobrio-panel';

    const title = document.createElement('div');
    title.className = 'sobrio-title';
    title.textContent = 'Sobrio — recommandation';
    panel.appendChild(title);

    const model = document.createElement('div');
    model.className = 'sobrio-model';
    model.textContent = reco.recommended_model;
    panel.appendChild(model);

    const meta = document.createElement('div');
    meta.className = 'sobrio-meta';
    meta.textContent = `confiance ${(reco.confidence * 100).toFixed(0)} % · règle : ${reco.rule}`;
    panel.appendChild(meta);

    const cost = document.createElement('div');
    cost.className = 'sobrio-range';
    cost.textContent = `Coût estimé : ${formatRange(
      reco.impact_estimate.cost_eur_min,
      reco.impact_estimate.cost_eur_max,
      '€ / appel',
    )}`;
    panel.appendChild(cost);

    const energy = document.createElement('div');
    energy.className = 'sobrio-range';
    // Règle n°3 : fourchette + périmètre explicite, en Wh, sans équivalents.
    energy.textContent = `Énergie estimée : ${formatRange(
      reco.impact_estimate.energy_wh_min,
      reco.impact_estimate.energy_wh_max,
      'Wh (périmètre : inférence)',
    )}`;
    panel.appendChild(energy);

    if (reco.budget) {
      const budget = document.createElement('div');
      budget.className = 'sobrio-meta';
      budget.textContent = `Budget ${reco.budget.team_label} : ${reco.budget.pct_used.toFixed(0)} % utilisé`;
      panel.appendChild(budget);
    }

    const actions = document.createElement('div');
    actions.className = 'sobrio-actions';

    const acknowledge = () => {
      // Après la télémétrie, on remplace les actions par un accusé discret.
      actions.replaceChildren();
      const ack = document.createElement('span');
      ack.className = 'sobrio-ack';
      ack.textContent = 'Merci, c’est noté.';
      actions.appendChild(ack);
    };

    // Bouton « suivi » : l'utilisateur déclare suivre la reco (followed=true).
    const followButton = document.createElement('button');
    followButton.className = 'primary';
    followButton.type = 'button';
    followButton.textContent = 'Je suis la reco';
    followButton.addEventListener('click', () => {
      callbacks.onFollow();
      acknowledge();
    });
    actions.appendChild(followButton);

    // Dérogation : choix d'un modèle alternatif (followed=false, overridden_to).
    if (reco.alternatives.length > 0) {
      const select = document.createElement('select');
      select.setAttribute('aria-label', 'Modèle choisi en dérogation');
      const placeholder = document.createElement('option');
      placeholder.value = '';
      placeholder.textContent = 'Déroger vers…';
      select.appendChild(placeholder);
      for (const alt of reco.alternatives) {
        const option = document.createElement('option');
        option.value = alt.model;
        option.textContent = alt.model;
        select.appendChild(option);
      }
      select.addEventListener('change', () => {
        if (!select.value) return;
        callbacks.onOverride(select.value);
        acknowledge();
      });
      actions.appendChild(select);
    }

    panel.appendChild(actions);
    shadow.appendChild(panel);
    anchor.appendChild(host);
  } catch {
    // Jamais bloquant : en cas d'erreur DOM inattendue, on n'affiche rien.
  }
}
