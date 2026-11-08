-- P4c: tenant_writer reads main, writes only tenant schema.

BEGIN;

GRANT USAGE ON SCHEMA public, catalog, library_main, library_bench TO scipal_tenant_writer;
GRANT SELECT ON ALL TABLES IN SCHEMA public, catalog, library_main, library_bench TO scipal_tenant_writer;

ALTER DEFAULT PRIVILEGES FOR ROLE scipal IN SCHEMA public
    GRANT SELECT ON TABLES TO scipal_tenant_writer;
ALTER DEFAULT PRIVILEGES FOR ROLE scipal IN SCHEMA catalog
    GRANT SELECT ON TABLES TO scipal_tenant_writer;
ALTER DEFAULT PRIVILEGES FOR ROLE scipal IN SCHEMA library_main
    GRANT SELECT ON TABLES TO scipal_tenant_writer;
ALTER DEFAULT PRIVILEGES FOR ROLE scipal IN SCHEMA library_bench
    GRANT SELECT ON TABLES TO scipal_tenant_writer;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA lib_ws_default TO scipal_tenant_writer;
ALTER DEFAULT PRIVILEGES FOR ROLE scipal IN SCHEMA lib_ws_default
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO scipal_tenant_writer;

COMMIT;
