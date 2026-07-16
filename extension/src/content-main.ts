/**
 * Logique du content script Sobrio — partagée entre l'entrypoint de
 * production (claude.ai) et l'entrypoint de développement (page
 * d'entraînement locale).
 *
 * RÈGLE N°2 (non négociable, encodée ici) — extension en LECTURE SEULE :
 *  - elle AFFICHE une recommandation et conseille, elle n'automatise JAMAIS ;
 *  - aucun clic simulé, aucune pré-sélection de modèle dans la page hôte ;
 *  - le DOM fonctionnel de la page n'est JAMAIS modifié : notre panneau vit
 *    dans un hôte dédié + Shadow DOM ajouté À CÔTÉ (voir src/panel.ts) ;
 *  - aucun secret dans le bundle : URL API, org_id et token viennent de
 *    browser.storage.local (popup).
 *
 * RÈGLE N°1 : le texte du prompt reste LOCAL. Il est réduit en features
 * (src/features.ts) et seules ces features partent vers l'API. Jamais de log
 * du contenu.
 *
 * Dégradation silencieuse : échec ou timeout (400 ms) de l'API ⇒ on n'affiche
 * RIEN. L'extension n'est JAMAIS bloquante pour l'utilisateur.
 */
import {
  getExtensionConfig,
  loadSettings,
  postRecoEvent,
  postRecommend,
  type ApiSettings,
  type RecommendResponse,
} from './api';
import { computeFeatures } from './features';
import { removePanel, renderPanel } from './panel';
import { resolveInputArea } from './selectors';

/** Pause de saisie avant calcul des features + appel API. */
const DEBOUNCE_MS = 600;

export async function bootstrap(): Promise<void> {
  const settings = await loadSettings();
  if (!settings) return; // pas configuré ⇒ on ne fait rien (jamais bloquant)

  // Kill-switch distant : on ne s'arrête que sur un `enabled: false` EXPLICITE.
  // Un échec réseau ne désactive pas l'extension (dégradation silencieuse).
  // TODO(LotA) : cache local de la config + rafraîchissement périodique +
  // vérification de min_extension_version.
  const config = await getExtensionConfig(settings);
  if (config && !config.enabled) return;

  observeInputArea(settings);
}

/**
 * Observe le DOM (SPA : la zone de saisie apparaît/disparaît au fil de la
 * navigation) et attache l'écouteur de saisie dès qu'une zone est résolue.
 * Résolution `null` ⇒ on réessaie au prochain changement de DOM, sans erreur.
 */
function observeInputArea(settings: ApiSettings): void {
  let currentInput: HTMLElement | null = null;
  let debounceTimer: ReturnType<typeof setTimeout> | undefined;

  const onInput = () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      void onTypingPause(settings, currentInput);
    }, DEBOUNCE_MS);
  };

  const ensureAttached = () => {
    if (currentInput?.isConnected) return;
    const input = resolveInputArea();
    if (!input) return; // dégradation silencieuse (voir src/selectors.ts)
    currentInput = input;
    // Écoute PASSIVE de la saisie — on lit, on ne modifie rien (règle n°2).
    input.addEventListener('input', onInput);
  };

  const observer = new MutationObserver(ensureAttached);
  observer.observe(document.documentElement, { childList: true, subtree: true });
  ensureAttached();
}

/**
 * Lecture LOCALE du texte de la zone de saisie. Le texte ne quitte jamais le
 * content script : il est immédiatement réduit en features (règle n°1).
 */
function readInputText(input: HTMLElement): string {
  if (input instanceof HTMLTextAreaElement) return input.value;
  return input.textContent ?? '';
}

/** À chaque pause de saisie : features locales → reco → affichage. */
async function onTypingPause(settings: ApiSettings, input: HTMLElement | null): Promise<void> {
  if (!input?.isConnected) return;

  const text = readInputText(input);
  if (text.trim().length === 0) {
    removePanel();
    return;
  }

  // Seules les features (mesures/indicateurs) sortent d'ici — jamais le texte.
  const features = computeFeatures(text);
  const reco = await postRecommend(settings, features);
  if (!reco) return; // échec/timeout ⇒ NE RIEN AFFICHER (jamais bloquant)

  renderPanel(reco, {
    onFollow: () => sendRecoEvent(settings, reco, true, null),
    onOverride: (model) => sendRecoEvent(settings, reco, false, model),
  });
}

/**
 * Télémétrie STRICTE (contrat) : exactement reco_id/followed/overridden_to/ts.
 * Fire-and-forget : un échec d'envoi n'affecte jamais l'utilisateur.
 */
function sendRecoEvent(
  settings: ApiSettings,
  reco: RecommendResponse,
  followed: boolean,
  overriddenTo: string | null,
): void {
  void postRecoEvent(settings, {
    reco_id: reco.reco_id,
    followed,
    overridden_to: overriddenTo,
    ts: new Date().toISOString(),
  });
}
