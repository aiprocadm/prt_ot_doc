#!/bin/bash
# SEC-65: create the unprivileged application role on first cluster init.
#
# The postgres image runs this once, on an empty data directory, as the bootstrap
# superuser. Row-level security is ignored for SUPERUSER/BYPASSRLS roles, so the
# runtime must not connect as ${POSTGRES_USER} — it connects as ${APP_DB_USER}
# created here, while Alembic keeps using the owner role via MIGRATION_DATABASE_URL.
#
# For an EXISTING cluster (this hook will not fire) run instead:
#   PYTHONPATH=backend python scripts/provision_app_role.py --role "$APP_DB_USER" \
#       --password "$APP_DB_PASSWORD"
set -euo pipefail

APP_DB_USER="${APP_DB_USER:-ptd_app}"

if [[ -z "${APP_DB_PASSWORD:-}" ]]; then
  echo "SEC-65: APP_DB_PASSWORD is not set — skipping application role creation." >&2
  echo "SEC-65: the runtime would fall back to the bootstrap superuser and RLS would be inert." >&2
  exit 0
fi

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-SQL
	DO \$\$
	BEGIN
	    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${APP_DB_USER}') THEN
	        ALTER ROLE "${APP_DB_USER}" WITH LOGIN NOSUPERUSER NOBYPASSRLS
	            NOCREATEDB NOCREATEROLE PASSWORD '${APP_DB_PASSWORD}';
	    ELSE
	        CREATE ROLE "${APP_DB_USER}" WITH LOGIN NOSUPERUSER NOBYPASSRLS
	            NOCREATEDB NOCREATEROLE PASSWORD '${APP_DB_PASSWORD}';
	    END IF;
	END
	\$\$;

	GRANT CONNECT, CREATE ON DATABASE "${POSTGRES_DB}" TO "${APP_DB_USER}";
	GRANT USAGE ON SCHEMA public TO "${APP_DB_USER}";
	GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "${APP_DB_USER}";
	GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "${APP_DB_USER}";
	-- Tables created later by Alembic (running as the owner role).
	ALTER DEFAULT PRIVILEGES FOR ROLE "${POSTGRES_USER}" IN SCHEMA public
	    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "${APP_DB_USER}";
	ALTER DEFAULT PRIVILEGES FOR ROLE "${POSTGRES_USER}" IN SCHEMA public
	    GRANT USAGE, SELECT ON SEQUENCES TO "${APP_DB_USER}";
SQL

echo "SEC-65: application role ${APP_DB_USER} created (NOSUPERUSER NOBYPASSRLS)."
