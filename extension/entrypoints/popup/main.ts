/**
 * Popup d'état Sobrio — Lot A (squelette).
 *
 * - Formulaire de configuration : URL API, org_id, token → browser.storage.local
 *   (règle n°2 : aucun secret dans le bundle, tout vient du storage).
 * - État : configuration distante via GET /v1/extension/config (kill-switch
 *   `enabled`, `mode`), avec dégradation silencieuse si l'API est injoignable.
 *
 * TODO(LotA) : UX finale (validation fine, i18n via config.messages,
 * indicateur de version vs min_extension_version, bouton de test de connexion).
 */
import { getExtensionConfig, loadSettings, saveSettings } from '../../src/api';

/** Timeout plus généreux que le content script : le popup n'est pas bloquant. */
const POPUP_TIMEOUT_MS = 2000;

function element<T extends HTMLElement>(id: string): T {
  const found = document.getElementById(id);
  if (!found) throw new Error(`Élément #${id} introuvable dans le popup`);
  return found as T;
}

async function refreshStatus(): Promise<void> {
  const statusText = element<HTMLParagraphElement>('status-text');
  const settings = await loadSettings();
  if (!settings) {
    statusText.textContent =
      'Non configuré — renseignez l’URL de l’API, l’organisation et le token.';
    return;
  }

  const config = await getExtensionConfig(settings, POPUP_TIMEOUT_MS);
  if (!config) {
    statusText.textContent =
      'API injoignable — la recommandation est simplement désactivée (jamais bloquant).';
    return;
  }

  const killSwitch = config.enabled ? 'active' : 'désactivée (kill-switch)';
  statusText.textContent = `Extension ${killSwitch} · mode « ${config.mode} » · version minimale ${config.min_extension_version}.`;
}

async function initForm(): Promise<void> {
  const form = element<HTMLFormElement>('settings-form');
  const apiUrlInput = element<HTMLInputElement>('api-url');
  const orgIdInput = element<HTMLInputElement>('org-id');
  const tokenInput = element<HTMLInputElement>('token');

  const settings = await loadSettings();
  if (settings) {
    apiUrlInput.value = settings.apiUrl;
    orgIdInput.value = settings.orgId;
    tokenInput.value = settings.token;
  }

  form.addEventListener('submit', (event) => {
    event.preventDefault();
    void (async () => {
      await saveSettings({
        apiUrl: apiUrlInput.value.trim(),
        orgId: orgIdInput.value.trim(),
        token: tokenInput.value,
      });
      await refreshStatus();
    })();
  });
}

void (async () => {
  await initForm();
  await refreshStatus();
})();
