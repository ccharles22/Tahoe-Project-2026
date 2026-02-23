### PostgreSQL installation via Homebrew
brew install postgresql #installing the newest version
brew services start postgresql@18
brew services list #see what’s started

psql postgres  #initialise the database cluster

## brew services stop postgresql #stopping
psql --version   


# create my own detabase user
createuser mariapaolaluciani –pwprompt #mysql is the password

psql -d postgres -c "ALTER ROLE mariapaolaluciani CREATEDB;" #these represent the permission to be able to create databases

# create database and visualize it
createdb -O mariapaolaluciani bio727p_group_project

psql -U mariapaolaluciani -d bio727p_group_project -h localhost

psql -d postgres -c "\du"
psql -d postgres -c "\l"




### SETTING UP A SHARED ENVIRONMENT FOR THE SQL DATABASE, CONSIDERING IT IS ALREADY ON MY MAC (TERMINAL): Tailscale + Postgres listen on Tailscale IP
## This makes your Mac behave like it’s on the same private LAN as your teammates. No router port forwarding, no public exposure.

# 1.	Tailscale installation from homebrew
 brew install --formula tailscale
sudo brew services start tailscale #mac password
 sudo tailscale up 
#to authenticate visit: https://login.tailscale.com/a/133fa7b601de0a
#completed through github

sudo tailscale status #visualisation of all the details

# each teammate also needs to download timescale on their laptop
#Everyone logs into the same Tailscale “tailnet” (same account/org)

# 2.	Finding the Timescale IP on my mac
tailscale ip -4

#this is the IP that everybody in the team will use

c

# 3.	Find PostgreSQL config files
psql -d postgres -c "SHOW config_file;"
# /opt/homebrew/var/postgresql@18/postgresql.conf

psql -d postgres -c "SHOW hba_file;"
# /opt/homebrew/var/postgresql@18/pg_hba.conf

# 4.	Allow Postgres to listen on Tailscale
nano /opt/homebrew/var/postgresql@18/postgresql.conf
# find the line #listen_addresses = 'localhost'
# change the line to listen_addresses = '*'
# and remember to remove # in front of it

# save: CTRL+O → Enter → CTRL+X

# 5.	Allow teammates to connect (authentication)
nano /opt/homebrew/var/postgresql@18/pg_hba.conf
# Add this at the bottom lines: 
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

# save: CTRL+O → Enter → CTRL+X

# 6.	Make sure my DB user has a password
psql postgres
alter role mariapaolaluciani with password '<PASSWORD>';
\q

# 7.	Restart PostgreSQL
brew services restart postgresql@18

psql -d postgres -c "SHOW listen_addresses;"
lsof -nP -iTCP:5432 -sTCP:LISTEN

# 8.	Testing the machine
psql -h 100.80.183.102 -U mariapaolaluciani -d bio727p_group_project 

# 9.	What everybody needs to put in flask
postgresql://mariapaolaluciani:mysql@100.110.34.96:5432/bio727p_group_project

postgresql://mariapaolaluciani:mysql@100.110.34.96:5432/bio727p_group_project

# or directly in the terminal: 
psql "postgresql://mariapaolaluciani:mysql@100.110.34.96:5432/bio727p_group_project"


###################### 

# EACH STUDENT GETS THEIR OWN USERNAME AND PASSWORD FOR CONNECTION
# Connecting as database admin
psql postgres
\c bio727p_group_project

\du #understanding the roles within the database

# Creating a shared permission role for each teammate
# ensuring the role exists
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bio727p_role') THEN
    CREATE ROLE bio727p_role NOLOGIN;
  END IF;
END$$;  


# allow connections and schema usage
GRANT CONNECT ON DATABASE bio727p_group_project TO bio727p_role;
GRANT USAGE ON SCHEMA public TO bio727p_role;


# existing objects
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO bio727p_role;
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO bio727p_role;


# future objects created by me 
ALTER DEFAULT PRIVILEGES FOR ROLE mariapaolaluciani IN SCHEMA public
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO bio727p_role;

