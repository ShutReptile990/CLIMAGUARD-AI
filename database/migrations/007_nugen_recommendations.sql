-- Nugen output is stored as a draft. Existing approved-only RLS remains intact.
alter table public.ai_recommendations
  add column audience text check (audience in ('citizen','authority')),
  add column model_id text,
  add column inferred_at timestamptz,
  add column source_analysis jsonb,
  add column analysis_hash text;

create index ai_recommendations_draft_lookup_idx
  on public.ai_recommendations(zone_id, audience, inferred_at desc)
  where approved_at is null;

-- Existing alert publication policy still requires a second authority reviewer.
