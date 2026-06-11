-- =============================================================================
-- Supabase security remediation — Kwabo (project ynvzwbtxqejthgcsxyiv)
-- Fixes the two CRITICAL advisor findings:
--   * rls_disabled_in_public     — public tables readable via the anon API
--   * sensitive_columns_exposed  — oauth_tokens / oauth_config = live creds
--
-- WHY THIS IS SAFE for this app:
--   * The backend talks to Postgres over a DIRECT connection (DATABASE_URL) as
--     the table-owner `postgres` role. Table owners BYPASS non-forced RLS, so
--     enabling RLS does NOT affect the app's reads/writes.
--   * The frontend uses NO supabase-js — it calls the FastAPI backend only.
--   * Nothing legitimate uses the PostgREST/anon data API. Enabling RLS with no
--     policies therefore denies the anon API (zero rows) and changes nothing
--     for the app.
--
-- Run this in: Supabase Dashboard -> SQL Editor -> New query -> Run.
-- Idempotent: safe to run repeatedly.
-- =============================================================================

-- 1) Enable RLS on EVERY base table in `public` (present + future-proof sweep).
do $$
declare
  r record;
begin
  for r in
    select tablename
    from pg_tables
    where schemaname = 'public'
  loop
    execute format('alter table public.%I enable row level security', r.tablename);
  end loop;
end $$;

-- 2) Defense-in-depth for the credential tables: even with RLS on (which already
--    blocks row access), strip the default API grants so anon/authenticated have
--    no privileges on them at all. Service-role (server-side, secret) still works.
revoke all on table public.oauth_tokens  from anon, authenticated;
revoke all on table public.oauth_config  from anon, authenticated;

-- 3) Verify: every public table should now show rowsecurity = true.
select
  c.relname              as table_name,
  c.relrowsecurity       as rls_enabled,
  c.relforcerowsecurity  as rls_forced
from pg_class c
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public'
  and c.relkind = 'r'
order by c.relrowsecurity asc, c.relname;
-- Expected: rls_enabled = true for ALL rows. rls_forced stays false on purpose,
-- so the app's owner connection keeps bypassing RLS.
