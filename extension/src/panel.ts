/**
 * UI Sobrio — badge « S » + panneau de recommandation. Hôtes dédiés + Shadow
 * DOM : styles isolés, AUCUNE pollution de la page hôte.
 *
 * Règle 2 (non négociable) : ces éléments sont À NOUS, ajoutés à côté du
 * contenu de la page. Le bouton « Utiliser [modèle] » NOTE une intention et
 * envoie la télémétrie — il ne clique jamais à la place de l'utilisateur, ne
 * pré-sélectionne aucun modèle dans la page, ne modifie jamais son DOM
 * fonctionnel.
 *
 * Règle 5 : tout coût/énergie affiché est un min–max avec périmètre.
 * Règle 7 : ton humble — les textes viennent de src/messages.ts.
 */
import type { RecoV0 } from './mockClient';
import {
  formatMessage,
  modeNote,
  modelDisplayName,
  ruleExplanation,
  type ExtensionMode,
  type Messages,
} from './messages';
import { resolvePanelAnchor } from './selectors';

const PANEL_HOST_ID = 'sobrio-reco-host';
const BADGE_HOST_ID = 'sobrio-badge-host';

/** Callbacks branchés par le content script (télémétrie + mémoire). */
export interface PanelCallbacks {
  /** L'utilisateur déclare suivre la recommandation (followed=true). */
  onFollow: () => void;
  /** L'utilisateur déroge et indique le modèle choisi (followed=false). */
  onOverride: (model: string) => void;
}

export interface PanelOptions {
  /** Modèles proposés à la dérogation (config.models_visible). */
  modelsVisible: string[];
  messages: Messages;
  callbacks: PanelCallbacks;
  /** Mode d'organisation (config.mode) — infléchit le ton affiché. */
  mode?: ExtensionMode;
}

const STYLE = `
  :host { all: initial; }
  * { box-sizing: border-box; }
  .panel {
    position: fixed;
    right: 16px;
    bottom: 96px;
    z-index: 2147483646;
    width: 300px;
    padding: 14px;
    border: 1px solid #d5d0c8;
    border-radius: 12px;
    background: #faf8f5;
    color: #2b2a27;
    font: 13px/1.5 system-ui, sans-serif;
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.14);
  }
  .header { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }
  .title { font-weight: 600; color: #6b675f; font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase; }
  .close { background: none; border: none; padding: 0; width: auto; color: #6b675f; cursor: pointer; font-size: 16px; line-height: 1; }
  .close:hover, .close:focus-visible { color: #2b2a27; }
  .mode-note { color: #6b675f; font-size: 11px; margin: 2px 0 6px; }
  button:focus-visible, select:focus-visible, .why:focus-visible {
    outline: 2px solid #4a6d51; outline-offset: 1px;
  }
  .model { font-size: 16px; font-weight: 700; margin: 4px 0 2px; }
  .model small { font-weight: 400; color: #6b675f; }
  .gauge { height: 6px; border-radius: 3px; background: #e6e1d7; overflow: hidden; margin: 4px 0 2px; }
  .gauge > div { height: 100%; border-radius: 3px; background: #4a6d51; }
  .gauge-label { color: #6b675f; font-size: 12px; }
  .range { margin: 3px 0; }
  .note { color: #6b675f; font-style: italic; margin: 6px 0 0; font-size: 12px; }
  .banner {
    margin-top: 8px; padding: 7px 9px; border-radius: 8px;
    background: #f0ead9; color: #5d5638; font-size: 12px;
  }
  .actions { display: flex; flex-direction: column; gap: 6px; margin-top: 10px; }
  button, select {
    font: inherit; padding: 6px 10px; border-radius: 8px;
    border: 1px solid #b8b2a7; background: #fff; cursor: pointer; width: 100%;
  }
  button.primary { background: #2b2a27; color: #faf8f5; border-color: #2b2a27; }
  .hint { color: #8a847a; font-size: 11px; margin: 0; }
  .why { background: none; border: none; padding: 0; color: #4a6d51; cursor: pointer; width: auto; font-size: 12px; text-decoration: underline; }
  .why-text { display: none; }
  .why-text.visible { display: block; }
  .ack { font-style: italic; color: #4a6d51; margin-top: 8px; }
  .badge {
    position: fixed; right: 16px; bottom: 48px; z-index: 2147483646;
    width: 26px; height: 26px; border-radius: 50%;
    background: #faf8f5; color: #2b2a27;
    border: 1px solid rgba(43, 42, 39, 0.28); cursor: pointer;
    font: 600 12px/24px system-ui, sans-serif; text-align: center;
    box-shadow: 0 1px 4px rgba(0, 0, 0, 0.18);
    opacity: 0.88;
    transition: opacity 0.15s ease, transform 0.15s ease, background 0.15s ease, color 0.15s ease;
    padding: 0;
  }
  .badge:hover {
    opacity: 1;
    transform: scale(1.08);
    background: #2b2a27;
    color: #faf8f5;
  }
`;

