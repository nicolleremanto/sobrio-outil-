# Journal des décisions — Sobrio

Toute décision structurante est consignée ici (une ligne par décision).
Les évolutions de contrats passent par une RFC (`docs/rfc/`) — voir règle n°7.

| Date | Décision | Motif |
|------|----------|-------|
| 2026-07-16 | Lot 0 bootstrappé, contrats v1.0 figés (`contracts/`) | Base commune stable pour les lots A-F ; tout changement de contrat = RFC + version |
| 2026-07-16 | `uv` non disponible sur la machine de bootstrap → venv racine `.venv` + `requirements.txt` par package | Rester sur l'outillage présent, sans dépendance exotique |
| 2026-07-16 | gitleaks non installable → hook pre-commit de détection de secrets en regex simple (`language: pygrep`) | Garder un garde-fou anti-secret (règle n°5) sans binaire externe |
| 2026-07-16 | `docs/DECOUPAGE_DEV_PHASE1.md` non fourni au bootstrap → à ajouter | Le document de découpage détaillé sera versionné dès réception |
| 2026-07-16 | Taux de conversion fixe `EUR_PER_USD = 0.92` en attendant une source de taux | Débloquer les calculs de coût ; TODO : brancher une vraie source de taux |
| 2026-07-16 | Module `sobrio_impact` installé en éditable et partagé entre API et warehouse | Une seule implémentation du type `Range` et de `estimate()` (règle n°3) |
| 2026-07-16 | `usage_daily` : sentinelle `''` (chaîne vide, jamais NULL) pour `workspace_id`/`api_key_id`/`user_pseudonym` non applicables | Postgres traite les NULL comme distincts dans un index UNIQUE → `ON CONFLICT DO NOTHING` inopérant, idempotence cassée. Filtrer avec `= ''`, pas `IS NULL` |
| 2026-07-16 | CORS activé sur l'API pour l'origine `https://claude.ai` (+ localhost dev), configurable via `SOBRIO_CORS_ORIGINS` | Le content script (Lot A) appelle l'API depuis claude.ai ; sans préflight OPTIONS autorisé, l'extension dégrade silencieusement et n'affiche rien |
| 2026-07-16 | Le Makefile charge et exporte `.env` (`-include .env` + `export`) | `make sync-fixtures` exige `PSEUDONYM_SALT` (règle n°1) ; les cibles doivent voir les variables d'environnement de dev |
| 2026-07-16 | **Amendement règle n°2** (décision fondateur) : application automatique du modèle dans claude.ai en **opt-in strict** — case popup désactivée par défaut, action déclenchée uniquement par le clic « Utiliser… » de l'utilisateur, module unique `extension/src/modelSwitcher.ts`, abandon silencieux au moindre doute | Demande produit assumée en connaissance des risques (fragilité sélecteurs, CGU Anthropic, pitch « n'automatise jamais » nuancé en « n'agit que si vous l'activez ») ; gating org `allow_auto_apply` proposé en RFC-0001 |
| 2026-07-16 | **Amendement règle n°2, v2** (décision fondateur) : l'application automatique passe **activée par défaut** (désactivable dans le popup — décochée, retour à la lecture seule stricte) | Choix produit assumé ; l'action reste déclenchée uniquement par le clic « Utiliser… » de l'utilisateur et vérifiée a posteriori ; le gating org `allow_auto_apply` (RFC-0001) devient d'autant plus important pour les déploiements entreprise |
