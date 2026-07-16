// Configuration ESLint (flat config) — extension Sobrio, Lot A.
import js from '@eslint/js';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  {
    ignores: ['.output/', '.wxt/', 'node_modules/', 'stats*.json'],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['**/*.ts'],
    rules: {
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
      // Garde-fou règle n°1 : pas de console.* dans le code de l'extension
      // (un log de texte de prompt serait une fuite de contenu).
      'no-console': 'error',
    },
  },
  {
    // Outillage de développement (serveur de la page d'entraînement, scripts
    // node) : hors bundle de l'extension — globals Node et console autorisés.
    files: ['dev/**/*.mjs'],
    languageOptions: {
      globals: {
        console: 'readonly',
        process: 'readonly',
        URL: 'readonly',
        Buffer: 'readonly',
      },
    },
  },
);
