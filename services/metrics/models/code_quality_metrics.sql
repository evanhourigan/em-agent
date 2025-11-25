-- Code Quality Metrics: Track code coverage and quality gate status over time
-- Aggregates data from Codecov and SonarQube

WITH codecov_coverage AS (
  SELECT
    received_at,
    payload::json->'commit'->>'commitid' AS commit_sha,
    payload::json->'repo'->>'name' AS repo_name,
    (payload::json->'coverage'->>'coverage')::NUMERIC AS coverage_pct,
    payload::json->'coverage'->>'diff' AS coverage_diff
  FROM public.events_raw
  WHERE source = 'codecov'
    AND event_type = 'coverage'
    AND payload::json->'coverage'->>'coverage' IS NOT NULL
),
sonarqube_quality AS (
  SELECT
    received_at,
    payload::json->'project'->>'key' AS project_key,
    payload::json->'project'->>'name' AS project_name,
    payload::json->'qualityGate'->>'status' AS quality_gate_status,
    (payload::json->'qualityGate'->'conditions'->0->>'value')::NUMERIC AS bugs,
    (payload::json->'qualityGate'->'conditions'->1->>'value')::NUMERIC AS vulnerabilities,
    (payload::json->'qualityGate'->'conditions'->2->>'value')::NUMERIC AS code_smells
  FROM public.events_raw
  WHERE source = 'sonarqube'
    AND event_type LIKE 'quality_gate_%'
),
combined_metrics AS (
  -- Codecov metrics
  SELECT
    date_trunc('week', received_at) AS week,
    'codecov' AS source,
    repo_name AS project,
    AVG(coverage_pct) AS avg_coverage,
    MAX(coverage_pct) AS max_coverage,
    MIN(coverage_pct) AS min_coverage,
    NULL::TEXT AS quality_status
  FROM codecov_coverage
  GROUP BY 1, 2, 3

  UNION ALL

  -- SonarQube metrics
  SELECT
    date_trunc('week', received_at) AS week,
    'sonarqube' AS source,
    project_name AS project,
    NULL::NUMERIC AS avg_coverage,
    NULL::NUMERIC AS max_coverage,
    NULL::NUMERIC AS min_coverage,
    quality_gate_status AS quality_status
  FROM sonarqube_quality
  GROUP BY 1, 2, 3, quality_gate_status
)
SELECT
  week,
  source,
  project,
  avg_coverage,
  max_coverage,
  min_coverage,
  quality_status,
  COUNT(*) AS event_count
FROM combined_metrics
GROUP BY 1, 2, 3, 4, 5, 6, 7
ORDER BY 1 DESC, 2, 3
