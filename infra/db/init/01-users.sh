#!/bin/bash
# Least-privilege database accounts (runs once, on first init of the datadir).
# POSTGRES_USER/POSTGRES_PASSWORD (from the db service environment) create the
# admin role already; this script only adds the limited app role and grants.
# FAIL_SOFT: role creation is idempotent so a re-run cannot abort init.
set -eu

psql -v ON_ERROR_STOP=0 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'omniwatch_app') THEN
            CREATE ROLE omniwatch_app LOGIN PASSWORD '${OMNIWATCH_APP_PASSWORD}';
        END IF;
    END
    \$\$;

    GRANT ALL ON SCHEMA public TO ${POSTGRES_USER};
    ALTER SCHEMA public OWNER TO ${POSTGRES_USER};
    ALTER ROLE omniwatch_app SET search_path TO public;
EOSQL

echo "init-users: app role ready"
