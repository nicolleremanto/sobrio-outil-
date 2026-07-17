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
import type { AssistMode } from './api';
import type { RecoV0 } from './mockClient';
import {
  formatMessage,
  modeNote,
  modelDisplayName,
  ruleExplanation,
  type ExtensionMode,
  type Messages,
} from './messages';
import { PANEL_CSS } from './panelStyle';
import { resolvePanelAnchor } from './selectors';

const PANEL_HOST_ID = 'sobrio-reco-host';
const BADGE_HOST_ID = 'sobrio-badge-host';

/** Callbacks branchés par le content script (télémétrie + mémoire). */
export interface PanelCallbacks {
  /** L'utilisateur déclare suivre la recommandation (followed=true). */
  onFollow: () => void;
  /** L'utilisateur déroge et indique le modèle choisi (followed=false). */
  onOverride: (model: string) => void;
  /**
   * Mode `auto` : l'utilisateur annule la bascule automatique. Restaure le
   * modèle précédent et télémètre followed=false, overridden_to=précédent.
   */
  onCancel?: () => void;
  /**
   * Mode `auto` : le panneau « basculé » est ÉCARTÉ sans annuler (fermeture,
   * Échap) — l'utilisateur accepte la bascule (followed=true différé).
   */
  onDismiss?: () => void;
}

export interface PanelOptions {
  /** Modèles proposés à la dérogation (config.models_visible). */
  modelsVisible: string[];
  messages: Messages;
  callbacks: PanelCallbacks;
  /** Mode d'organisation (config.mode) — infléchit le ton affiché. */
  mode?: ExtensionMode;
  /** Mode d'assistance effectif (RFC-0003) — infléchit la zone d'actions. */
  assistMode?: AssistMode;
  /**
   * Mode `auto` : la bascule a déjà été DÉCLENCHÉE (UI optimiste) → le panneau
   * s'ouvre en état « basculé » avec Annuler, au lieu du bouton « Utiliser ».
   */
  autoSwitched?: boolean;
  /**
   * Mode `auto` : le modèle recommandé est DÉJÀ sélectionné — rien à basculer.
   * On l'indique au lieu d'un bouton d'action inutile.
   */
  alreadyOnModel?: boolean;
}

const STYLE = PANEL_CSS;

/**
 * Détecte le thème de la page hôte (claude.ai) : classe/attribut de thème, puis
 * repli sur la luminance du fond. Retourne `null` si indéterminable — auquel
 * cas `prefers-color-scheme` gouverne (charte §4). Ne throw jamais.
 */
export function detectHostTheme(): 'dark' | 'light' | null {
  try {
    const root = document.documentElement;
    const cls = ` ${root.className} `;
    const attr = (
      root.getAttribute('data-theme') ??
      root.getAttribute('data-mode') ??
      ''
    ).toLowerCase();
    if (/\s(dark|theme-dark)\s/.test(cls) || attr === 'dark') return 'dark';
    if (/\s(light|theme-light)\s/.test(cls) || attr === 'light') return 'light';
    const bg = getComputedStyle(document.body).backgroundColor;
    const m = /rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?/.exec(bg);
    if (m) {
      const alpha = m[4] === undefined ? 1 : Number(m[4]);
      if (alpha > 0) {
        const lum = 0.2126 * Number(m[1]) + 0.7152 * Number(m[2]) + 0.0722 * Number(m[3]);
        return lum < 128 ? 'dark' : 'light';
      }
    }
  } catch {
    // Dégradation silencieuse.
  }
  return null;
}

