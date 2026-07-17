import { defineConfig } from 'wxt';

/**
 * Configuration WXT — Manifest V3, cible Chrome/Edge.
 *
 * Règle n°2 : AUCUN secret dans le bundle. L'URL de l'API, l'org_id et le
 * token vivent dans browser.storage.local (renseignés via le popup), jamais
 * dans le code ni dans le manifest.
 *
 * Règle n°6 : permissions minimales — `storage` uniquement ; le content
 * script est déclaré sur `https://claude.ai/*` via ses `matches`
 * (entrypoints/content.ts). Aucun host_permissions supplémentaire.
 *
 * Développement (`pnpm dev`) : WXT ouvre un Chrome dédié, l'extension chargée,
 * en auto-rechargement sur claude.ai — il suffit d'actualiser l'onglet pour
 * voir chaque changement (voir README).
 */
export default defineConfig({
  manifest: {
    name: 'Sobrio',
    version: '1.2.0',
    description:
      "Recommande le modèle Claude adapté à chaque prompt — n'agit que si vous l'y autorisez.",
    permissions: ['storage'],
  },
});
