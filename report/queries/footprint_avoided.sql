-- footprint_avoided.sql — Empreinte ÉVITÉE sur le mois, en fourchette Wh min–max.
--
-- Mesure   : somme, sur les recommandations SUIVIES (followed = true), de
--            l'énergie évitée estimée au moment de la recommandation (colonnes
--            impact_wh_min / impact_wh_max d'events_reco). Fourchette
--            uniquement (règle n°3) : somme des bornes basses / somme des
--            bornes hautes. Jamais d'équivalents grand public.
-- Périmètre: chat navigateur (claude.ai via l'extension) UNIQUEMENT — même
--            périmètre que reco_savings.sql. Ce chiffre ne s'additionne PAS à
--            l'empreinte totale mesurée par le connecteur et ne s'y compare
--            pas directement (règle n°4) : il s'agit d'une estimation
--            contrefactuelle, pas d'une mesure.
-- Limites  : STUB honnête — TODO(LotE) : même baseline exacte que
--            reco_savings.sql (alternative haute de référence, tokens réels vs
--            estimés). Facteurs d'impact du catalogue à recalibrer (Lot D).
SELECT
  count(*) AS n_followed,
  coalesce(sum(impact_wh_min), 0) AS avoided_wh_min,
  coalesce(sum(impact_wh_max), 0) AS avoided_wh_max
FROM events_reco
WHERE org_id = :org_id
  AND followed IS TRUE
  AND ts >= :month
  AND ts < :month_next;
