import { defineConfig } from 'wxt';

/**
 * Configuration WXT — Manifest V3, cible Chrome/Edge.
 *
 * Règle n°2 (non négociable) : AUCUN secret dans le bundle.
 * L'URL de l'API, l'org_id et le token vivent dans browser.storage.local
 * (renseignés via le popup), jamais dans le code ni dans le manifest.
 *
 * Permissions minimales : `storage` uniquement. Le content script est
 * déclaré sur claude.ai via ses `matches` (entrypoints/content.ts) — pas
 * de host_permissions supplémentaires.
 */
export default defineConfig({
  manifest: {
    name: 'Sobrio',
    description:
      "Recommande le modèle Claude adapté à chaque prompt — affiche et conseille, n'automatise jamais.",
    permissions: ['storage'],
  },
});
