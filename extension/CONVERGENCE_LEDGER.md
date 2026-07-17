# Journal de convergence — Finition orchestrée multi-agents (V2)

> Chef d'orchestre : construit → prouve (lint/test/build/captures) → juge (agents
> INDÉPENDANTS à contexte neuf) → consigne → décide. Convergence d'un chantier =
> **2 rondes vertes consécutives**. Plafond 8 rondes. Un FAIL `privacy-sentinel`
> interdit de passer, non waivable.

Agents : `design-critic`, `qa-auditor`, `privacy-sentinel` (PASS/FAIL),
`robustness-redteam`, `product-conformance`, `perf-auditor`
(définitions dans `.claude/agents/`).

Vérification en ligne (2026-07-17) : gamme et tarifs Anthropic confirmés via
`platform.claude.com/docs/.../models/overview` et la référence claude-api —
Fable 5 (10/50), Opus 4.8 (5/25), Sonnet 5 (3/15 · intro 2/10), Haiku 4.5 (1/5).

---

## État des chantiers

| Chantier | Sujet                             | Rondes vertes consécutives | Statut   |
| -------- | --------------------------------- | -------------------------- | -------- |
| C        | Catalogue de modèles à jour       | 0/2                        | en cours |
| A        | Refonte graphique du panneau      | 0/2                        | à venir  |
| B        | Bascule instantanée + assist_mode | 0/2                        | à venir  |

---

<!-- Les tableaux de rondes sont ajoutés au fil de l'eau ci-dessous. -->
