/**
 * Popup Sobrio V0 — configuration (storage uniquement, règle 4) et état.
 *
 * - Backend commutable : mock (défaut, tout marche sans serveur) / api.
 * - URL API, org_id, token → browser.storage.local, jamais dans le bundle.
 * - État de connexion : config distante (kill-switch, mode) en mode api ;
 *   « mode démonstration » en mock. Version affichée depuis le manifest.
 */
import { browser } from 'wxt/browser';

import { getExtensionConfig } from '../../src/api';
import { initDebugLog, saveDebugLogEnabled } from '../../src/debugLog';
import { DIAGNOSE_MESSAGE, formatDiagnosis, type DiagnoseResponse } from '../../src/diagnostics';
import { loadStoredSettings, saveStoredSettings, type BackendMode } from '../../src/settings';

/** Timeout plus généreux que le content script : le popup n'est pas bloquant. */
const POPUP_TIMEOUT_MS = 2000;

function element<T extends HTMLElement>(id: string): T {
  const found = document.getElementById(id);
  if (!found) throw new Error(`Élément #${id} introuvable dans le popup`);
  return found as T;
}

async function refreshStatus(): Promise<void> {
  const statusText = element<HTMLParagraphElement>('status-text');
  const settings = await loadStoredSettings();

  if (settings.backend === 'mock') {
    statusText.textContent =
      'Mode démonstration (mock) — tout fonctionne sans serveur, aucune donnée n’est envoyée.';
    return;
  }

  if (!settings.apiUrl || !settings.orgId || !settings.token) {
    statusText.textContent =
      'Mode API : renseignez l’URL de l’API, l’organisation et le token pour activer la recommandation.';
    return;
  }

  const config = await getExtensionConfig(
    { apiUrl: settings.apiUrl, orgId: settings.orgId, token: settings.token },
    POPUP_TIMEOUT_MS,
  );
  if (!config) {
    statusText.textContent =
      'API injoignable — la recommandation est simplement désactivée (jamais bloquant).';
    return;
  }

  const killSwitch = config.enabled ? 'active' : 'désactivée (kill-switch)';
  statusText.textContent = `Extension ${killSwitch} · mode « ${config.mode} » · version minimale ${config.min_extension_version}.`;
}

function refreshApiFieldsVisibility(backend: BackendMode): void {
  element<HTMLFieldSetElement>('api-fields').style.display = backend === 'api' ? 'block' : 'none';
}

async function initForm(): Promise<void> {
  const form = element<HTMLFormElement>('settings-form');
  const backendSelect = element<HTMLSelectElement>('backend');
  const apiUrlInput = element<HTMLInputElement>('api-url');
  const orgIdInput = element<HTMLInputElement>('org-id');
  const tokenInput = element<HTMLInputElement>('token');
  const autoApplyCheckbox = element<HTMLInputElement>('auto-apply');
  const debugCheckbox = element<HTMLInputElement>('debug');

  const settings = await loadStoredSettings();
  backendSelect.value = settings.backend;
  apiUrlInput.value = settings.apiUrl;
  orgIdInput.value = settings.orgId;
  tokenInput.value = settings.token;
  autoApplyCheckbox.checked = settings.autoApplyModel;
  refreshApiFieldsVisibility(settings.backend);

  try {
    const stored = await browser.storage.local.get('sobrio_debug');
    debugCheckbox.checked = stored['sobrio_debug'] === true;
  } catch {
    debugCheckbox.checked = false;
  }

  backendSelect.addEventListener('change', () => {
    refreshApiFieldsVisibility(backendSelect.value === 'api' ? 'api' : 'mock');
  });

  form.addEventListener('submit', (event) => {
    event.preventDefault();
    void (async () => {
      await saveStoredSettings({
        backend: backendSelect.value === 'api' ? 'api' : 'mock',
        apiUrl: apiUrlInput.value.trim(),
        orgId: orgIdInput.value.trim(),
        token: tokenInput.value,
        // Opt-in explicite (amendement règle 2) — décoché = lecture seule.
        autoApplyModel: autoApplyCheckbox.checked,
      });
      await saveDebugLogEnabled(debugCheckbox.checked);
      await refreshStatus();
    })();
  });
}

/**
 * « Tester la détection » : demande au content script de l'onglet actif
 * d'exécuter le diagnostic (le popup n'a pas accès au DOM de la page).
 * Message-only : aucun contenu ne transite (règle 1).
 */
function initDiagnostic(): void {
  const button = element<HTMLButtonElement>('diagnose-btn');
  const result = element<HTMLParagraphElement>('diagnose-result');
  button.addEventListener('click', () => {
    void (async () => {
      result.textContent = 'Test en cours…';
      try {
        const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
        if (tab?.id === undefined) {
          result.textContent = 'Aucun onglet actif.';
          return;
        }
        const response = (await browser.tabs.sendMessage(tab.id, {
          type: DIAGNOSE_MESSAGE,
        })) as DiagnoseResponse | undefined;
        result.textContent = response?.ok
          ? formatDiagnosis(response.diagnosis)
          : "Sobrio n'est pas actif sur cet onglet (ouvrez une page claude.ai).";
      } catch {
        result.textContent =
          "Sobrio n'est pas actif sur cet onglet (ouvrez une page claude.ai, puis rechargez).";
      }
    })();
  });
}

function showVersion(): void {
  try {
    const { version } = browser.runtime.getManifest();
    element<HTMLParagraphElement>('version-text').textContent = `Extension v${version}`;
  } catch {
    // Dégradation silencieuse (contexte de test).
  }
}

void (async () => {
  await initDebugLog();
  await initForm();
  initDiagnostic();
  showVersion();
  await refreshStatus();
})();
