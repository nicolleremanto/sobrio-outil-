CREATE TABLE orgs (
  org_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  api_token_hash TEXT NOT NULL,
  policy_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE usage_daily (
  id BIGSERIAL PRIMARY KEY,
  org_id TEXT NOT NULL REFERENCES orgs(org_id),
  date DATE NOT NULL,
  source TEXT NOT NULL,              -- 'anthropic_admin' | 'anthropic_analytics'
  workspace_id TEXT,
  api_key_id TEXT,
  user_pseudonym TEXT,               -- hash salé, jamais d'email en clair
  product TEXT,                      -- 'api' | 'claude_ai' | 'claude_code' | NULL
  model TEXT NOT NULL,
  tokens_in_uncached BIGINT NOT NULL DEFAULT 0,
  tokens_in_cached BIGINT NOT NULL DEFAULT 0,
  tokens_cache_write BIGINT NOT NULL DEFAULT 0,
  tokens_out BIGINT NOT NULL DEFAULT 0,
  cost_usd NUMERIC(12,4),
  snapshot_ts TIMESTAMPTZ NOT NULL,
  UNIQUE (org_id, date, source, workspace_id, api_key_id, user_pseudonym, product, model, snapshot_ts)
);

CREATE TABLE events_reco (
  reco_id UUID PRIMARY KEY,
  org_id TEXT NOT NULL REFERENCES orgs(org_id),
  ts TIMESTAMPTZ NOT NULL,
  surface TEXT NOT NULL,
  features_json JSONB NOT NULL,      -- SANS texte : features du contrat uniquement
  recommended_model TEXT NOT NULL,
  final_model TEXT,
  followed BOOLEAN,
  confidence REAL,
  rule TEXT,
  impact_wh_min REAL, impact_wh_max REAL,
  cost_eur_min REAL, cost_eur_max REAL
);

CREATE TABLE sync_runs (
  id BIGSERIAL PRIMARY KEY,
  org_id TEXT NOT NULL,
  started_at TIMESTAMPTZ NOT NULL,
  finished_at TIMESTAMPTZ,
  window_start DATE, window_end DATE,
  rows_ingested INT, status TEXT, error TEXT
);

CREATE TABLE monthly_agg (
  org_id TEXT NOT NULL,
  month DATE NOT NULL,
  dimension TEXT NOT NULL,           -- 'model' | 'workspace' | 'api_key' | 'user' | 'total'
  dim_value TEXT,
  tokens_total BIGINT,
  cost_usd NUMERIC(14,4),
  energy_wh_min NUMERIC(14,2), energy_wh_max NUMERIC(14,2),
  catalog_version TEXT NOT NULL,
  PRIMARY KEY (org_id, month, dimension, dim_value)
);