ALTER DEFAULT PRIVILEGES FOR ROLE mariapaolaluciani IN SCHEMA public
GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO bio727p_role;

# create a user for each teammate:
# -	Reman
CREATE USER rp1284 WITH PASSWORD 'potato';
GRANT bio727p_role TO rp1284;

# changing login options, considering bio727p_role does not allow to login 
ALTER ROLE rp1284 LOGIN;
ALTER ROLE rp1284 WITH PASSWORD 'potato';
GRANT bio727p_role TO rp1284;

psql "postgresql://rp1284:potato@100.80.183.102:5432/bio727p_group_project"

# -	Luke
CREATE USER lukeoakarr WITH PASSWORD 'lukeoakarr17';
GRANT bio727p_role TO lukeoakarr;

# changing login options, considering bio727p_role does not allow to login 
ALTER ROLE lukeoakarr LOGIN;
ALTER ROLE lukeoakarr WITH PASSWORD 'lukeoakarr17';
GRANT bio727p_role TO lukeoakarr;

psql "postgresql://lukeoakarr:lukeoakarr17@100.80.183.102:5432/bio727p_group_project"


# -	Candice
CREATE USER candicecharles WITH PASSWORD 'Candy22';
GRANT bio727p_role TO candicecharles;

psql "postgresql://candicecharles:Candy22@100.80.183.102:5432/bio727p_group_project" 

# -	Patricia
CREATE USER patriciaosire WITH PASSWORD 'blue';
GRANT bio727p_role TO patriciaosire;

psql "postgresql://patriciaosire:blue@100.80.183.102:5432/bio727p_group_project"


# checking granted permissions
SELECT rolname, rolcanlogin
FROM pg_roles
WHERE rolname IN ('rp1284','bio727p_role','mariapaolaluciani','lukeoakarr', 'candicecharles','patriciaosire');


#######################

## **IMPLEMENTATION OF AUTOMATIC SYNCHRONIZATION TO MAINTAIN A LOCAL COPY OF THE DATA
psql "host=100.80.183.102 port=5432 dbname=bio727p_group_project user=repl_user password=local" -c "select 1;" #

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

# -- needed for initial manual COPY
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
# all there!


### SUBSCRIBER (LOCAL)
\c bio727p_group_project_local
ALTER SUBSCRIPTION bio_sub DISABLE;
DROP SUBSCRIPTION bio_sub;

# add initial schema and data (on the terminal)
# schema
pg_dump -h 100.80.183.102 -U mariapaolaluciani -d bio727p_group_project --schema-only > published_schema.sql
psql -d bio727p_group_project_local -f published_schema.sql

# data
pg_dump -h 100.80.183.102 -U mariapaolaluciani -d bio727p_group_project --data-only --inserts > published_data.sql
psql -d bio727p_group_project_local -f published_data.sql

# check
psql -d bio727p_group_project_local -c "\dt public.*"
#all good


# now back to the subscriber
psql -d bio727p_group_project_local

# subscription is created but not connected
DROP SUBSCRIPTION IF EXISTS bio_sub;
CREATE SUBSCRIPTION bio_sub
CONNECTION 'host=100.80.183.102 port=5432 dbname=bio727p_group_project user=repl_user password=local'
PUBLICATION bio_pub
WITH (copy_data=false, create_slot=false, enabled=false, connect=false);

# enable and refresh subscription
ALTER SUBSCRIPTION bio_sub SET (slot_name='bio_sub');
ALTER SUBSCRIPTION bio_sub ENABLE;
ALTER SUBSCRIPTION bio_sub REFRESH PUBLICATION;


### BACK ON THE PUBLISHER
# reate create the logical slot (output) on publisher
SELECT pg_create_logical_replication_slot('bio_sub', 'pgoutput');

# and confirm
SELECT slot_name, plugin, database, active
FROM pg_replication_slots
WHERE slot_name='bio_sub';
# f until the subscriber connects


#### CHECKING THE CONNECTION
#subscriber
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

## ***
# Files moved to the schema folder
mv published_data.sql schema/
mv published_schema.sql schema/

# send it into github