/** Crée (ou remplace) un hôte + shadow root. Retourne null si pas d'ancre. */
function mountHost(hostId: string): ShadowRoot | null {
  try {
    document.getElementById(hostId)?.remove();
    const anchor = resolvePanelAnchor();
    if (!anchor) return null; // dégradation silencieuse
    const host = document.createElement('div');
    host.id = hostId;
    const shadow = host.attachShadow({ mode: 'open' });
    const style = document.createElement('style');
    style.textContent = STYLE;
    shadow.appendChild(style);
    anchor.appendChild(host);
    return shadow;
  } catch {
    return null;
  }
}

/** Retire le panneau (sans jamais throw). */
export function removePanel(): void {
  try {
    document.getElementById(PANEL_HOST_ID)?.remove();
  } catch {
    // Dégradation silencieuse.
  }
}

/** Retire le badge (sans jamais throw). */
export function removeBadge(): void {
  try {
    badgeAnchor = null;
    document.getElementById(BADGE_HOST_ID)?.remove();
  } catch {
    // Dégradation silencieuse.
  }
}

/** Taille du badge (px) — utilisée par le calcul d'ancrage. */
const BADGE_SIZE = 26;

/** Marge intérieure entre le badge et le bord droit de la zone de saisie. */
const BADGE_INSET = 10;

/** Zone de saisie sur laquelle le badge est ancré (overlay, jamais inséré
 * dans le DOM de la page hôte — règle 2 ; son React nous éjecterait). */
let badgeAnchor: HTMLElement | null = null;

/**
 * (Re)positionne le badge sur le bord droit de la barre de saisie, centré
 * verticalement. Si l'ancre a disparu ou n'est pas mesurable (tests),
 * retombe sur le coin bas-droit. Ne throw jamais.
 */
export function repositionBadge(): void {
  try {
    const host = document.getElementById(BADGE_HOST_ID);
    const badge = host?.shadowRoot?.querySelector<HTMLElement>('.badge');
    if (!badge) return;
    const rect = badgeAnchor?.isConnected ? badgeAnchor.getBoundingClientRect() : null;
    if (rect && rect.width > 0 && rect.height > 0) {
      badge.style.top = `${Math.round(rect.top + (rect.height - BADGE_SIZE) / 2)}px`;
      badge.style.left = `${Math.round(rect.right - BADGE_SIZE - BADGE_INSET)}px`;
      badge.style.right = 'auto';
      badge.style.bottom = 'auto';
    } else {
      // Repli : coin bas-droit (comportement d'origine).
      badge.style.top = '';
      badge.style.left = '';
      badge.style.right = '16px';
      badge.style.bottom = '48px';
    }
  } catch {
    // Dégradation silencieuse.
  }
}

/**
 * Badge « S » discret, ANCRÉ dans la barre de saisie (bord droit, centré) —
 * présence de Sobrio, clic = replier le panneau. Overlay positionné sur le
 * rectangle de la zone de saisie : rien n'est inséré dans le DOM fonctionnel.
 */
export function renderBadge(messages: Messages, anchor: HTMLElement | null = null): void {
  badgeAnchor = anchor ?? badgeAnchor;
  if (document.getElementById(BADGE_HOST_ID)) {
    repositionBadge(); // déjà en place : on met simplement à jour l'ancrage
    return;
  }
  const shadow = mountHost(BADGE_HOST_ID);
  if (!shadow) return;
  const badge = document.createElement('button');
  badge.className = 'badge';
  badge.type = 'button';
  badge.textContent = 'S';
  badge.title = messages['badge_title'] ?? 'Sobrio';
  badge.addEventListener('click', () => removePanel());
  shadow.appendChild(badge);
  repositionBadge();
}

