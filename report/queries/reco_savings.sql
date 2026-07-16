-- reco_savings.sql — Économies OBTENUES sur le mois, en fourchette EUR min–max.
--
-- Mesure   : somme, sur les recommandations SUIVIES (followed = true), de la
--            différence de coût estimée entre l'alternative haute et le modèle
--            recommandé, telle que calculée au moment de la recommandation
--            (colonnes cost_eur_min / cost_eur_max d'events_reco). Fourchette
--            uniquement (règle n°3) : somme des bornes basses / somme des
--            bornes hautes.
-- Périmètre: chat navigateur (claude.ai via l'extension) UNIQUEMENT — ne couvre
--            pas l'usage API. Ces économies OBTENUES ne se comparent pas à la
--            dépense totale MESURÉE par le connecteur (règle n°4).
-- Limites  : STUB honnête — TODO(LotE) : définir la baseline exacte du
--            contrefactuel (quelle « alternative haute » sert de référence,
--            tokens réels vs estimés au moment de la reco, dérogations
--            partielles). En Lot 0 on somme les deltas pré-calculés par
--            événement, sans re-calcul.
SELECT
  count(*) AS n_followed,
  coalesce(sum(cost_eur_min), 0) AS savings_eur_min,
  coalesce(sum(cost_eur_max), 0) AS savings_eur_max
FROM events_reco
WHERE org_id = :org_id
  AND followed IS TRUE
  AND ts >= :month
  AND ts < :month_next;
