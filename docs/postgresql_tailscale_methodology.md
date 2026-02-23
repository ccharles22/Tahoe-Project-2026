# ON MACBOOK
# PostgreSQL installation via Homebrew
brew install postgresql  #installing the latest version 
brew services start postgresql@18
brew services list #see what as started 

psql postgres #initialise the database cluster 

# it is possible to stop postgresql 
#brew services stop
psql --version #to visualize that the psql version is the correct one

# create my own database user
createuser <USERNAME> –pwprompt 

psql -d postgres -c "ALTER ROLE <USERNAME> CREATEDB;" #these represent the permission to be able to create databases

# create database and visualize it
createdb -O <USERNAME> bio727p_group_project

psql -U <USERNAME> -d bio727p_group_project -h localhost

psql -d postgres -c "\du"
psql -d postgres -c "\l"


##############################################################################


# SETTING UP A SHARED ENVIRONMENT FOR THE SQL DATABASE, CONSIDERING IT IS ALREADY ON MY MAC (TERMINAL): Tailscale + Postgres listen on Tailscale IP

# 1. Tailscale installation from homebrew
brew install --formula tailscale
sudo brew services start tailscale #mac password
sudo tailscale up 
# to authenticate visit: https://login.tailscale.com/a/133fa7b601de0a
# completed through github
sudo tailscale status #visualisation of all the details

# 2. Finding the Timescale IP on my mac
tailscale ip -4
# this is the IP that everybody in the team will use

# 3. Find PostgreSQL config files
psql -d postgres -c "SHOW config_file;"
# /opt/homebrew/var/postgresql@18/postgresql.conf
psql -d postgres -c "SHOW hba_file;"
# /opt/homebrew/var/postgresql@18/pg_hba.conf

# 4. Allow Postgres to listen on Tailscale
nano /opt/homebrew/var/postgresql@18/postgresql.conf
# find the line # listen_addresses = 'localhost'
# change the line to listen_addresses = '*'

# 5. Allow teammates to connect (authentication)
nano /opt/homebrew/var/postgresql@18/pg_hba.conf
Add this at the bottom lines: 
# TYPE  DATABASE        USER            ADDRESS                 METHOD
# Local socket connections
local   all             all                                     trust
# IPv4 localhost
host    all             all             127.0.0.1/32            scram-sha-256
# IPv6 localhost
host    all             all             ::1/128                 scram-sha-256
# Allow Tailscale network (teammates)
host    all             all             100.64.0.0/10           scram-sha-256
# Replication (leave as-is)
local   replication     all                                     trust
host    replication     all             127.0.0.1/32            trust
host    replication     all             ::1/128                 trust

# 6. Make sure my DB user has a password
psql postgres
alter role <USERNAME> with password '<PASSWORD>';
\q

# 7. Restart PostgreSQL
brew services restart postgresql@18
psql -d postgres -c "SHOW listen_addresses;"
lsof -nP -iTCP:5432 -sTCP:LISTEN

# 8. Testing the machine
psql -h 100.80.183.102 -U <HOST-USERNAME> -d bio727p_group_project 

# 9. Improvements in sql language
psql -d postgres -v on_error_stop=1 <<'sql'
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'bio727p_team') then
    create role bio727p_team with login password 'mysql';
  end if;
end$$;
grant connect on database bio727p_group_project to bio727p_team;
sql

psql -d bio727p_group_project -v on_error_stop=1 <<'sql'
grant usage on schema public to bio727p_team;
grant select, insert, update, delete on all tables in schema public to bio727p_team;
grant usage, select, update on all sequences in schema public to bio727p_team;
alter default privileges in schema public
grant select, insert, update, delete on tables to bio727p_team;
alter default privileges in schema public
grant usage, select, update on sequences to bio727p_team;
sql
# this allows the team to be able to view, add, edit and delete data

# check everything worked well
psql -d postgres -c "\du" #check the team user exists (bio727p_team)
psql -d postgres -c "\l" # Check the team user can access your database
### testing
psql "postgresql://bio727p_team:<DATABASE PASSWORD>@<HOST>:5432/bio727p_group_project"



# IMPORTANT!
# EACH STUDENT NEEDS TO HAVE THEIR OWN ACCOUNT TO ACCESS THE DATABASE
# connecting as database admin
psql postgres
\c bio727p_group_project
\du #understanding the roles within the database

# Creating a shared permission role for each teammate
# ensuring the role exists
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'bio727p_role') then
    create role bio727p_role nologin;
  end if;
end$$;

# allow connections and schema usage
grant connect on database bio727p_group_project to bio727p_role;
grant usage on schema public to bio727p_role;

# existing objects
grant select, insert, update, delete on all tables in schema public to bio727p_role;
grant usage, select, update on all sequences in schema public to bio727p_role;

# future objects created by me
alter default privileges for role mariapaolaluciani in schema public
grant select, insert, update, delete on tables to bio727p_role;