/** Fourchette min–max (règle 5 : jamais de valeur unique). */
function formatRange(min: number, max: number): string {
  const digits = max < 0.01 ? 4 : max < 1 ? 3 : 1;
  return `${min.toFixed(digits)} – ${max.toFixed(digits)}`;
}

/**
 * Affiche (ou remplace) le panneau de recommandation.
 * Ne throw jamais : en cas de problème DOM, on n'affiche simplement rien.
 */
export function renderPanel(reco: RecoV0, options: PanelOptions): void {
  try {
    const { messages, callbacks } = options;
    const shadow = mountHost(PANEL_HOST_ID);
    if (!shadow) return;

    const panel = document.createElement('div');
    panel.className = 'panel';
    panel.setAttribute('data-sobrio-panel', '');
    // Accessibilité : panneau non modal (le focus n'est JAMAIS piégé), nommé.
    panel.setAttribute('role', 'complementary');
    panel.setAttribute('aria-label', messages['panel_aria_label'] ?? 'Recommandation Sobrio');

    const header = document.createElement('div');
    header.className = 'header';
    const title = document.createElement('div');
    title.className = 'title';
    title.textContent = messages['panel_title'] ?? 'Sobrio';
    header.appendChild(title);
    const closeButton = document.createElement('button');
    closeButton.className = 'close';
    closeButton.type = 'button';
    closeButton.setAttribute('data-sobrio-close', '');
    closeButton.setAttribute('aria-label', messages['close_label'] ?? 'Fermer');
    closeButton.textContent = '×';
    closeButton.addEventListener('click', () => removePanel());
    header.appendChild(closeButton);
    panel.appendChild(header);

    // Échap ferme le panneau (accessibilité clavier), sans piéger le focus.
    panel.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') removePanel();
    });

    // Note de ton selon le mode d'organisation (eco/equilibre/qualite).
    const note = modeNote(options.mode, messages);
    if (note) {
      const modeLine = document.createElement('div');
      modeLine.className = 'mode-note';
      modeLine.setAttribute('data-sobrio-mode', options.mode ?? '');
      modeLine.textContent = note;
      panel.appendChild(modeLine);
    }

    const model = document.createElement('div');
    model.className = 'model';
    model.setAttribute('data-sobrio-model', reco.recommended_model);
    const suffix = messages['recommended_suffix'] ?? 'recommandé';
    model.append(modelDisplayName(reco.recommended_model), ' ');
    const small = document.createElement('small');
    small.textContent = suffix;
    model.appendChild(small);
    panel.appendChild(model);

    // Jauge de confiance (accessible : progressbar 0–100).
    const gauge = document.createElement('div');
    gauge.className = 'gauge';
    gauge.setAttribute('data-sobrio-confidence', String(reco.confidence));
    const confidencePct = Math.round(Math.min(1, Math.max(0, reco.confidence)) * 100);
    gauge.setAttribute('role', 'progressbar');
    gauge.setAttribute('aria-valuemin', '0');
    gauge.setAttribute('aria-valuemax', '100');
    gauge.setAttribute('aria-valuenow', String(confidencePct));
    gauge.setAttribute('aria-label', messages['confidence_label'] ?? 'Confiance');
    const fill = document.createElement('div');
    fill.style.width = `${confidencePct}%`;
    gauge.appendChild(fill);
    panel.appendChild(gauge);
    const gaugeLabel = document.createElement('div');
    gaugeLabel.className = 'gauge-label';
    gaugeLabel.textContent = `${messages['confidence_label'] ?? 'Confiance'} : ${Math.round(
      reco.confidence * 100,
    )} %`;
    panel.appendChild(gaugeLabel);

    // Signal ambigu ⇒ on le dit (règle 7).
    if (reco.confidence < 0.65) {
      const note = document.createElement('p');
      note.className = 'note';
      note.setAttribute('data-sobrio-ambiguous', '');
      note.textContent = messages['ambiguous_note'] ?? '';
      panel.appendChild(note);
    }

    // Fourchettes coût / énergie (règle 5 : min–max + périmètre).
    const cost = document.createElement('div');
    cost.className = 'range';
    cost.textContent = `${messages['cost_label'] ?? 'Coût estimé'} : ${formatRange(
      reco.impact_estimate.cost_eur_min,
      reco.impact_estimate.cost_eur_max,
    )} ${messages['cost_unit'] ?? '€ / appel'}`;
    panel.appendChild(cost);

    const energy = document.createElement('div');
    energy.className = 'range';
    energy.textContent = `${messages['energy_label'] ?? 'Énergie estimée'} : ${formatRange(
      reco.impact_estimate.energy_wh_min,
      reco.impact_estimate.energy_wh_max,
    )} ${messages['energy_unit'] ?? 'Wh'}`;
    panel.appendChild(energy);

    // Jauge budget — uniquement si fournie.
    if (reco.budget) {
      const budgetGauge = document.createElement('div');
      budgetGauge.className = 'gauge';
      budgetGauge.setAttribute('data-sobrio-budget', '');
      const budgetFill = document.createElement('div');
      budgetFill.style.width = `${Math.round(Math.min(100, Math.max(0, reco.budget.pct_used)))}%`;
      budgetGauge.appendChild(budgetFill);
      panel.appendChild(budgetGauge);
      const budgetLabel = document.createElement('div');
      budgetLabel.className = 'gauge-label';
      budgetLabel.textContent = `${messages['budget_label'] ?? 'Budget'} ${reco.budget.team_label} : ${Math.round(
        reco.budget.pct_used,
      )} ${messages['budget_used_suffix'] ?? '% utilisé'}`;
      panel.appendChild(budgetLabel);
    }

    // Bandeau discret « conversation longue ».
    if (reco.suggest_new_conversation) {
      const banner = document.createElement('div');
      banner.className = 'banner';
      banner.setAttribute('data-sobrio-banner', '');
      banner.textContent = messages['long_conversation_banner'] ?? '';
      panel.appendChild(banner);
    }

    // « Pourquoi ? » — explicabilité en langage clair.
    const why = document.createElement('button');
    why.className = 'why';
    why.type = 'button';
    why.textContent = messages['why_link'] ?? 'Pourquoi ?';
    const whyText = document.createElement('p');
    whyText.className = 'note why-text';
    whyText.setAttribute('data-sobrio-why', '');
    whyText.textContent = ruleExplanation(reco.rule, messages);
    why.addEventListener('click', () => whyText.classList.toggle('visible'));
    panel.appendChild(why);
    panel.appendChild(whyText);

    // Actions — elles NOTENT et télémètrent, elles n'agissent JAMAIS sur la
    // page hôte (règle 2).
    const actions = document.createElement('div');
    actions.className = 'actions';

    const acknowledge = (text: string) => {
      actions.replaceChildren();
      const ack = document.createElement('div');
      ack.className = 'ack';
      ack.setAttribute('data-sobrio-ack', '');
      ack.textContent = text;
      actions.appendChild(ack);
    };

    const followButton = document.createElement('button');
    followButton.className = 'primary';
    followButton.type = 'button';
    followButton.setAttribute('data-sobrio-follow', '');
    followButton.textContent = formatMessage(messages['use_model'] ?? 'Utiliser {model}', {
      model: modelDisplayName(reco.recommended_model),
    });
    followButton.addEventListener('click', () => {
      callbacks.onFollow();
      acknowledge(messages['followed_ack'] ?? '');
    });
    actions.appendChild(followButton);

    const followHint = document.createElement('p');
    followHint.className = 'hint';
    followHint.textContent = messages['use_model_hint'] ?? '';
    actions.appendChild(followHint);

    const others = options.modelsVisible.filter((id) => id !== reco.recommended_model);
    if (others.length > 0) {
      const select = document.createElement('select');
      select.setAttribute('data-sobrio-override', '');
      select.setAttribute('aria-label', messages['choose_other'] ?? 'Choisir un autre modèle');
      const placeholder = document.createElement('option');
      placeholder.value = '';
      placeholder.textContent = messages['choose_other'] ?? 'Choisir un autre modèle…';
      select.appendChild(placeholder);
      for (const id of others) {
        const option = document.createElement('option');
        option.value = id;
        option.textContent = modelDisplayName(id);
        select.appendChild(option);
      }
      select.addEventListener('change', () => {
        if (!select.value) return;
        callbacks.onOverride(select.value);
        acknowledge(messages['overridden_ack'] ?? '');
      });
      actions.appendChild(select);
    }

    panel.appendChild(actions);
    shadow.appendChild(panel);
  } catch {
    // Jamais bloquant : en cas d'erreur DOM inattendue, on n'affiche rien.
  }
}
