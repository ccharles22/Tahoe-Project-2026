# PostgreSQL + Tailscale methodology

This page documents a repeatable pattern for hosting the project database on one machine and granting access to collaborators over Tailscale.

For copy-paste setup commands, use the companion page: `Database setup (Tailscale)`.

## Architecture summary

- Host machine runs PostgreSQL.
- Host joins Tailscale and exposes port `5432` only to tailnet peers.
- Collaborators connect using personal DB credentials.

## Host bootstrap

### Install services

```bash
brew install postgresql
brew install --formula tailscale
brew services start postgresql@18
sudo brew services start tailscale
sudo tailscale up
```

### Verify host state

```bash
psql --version
tailscale ip -4
tailscale status
```

## PostgreSQL network configuration

Find config files:

```bash
psql -d postgres -c "SHOW config_file;"
psql -d postgres -c "SHOW hba_file;"
```

Set in `postgresql.conf`:

```conf
listen_addresses = '*'
```

Add in `pg_hba.conf`:

```conf
host    all             all             100.64.0.0/10           scram-sha-256
host    replication     repl_user       100.64.0.0/10           scram-sha-256
```

Restart:

```bash
brew services restart postgresql@18
```

## Access management pattern

Use one no-login role for permissions and grant that role to each teammate account.

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

Create one account per teammate:

```sql
CREATE USER <TEAMMATE_USER> WITH PASSWORD '<TEAMMATE_PASSWORD>';
GRANT bio727p_role TO <TEAMMATE_USER>;
```

### Materialized view permissions

Grant read access to bonus materialized views:

```sql
GRANT SELECT ON MATERIALIZED VIEW mv_activity_landscape TO bio727p_role;
GRANT SELECT ON MATERIALIZED VIEW mv_domain_mutation_enrichment TO bio727p_role;
```

Grant permission for the refresh helper:

```sql
GRANT EXECUTE ON FUNCTION refresh_bonus_materialized_views() TO bio727p_role;
```

Note: materialized view refresh usually requires ownership. If collaborators cannot refresh, run refresh as owner or harden the function with `SECURITY DEFINER`.

## Optional logical replication setup

### Publisher settings

```sql
ALTER SYSTEM SET wal_level = 'logical';
ALTER SYSTEM SET max_wal_senders = 10;
ALTER SYSTEM SET max_replication_slots = 10;
```

Restart and verify:

```bash
brew services restart postgresql@18
psql -d postgres -c "SHOW wal_level;"
psql -d postgres -c "SHOW max_wal_senders;"
psql -d postgres -c "SHOW max_replication_slots;"
```

Create replication user:

```sql
DROP ROLE IF EXISTS repl_user;
CREATE ROLE repl_user WITH LOGIN PASSWORD '<REPL_PASSWORD>' REPLICATION;
GRANT CONNECT ON DATABASE bio727p_group_project TO repl_user;
GRANT USAGE ON SCHEMA public TO repl_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO repl_user;
```

Create publication:

```sql
DROP PUBLICATION IF EXISTS bio_pub;
CREATE PUBLICATION bio_pub FOR TABLE users, wild_type_proteins, protein_features, experiments, generations, variants, mutations, metrics, experiment_metadata;
```

## Validation checklist

```bash
psql "postgresql://<USER>:<PASSWORD>@<TAILSCALE_IP>:5432/bio727p_group_project" -c "select 1;"
psql -d postgres -c "\du"
psql -d postgres -c "\l"
```

## Operational cautions

- Keep `pg_hba.conf` restricted to `100.64.0.0/10`, not `0.0.0.0/0`.
- Use strong passwords and rotate them.
- Prefer per-user accounts; avoid shared human logins.
