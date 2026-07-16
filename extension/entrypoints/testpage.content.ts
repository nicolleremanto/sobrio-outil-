/**
 * Content script de DÉVELOPPEMENT — page d'entraînement locale uniquement
 * (pnpm dev:page → http://localhost:8788). Cet entrypoint est EXCLU des
 * builds de production par `filterEntrypoints` (voir wxt.config.ts) : le zip
 * livré ne matche que claude.ai (règle 6 — permissions minimales).
 */
import { defineContentScript } from 'wxt/utils/define-content-script';

import { bootstrap } from '../src/content-main';

export default defineContentScript({
  matches: ['http://localhost:8788/*'],
  main() {
    void bootstrap();
  },
});
