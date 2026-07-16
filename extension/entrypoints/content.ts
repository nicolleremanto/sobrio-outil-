/**
 * Content script de PRODUCTION — strictement limité à https://claude.ai/*
 * (règle 6 : permissions minimales). Toute la logique vit dans
 * src/content-main.ts, partagée avec l'entrypoint de développement.
 */
import { defineContentScript } from 'wxt/utils/define-content-script';

import { bootstrap } from '../src/content-main';

export default defineContentScript({
  matches: ['https://claude.ai/*'],
  main() {
    void bootstrap();
  },
});
