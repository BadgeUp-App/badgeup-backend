-- BadgeUp - Habilitar Row-Level Security en todas las tablas public
--
-- Contexto:
--   Supabase Security Advisor flagueo CRITICAL:
--     - rls_disabled_in_public
--     - sensitive_columns_exposed
--   Las tablas Django en schema public estan expuestas via Supabase REST API
--   con anon key. Sin RLS, cualquiera con la URL + anon key puede leer/editar.
--
-- Que hace este script:
--   Habilita RLS en TODAS las tablas del schema public sin crear policies.
--   Esto bloquea cualquier acceso vía API REST (anon o authenticated).
--   Django sigue funcionando porque su DATABASE_URL usa el postgres user
--   que tiene BYPASSRLS automaticamente.
--
-- Como correr:
--   1. Supabase Dashboard > SQL Editor > New query
--   2. Pegar este archivo completo
--   3. Click Run
--   4. Verificar que las 2 alertas CRITICAL desaparecen del Security Advisor
--
-- Como revertir (si Django se rompe):
--   Correr enable_rls_revert.sql

DO $$
DECLARE
    r RECORD;
    enabled_count INT := 0;
BEGIN
    FOR r IN (
        SELECT tablename
        FROM pg_tables
        WHERE schemaname = 'public'
        ORDER BY tablename
    )
    LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', r.tablename);
        enabled_count := enabled_count + 1;
        RAISE NOTICE 'RLS enabled on: %', r.tablename;
    END LOOP;
    RAISE NOTICE 'TOTAL: RLS enabled on % tables', enabled_count;
END $$;

-- Verificacion final
SELECT
    tablename,
    CASE WHEN rowsecurity THEN 'ENABLED' ELSE 'DISABLED' END AS rls_status
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY tablename;
