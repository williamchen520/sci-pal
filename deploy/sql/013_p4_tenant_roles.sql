-- P4a: database-level read-only main role and tenant writer role.
-- Additive. The application keeps using the existing connection until P4b.

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'scipal_main_reader') THEN
        CREATE ROLE scipal_main_reader NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'scipal_tenant_writer') THEN
        CREATE ROLE scipal_tenant_writer NOLOGIN;
    END IF;
END
$$;

GRANT CONNECT ON DATABASE scipal_bench TO scipal_main_reader, scipal_tenant_writer;

GRANT USAGE ON SCHEMA public, catalog, library_main, library_bench TO scipal_main_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public, catalog, library_main, library_bench TO scipal_main_reader;
ALTER DEFAULT PRIVILEGES FOR ROLE scipal IN SCHEMA public
    GRANT SELECT ON TABLES TO scipal_main_reader;
ALTER DEFAULT PRIVILEGES FOR ROLE scipal IN SCHEMA catalog
    GRANT SELECT ON TABLES TO scipal_main_reader;
ALTER DEFAULT PRIVILEGES FOR ROLE scipal IN SCHEMA library_main
    GRANT SELECT ON TABLES TO scipal_main_reader;
ALTER DEFAULT PRIVILEGES FOR ROLE scipal IN SCHEMA library_bench
    GRANT SELECT ON TABLES TO scipal_main_reader;

GRANT USAGE ON SCHEMA catalog TO scipal_tenant_writer;
GRANT SELECT ON ALL TABLES IN SCHEMA catalog TO scipal_tenant_writer;

CREATE SCHEMA IF NOT EXISTS lib_ws_default AUTHORIZATION scipal;
GRANT USAGE, CREATE ON SCHEMA lib_ws_default TO scipal_tenant_writer;

COMMIT;
