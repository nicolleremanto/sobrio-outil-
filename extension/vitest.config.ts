import { defineConfig } from 'vitest/config';

/**
 * Tests unitaires du Lot A — environnement DOM factice (happy-dom) pour les
 * tests de sélecteurs ; les tests de features sont de pures fonctions.
 */
export default defineConfig({
  test: {
    environment: 'happy-dom',
    include: ['tests/**/*.test.ts'],
  },
});
