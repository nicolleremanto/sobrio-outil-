-- reco_adoption.sql — Taux de suivi des recommandations de l'extension (events_reco).
--
-- Mesure   : nombre de recommandations émises sur le mois, nombre suivies
--            (followed = true), nombre tranchées (followed non null), et taux
--            de suivi en % (suivies / tranchées).
-- Périmètre: chat navigateur (claude.ai via l'extension) UNIQUEMENT — ne couvre
--            pas l'usage API. À présenter séparément des mesures du connecteur
--            (règle n°4).
-- Limites  : les événements sans retour (followed null) sont exclus du taux ;
--            la télémétrie est déclarative côté extension (Lot A) et ne
--            contient JAMAIS de texte de prompt (règle n°1).
SELECT
  count(*) AS n_events,
  count(*) FILTER (WHERE followed IS TRUE) AS n_followed,
  count(*) FILTER (WHERE followed IS NOT NULL) AS n_decided,
  CASE
    WHEN count(*) FILTER (WHERE followed IS NOT NULL) > 0
    THEN round(
      100.0 * count(*) FILTER (WHERE followed IS TRUE)
        / count(*) FILTER (WHERE followed IS NOT NULL),
      1
    )
    ELSE NULL
  END AS adoption_rate_pct
FROM events_reco
WHERE org_id = :org_id
  AND ts >= :month
  AND ts < :month_next;