/** Crée (ou remplace) un hôte + shadow root. Retourne null si pas d'ancre. */
function mountHost(hostId: string): ShadowRoot | null {
  try {
    document.getElementById(hostId)?.remove();
    const anchor = resolvePanelAnchor();
    if (!anchor) return null; // dégradation silencieuse
    const host = document.createElement('div');
    host.id = hostId;
    // Thème détecté de la page hôte (prioritaire sur prefers-color-scheme).
    const theme = detectHostTheme();
    if (theme) host.setAttribute('data-sobrio-theme', theme);
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

/**
 * Vrai si le panneau de recommandation est actuellement monté. Sert à ne PAS
 * ressusciter un panneau qu'une navigation SPA vient de retirer (anti-fuite).
 */
export function isPanelPresent(): boolean {
  try {
    return document.getElementById(PANEL_HOST_ID) !== null;
  } catch {
    return false;
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
const BADGE_SIZE = 22;

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
export interface BadgeOptions {
  /** Mode d'assistance effectif — infléchit le libellé (honnêteté, règle 7). */
  assistMode?: AssistMode;
  /** Masquer le panneau via le badge = l'écarter (committe une acceptation). */
  onDismiss?: () => void;
}

export function renderBadge(
  messages: Messages,
  anchor: HTMLElement | null = null,
  options: BadgeOptions = {},
): void {
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
  // Titre HONNÊTE selon le mode (règle 7) : auto = agit automatiquement ;
  // one_click = agit sur clic ; guide (défaut) = ne touche jamais la page.
  badge.title =
    options.assistMode === 'auto'
      ? (messages['badge_title_auto'] ?? messages['badge_title'] ?? 'Sobrio')
      : options.assistMode === 'one_click'
        ? (messages['badge_title_one_click'] ?? messages['badge_title'] ?? 'Sobrio')
        : (messages['badge_title'] ?? 'Sobrio');
  badge.addEventListener('click', () => {
    // Écarter le panneau via le badge committe une acceptation auto en attente
    // (sinon orpheline), puis le retire.
    options.onDismiss?.();
    removePanel();
  });
  shadow.appendChild(badge);
  repositionBadge();
}

/**
 * Fourchette min–max (règle 5 : jamais de valeur unique). Format charte §4 :
 * décimale virgule (FR) et tiret demi-cadratin SANS espaces — « 0,004–0,006 ».
 */
export function formatRange(min: number, max: number): string {
  const digits = max < 0.01 ? 4 : max < 1 ? 3 : 1;
  const fr = (n: number) => n.toFixed(digits).replace('.', ',');
  return `${fr(min)}–${fr(max)}`;
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
    // Écarter le panneau (croix / Échap) notifie l'acceptation d'une bascule
    // auto en attente (onDismiss), puis le retire — sans piéger le focus.
    const dismiss = () => {
      callbacks.onDismiss?.();
      removePanel();
    };
    closeButton.addEventListener('click', dismiss);
    header.appendChild(closeButton);
    panel.appendChild(header);

    // Échap ferme le panneau (accessibilité clavier), sans piéger le focus.
    panel.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') dismiss();
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
    // Libellé borné (réutilise confidencePct) : texte et barre coïncident toujours.
    gaugeLabel.textContent = `${messages['confidence_label'] ?? 'Confiance'} : ${confidencePct} %`;
    panel.appendChild(gaugeLabel);

    // Signal ambigu ⇒ on le dit (règle 7). Variable distincte de la `note` de
    // ton plus haut (évite l'ombrage — une seule source de l'UI, lisible).
    if (reco.confidence < 0.65) {
      const ambiguousNote = document.createElement('p');
      ambiguousNote.className = 'note';
      ambiguousNote.setAttribute('data-sobrio-ambiguous', '');
      ambiguousNote.textContent = messages['ambiguous_note'] ?? '';
      panel.appendChild(ambiguousNote);
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

    // Jauge budget — uniquement si fournie (accessible : progressbar 0–100,
    // par parité avec la jauge de confiance).
    if (reco.budget) {
      // Sincérité budget : la BARRE est bornée à 100 % (elle ne peut pas
      // déborder visuellement), mais le LIBELLÉ affiche la valeur RÉELLE — un
      // dépassement (> 100 %) doit rester visible, jamais masqué en « 100 % ».
      const rawPct = Math.round(Math.max(0, reco.budget.pct_used));
      const barPct = Math.min(100, rawPct);
      const budgetGauge = document.createElement('div');
      budgetGauge.className = 'gauge';
      budgetGauge.setAttribute('data-sobrio-budget', '');
      budgetGauge.setAttribute('role', 'progressbar');
      budgetGauge.setAttribute('aria-valuemin', '0');
      budgetGauge.setAttribute('aria-valuemax', '100');
      // La barre (donc aria-valuenow) est bornée à 100 ; le dépassement est
      // porté par le libellé, l'attribut de dépassement, et aria-valuetext —
      // pour que le lecteur d'écran entende la valeur RÉELLE (parité a11y ↔ visuel).
      budgetGauge.setAttribute('aria-valuenow', String(barPct));
      budgetGauge.setAttribute(
        'aria-valuetext',
        `${rawPct} ${messages['budget_used_suffix'] ?? '% utilisé'}`,
      );
      if (rawPct > 100) budgetGauge.setAttribute('data-sobrio-budget-over', String(rawPct));
      budgetGauge.setAttribute(
        'aria-label',
        `${messages['budget_label'] ?? 'Budget'} ${reco.budget.team_label}`,
      );
      const budgetFill = document.createElement('div');
      budgetFill.style.width = `${barPct}%`;
      budgetGauge.appendChild(budgetFill);
      panel.appendChild(budgetGauge);
      const budgetLabel = document.createElement('div');
      budgetLabel.className = 'gauge-label';
      // Libellé : valeur RÉELLE (rawPct) — un budget dépassé s'affiche « 118 % »,
      // jamais tronqué à 100 % (sincérité, cohérent avec les fourchettes).
      budgetLabel.textContent = `${messages['budget_label'] ?? 'Budget'} ${reco.budget.team_label} : ${rawPct} ${messages['budget_used_suffix'] ?? '% utilisé'}`;
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

    if (options.autoSwitched) {
      // Mode `auto` : la bascule a déjà été déclenchée (UI optimiste). On
      // confirme discrètement et on propose Annuler (restaure le précédent).
      const switched = document.createElement('div');
      switched.className = 'ack';
      switched.setAttribute('data-sobrio-switched', '');
      switched.textContent = formatMessage(messages['auto_switched'] ?? 'Basculé sur {model}', {
        model: modelDisplayName(reco.recommended_model),
      });
      actions.appendChild(switched);

      const cancelButton = document.createElement('button');
      cancelButton.type = 'button';
      cancelButton.setAttribute('data-sobrio-cancel', '');
      cancelButton.textContent = messages['cancel_auto'] ?? 'Annuler';
      cancelButton.addEventListener('click', () => {
        cancelButton.disabled = true; // pas de double-clic pendant la restauration
        callbacks.onCancel?.();
        acknowledge(messages['switched_back'] ?? '');
      });
      actions.appendChild(cancelButton);

      const autoHint = document.createElement('p');
      autoHint.className = 'hint';
      autoHint.textContent = messages['auto_switch_hint'] ?? '';
      actions.appendChild(autoHint);
    } else if (options.alreadyOnModel) {
      // Auto, mais déjà sur le modèle recommandé : simple accusé, aucune action.
      const already = document.createElement('div');
      already.className = 'ack';
      already.setAttribute('data-sobrio-already', '');
      already.textContent = formatMessage(messages['already_on_model'] ?? 'Déjà sur {model}.', {
        model: modelDisplayName(reco.recommended_model),
      });
      actions.appendChild(already);
    } else {
      const followButton = document.createElement('button');
      followButton.className = 'primary';
      followButton.type = 'button';
      followButton.setAttribute('data-sobrio-follow', '');
      // En guide, le bouton ne bascule PAS la page : libellé non-actif (intention),
      // pas « Utiliser » qui suggérerait une action que guide n'effectue jamais.
      const useLabel =
        options.assistMode === 'guide'
          ? (messages['use_model_guide'] ?? 'J’utiliserai {model}')
          : (messages['use_model'] ?? 'Utiliser {model}');
      followButton.textContent = formatMessage(useLabel, {
        model: modelDisplayName(reco.recommended_model),
      });
      followButton.addEventListener('click', () => {
        callbacks.onFollow();
        acknowledge(messages['followed_ack'] ?? '');
      });
      actions.appendChild(followButton);

      const followHint = document.createElement('p');
      followHint.className = 'hint';
      // Mode `guide` : on n'agit pas sur la page — on indique quoi faire.
      followHint.textContent =
        options.assistMode === 'guide'
          ? (messages['guide_hint'] ?? '')
          : (messages['use_model_hint'] ?? '');
      if (options.assistMode === 'guide') followHint.setAttribute('data-sobrio-guide-hint', '');
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
    }

    panel.appendChild(actions);
    shadow.appendChild(panel);
  } catch {
    // Jamais bloquant : en cas d'erreur DOM inattendue, on n'affiche rien.
  }
}
