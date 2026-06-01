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
--   IMPORTANTE: re-correr este script despues de cualquier migracion que
--   agregue tablas nuevas. RLS (y los REVOKE de la Parte 2) solo cubren las
--   tablas que existen al momento de correrlo.
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


-- ============================================================================
-- PARTE 2 (OPCIONAL) - Defensa en profundidad
-- ============================================================================
-- RLS sin policies ya bloquea a anon/authenticated. Esto es belt-and-suspenders:
-- ademas quita los GRANT de los roles del API REST de Supabase (anon,
-- authenticated), porque las tablas Django no se exponen por PostgREST.
-- Es seguro: Django usa su propio rol (el de DATABASE_URL), no estos.
-- Si prefieres lo minimo, no corras esta seccion (revertible con la Parte 2
-- de enable_rls_revert.sql).

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        EXECUTE 'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon';
        EXECUTE 'REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon';
        RAISE NOTICE 'grants revocados a anon';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        EXECUTE 'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM authenticated';
        EXECUTE 'REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM authenticated';
        RAISE NOTICE 'grants revocados a authenticated';
    END IF;
END $$;