alter default privileges for role mariapaolaluciani in schema public
grant usage, select, update on sequences to bio727p_role;


# create a user for each team member
CREATE USER <TEAMMATE-USERNAME> WITH PASSWORD '<TEAMMATE-PASSWORD>';
GRANT bio727p_role TO <TEAMMATE-USERNAME>;


###############################################################################


## *IMPLEMENTATION OF AUTOMATIC SYNCHRONIZATION TO MAINTAIN A LOCAL COPY OF THE DATA
psql "host=<HOST-IP> port=5432 dbname=bio727p_group_project user=repl_user password=local" -c "select 1;" 


### PUBLISHER (SERVER)
ALTER SYSTEM SET wal_level = 'logical';
ALTER SYSTEM SET max_wal_senders = 10;
ALTER SYSTEM SET max_replication_slots = 10;

brew services restart postgresql@18 #restart to allow changes to occur

# verify
SHOW wal_level;
SHOW max_wal_senders;
SHOW max_replication_slots;
SHOW listen_addresses;
SHOW port;

# EDIT PG_PUBLICATIOS CONF
nano /opt/homebrew/var/postgresql@18/pg_hba.conf
# Allow logical replication connections from Tailscale
host    replication     repl_user    100.64.0.0/10    scram-sha-256
# Allow normal connections from Tailscale
host    bio727p_group_project   all  100.64.0.0/10    scram-sha-256

# restart
brew services restart postgresql@18

# create a dedicated replication user on the publisher
DROP ROLE IF EXISTS repl_user;
CREATE ROLE repl_user WITH LOGIN PASSWORD 'local' REPLICATION;

GRANT CONNECT ON DATABASE bio727p_group_project TO repl_user;
GRANT USAGE ON SCHEMA public TO repl_user;

# needed for initial manual COPY
GRANT SELECT ON ALL TABLES IN SCHEMA public TO repl_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO repl_user;

# on publisher, create and verify publication
DROP PUBLICATION IF EXISTS bio_pub;

CREATE PUBLICATION bio_pub
FOR TABLE
  users,
  wild_type_proteins,
  protein_features,
  experiments,
  generations,
  variants,
  mutations,
  metrics,
  experiment_metadata;
# no wild type control and metrics definitions

# verify
SELECT tablename
FROM pg_publication_tables
WHERE pubname='bio_pub'
ORDER BY tablename;
# should all be there!


### SUBSCRIBER (LOCAL CONNECTION)
\c bio727p_group_project_local
ALTER SUBSCRIPTION bio_sub DISABLE;
DROP SUBSCRIPTION bio_sub;

# add initial schema and data (on the terminal)
# schema
pg_dump -h <HOST-IP> -U <HOST-USERNAME> -d bio727p_group_project --schema-only > published_schema.sql
psql -d bio727p_group_project_local -f published_schema.sql
# data
pg_dump -h <HOST-IP> -U <HOST-USERNAME> -d bio727p_group_project --data-only --inserts > published_data.sql
psql -d bio727p_group_project_local -f published_data.sql

# check
psql -d bio727p_group_project_local -c "\dt public.*"


# now back to the subscriber
psql -d bio727p_group_project_local

# subscription is created but not connected
DROP SUBSCRIPTION IF EXISTS bio_sub;
CREATE SUBSCRIPTION bio_sub
CONNECTION 'host=<HOST-IP> port=5432 dbname=bio727p_group_project user=repl_user password=<PASSWORD>'
PUBLICATION bio_pub
WITH (copy_data=false, create_slot=false, enabled=false, connect=false);

# enable and refresh subscription
ALTER SUBSCRIPTION bio_sub SET (slot_name='bio_sub');
ALTER SUBSCRIPTION bio_sub ENABLE;
ALTER SUBSCRIPTION bio_sub REFRESH PUBLICATION;


### BACK ON THE PUBLISHER
# create create the logical slot (output) on publisher
SELECT pg_create_logical_replication_slot('bio_sub', 'pgoutput');

# and confirm
SELECT slot_name, plugin, database, active
FROM pg_replication_slots
WHERE slot_name='bio_sub';
# f until the subscriber connects


#### CHECKING THE CONNECTION
# subscriber
SELECT subname, subenabled, subslotname
FROM pg_subscription;
SELECT subname, worker_type, pid, last_msg_receipt_time, latest_end_lsn
FROM pg_stat_subscription;

# publisher
SELECT pid, usename, client_addr, state, application_name
FROM pg_stat_replication;
SELECT slot_name, active, active_pid
FROM pg_replication_slots
WHERE slot_name='bio_sub';
# t in both so it connected!!!

# important trigger checks on the subscriber
ALTER TABLE public.users ENABLE TRIGGER ALL;
ALTER TABLE public.experiments ENABLE TRIGGER ALL;
ALTER TABLE public.metrics ENABLE TRIGGER ALL;

SET session_replication_role = DEFAULT;

# the operating model: all writes happen on the publisher, the subscriber is read only, as it is a local replica