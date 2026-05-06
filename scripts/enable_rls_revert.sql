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
