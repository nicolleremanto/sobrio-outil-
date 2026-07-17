/**
 * Content script de PRODUCTION — strictement limité à https://claude.ai/*
 * (règle 6 : permissions minimales). Toute la logique vit dans
 * src/content-main.ts.
 *
 * Il enregistre aussi le canal de diagnostic (« Tester la détection » du
 * popup) — répond au message avec la stratégie de détection, sans jamais
 * transmettre de contenu (règle 1).
 */
import { defineContentScript } from 'wxt/utils/define-content-script';
import { browser } from 'wxt/browser';

import { bootstrap } from '../src/content-main';
import { isDiagnoseRequest, runDiagnostics } from '../src/diagnostics';

export default defineContentScript({
  matches: ['https://claude.ai/*'],
  main() {
    browser.runtime.onMessage.addListener((message, _sender, sendResponse) => {
      if (isDiagnoseRequest(message)) {
        sendResponse(runDiagnostics());
        return true; // réponse synchrone
      }
      return false;
    });
    void bootstrap();
  },
});
