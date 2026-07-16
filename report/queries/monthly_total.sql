-- monthly_total.sql — Totaux mensuels de l'organisation (dimension « total » de monthly_agg).
--
-- Mesure   : tokens totaux, dépense mesurée (USD), énergie estimée en fourchette
--            Wh min–max (règle n°3 : jamais de valeur unique), et version du
--            catalogue utilisée lors de l'agrégation (traçabilité).
-- Périmètre: 100 % de l'usage mesuré par le connecteur (API d'administration
--            Anthropic — Usage & Cost). Usage Bedrock/Vertex NON couvert.
-- Limites  : données réconciliées jusqu'à J+30 (règle n°6) ; la dimension
--            « total » porte une seule ligne, avec dim_value sentinelle (« * »).
SELECT
  tokens_total,
  cost_usd,
  energy_wh_min,
  energy_wh_max,
  catalog_version
FROM monthly_agg
WHERE org_id = :org_id
  AND month = :month
  AND dimension = 'total';
