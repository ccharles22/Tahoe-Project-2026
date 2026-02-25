# Database setup (Tailscale)

This page is an operational checklist for exposing a local PostgreSQL server to teammates over Tailscale.

## Install and start PostgreSQL

```bash
brew install postgresql
brew services start postgresql@18
psql --version
```

## Create local DB user and database

```bash
createuser <DB_ADMIN_USER> --pwprompt
psql -d postgres -c "ALTER ROLE <DB_ADMIN_USER> CREATEDB;"
createdb -O <DB_ADMIN_USER> bio727p_group_project
psql -U <DB_ADMIN_USER> -d bio727p_group_project -h localhost
```

## Install and start Tailscale

```bash
brew install --formula tailscale
sudo brew services start tailscale
sudo tailscale up
tailscale status
tailscale ip -4
```

Save the IPv4 address; teammates will connect using this host.

## Configure PostgreSQL to listen externally

Find config paths:

```bash
psql -d postgres -c "SHOW config_file;"
psql -d postgres -c "SHOW hba_file;"
```

Edit `postgresql.conf`:

```conf
listen_addresses = '*'
```

Edit `pg_hba.conf` and add:

```conf
# Local
local   all             all                                     trust
host    all             all             127.0.0.1/32            scram-sha-256
host    all             all             ::1/128                 scram-sha-256

# Tailscale network
host    all             all             100.64.0.0/10           scram-sha-256
```

Restart and verify:

```bash
brew services restart postgresql@18
psql -d postgres -c "SHOW listen_addresses;"
lsof -nP -iTCP:5432 -sTCP:LISTEN
```

## Set password for host user

```sql
ALTER ROLE <DB_ADMIN_USER> WITH PASSWORD '<PASSWORD>';
```

## Create team role and grant privileges

```sql
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bio727p_role') THEN
    CREATE ROLE bio727p_role NOLOGIN;
  END IF;
END $$;

GRANT CONNECT ON DATABASE bio727p_group_project TO bio727p_role;
GRANT USAGE ON SCHEMA public TO bio727p_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO bio727p_role;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO bio727p_role;
```

Set default privileges for future objects:

```sql
ALTER DEFAULT PRIVILEGES FOR ROLE <DB_ADMIN_USER> IN SCHEMA public
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO bio727p_role;

ALTER DEFAULT PRIVILEGES FOR ROLE <DB_ADMIN_USER> IN SCHEMA public
GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO bio727p_role;
```

## Create individual teammate users

```sql
CREATE USER <TEAMMATE_USER> WITH PASSWORD '<TEAMMATE_PASSWORD>';
GRANT bio727p_role TO <TEAMMATE_USER>;
ALTER ROLE <TEAMMATE_USER> LOGIN;
```

## Connection test

```bash
psql "postgresql://<TEAMMATE_USER>:<TEAMMATE_PASSWORD>@<TAILSCALE_IP>:5432/bio727p_group_project"
```

## Grant permissions for materialized views

If teammates need read access to the bonus materialized views:

```sql
GRANT SELECT ON MATERIALIZED VIEW mv_activity_landscape TO bio727p_role;
GRANT SELECT ON MATERIALIZED VIEW mv_domain_mutation_enrichment TO bio727p_role;
```

If teammates should run the refresh helper too:

```sql
GRANT EXECUTE ON FUNCTION refresh_bonus_materialized_views() TO bio727p_role;
```

If refresh fails for non-owners, run refresh as the DB owner account or convert the function to `SECURITY DEFINER` with a safe `search_path`.

## Security notes

- Do not commit passwords or full connection strings to Git.
- Rotate shared credentials regularly.
- Prefer per-user credentials over a shared login.
