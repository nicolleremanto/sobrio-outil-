-- by_model.sql — Ventilation mensuelle par modèle (dimension « model » de monthly_agg).
--
-- Mesure   : par modèle du catalogue (haiku-4-5, sonnet-4-6, opus-4-8…) :
--            tokens totaux, dépense mesurée (USD), énergie estimée en fourchette
--            Wh min–max (règle n°3).
-- Périmètre: 100 % de l'usage mesuré par le connecteur (API d'administration
--            Anthropic). Usage Bedrock/Vertex NON couvert.
-- Limites  : données réconciliées jusqu'à J+30 (règle n°6) ; les identifiants de
--            modèle sont ceux de contracts/model_catalog.yaml.
SELECT
  dim_value AS model,
  tokens_total,
  cost_usd,
  energy_wh_min,
  energy_wh_max
FROM monthly_agg
WHERE org_id = :org_id
  AND month = :month
  AND dimension = 'model'
ORDER BY cost_usd DESC NULLS LAST, dim_value;
