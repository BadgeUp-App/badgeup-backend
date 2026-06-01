-- BadgeUp - REVERTIR Row-Level Security en todas las tablas public
--
-- Solo usar si Django empieza a fallar despues de aplicar enable_rls.sql.
-- Significa que el user de DATABASE_URL no tiene BYPASSRLS.

DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN (
        SELECT tablename
        FROM pg_tables
        WHERE schemaname = 'public'
    )
    LOOP
        EXECUTE format('ALTER TABLE public.%I DISABLE ROW LEVEL SECURITY', r.tablename);
        RAISE NOTICE 'RLS disabled on: %', r.tablename;
    END LOOP;
END $$;

SELECT
    tablename,
    CASE WHEN rowsecurity THEN 'ENABLED' ELSE 'DISABLED' END AS rls_status
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY tablename;


-- ============================================================================
-- PARTE 2 (OPCIONAL) - Solo si corriste la seccion de REVOKE en enable_rls.sql
-- ============================================================================
-- Restaura los grants estandar de Supabase. OJO: con RLS deshabilitado + grants
-- restaurados vuelves al estado inseguro original. Usar solo para diagnosticar.

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO anon';
        EXECUTE 'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO anon';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO authenticated';
        EXECUTE 'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO authenticated';
    END IF;
END $$;
