-- by_workspace.sql — Ventilation mensuelle par workspace (dimension « workspace »).
--
-- Mesure   : par workspace Anthropic : tokens totaux, dépense mesurée (USD),
--            énergie estimée en fourchette Wh min–max (règle n°3).
-- Périmètre: 100 % de l'usage mesuré par le connecteur (API d'administration
--            Anthropic). Usage Bedrock/Vertex NON couvert.
-- Limites  : données réconciliées jusqu'à J+30 (règle n°6) ; l'usage sans
--            workspace identifié peut apparaître sous une valeur sentinelle
--            définie par l'agrégation (Lot D).
SELECT
  -- Sentinelle '' (lignes sans workspace, cf. docs/decisions.md) → libellé lisible.
  COALESCE(NULLIF(dim_value, ''), '(hors workspace)') AS workspace,
  tokens_total,
  cost_usd,
  energy_wh_min,
  energy_wh_max
FROM monthly_agg
WHERE org_id = :org_id
  AND month = :month
  AND dimension = 'workspace'
ORDER BY cost_usd DESC NULLS LAST, dim_value;
