-- EXTENSIONS
CREATE EXTENSION IF NOT EXISTS citext;


-- TRIGGER FUNCTIONS
create or replace function set_updated_at()
returns trigger as $$
begin
    new.updated_at = current_timestamp;
    return new;
end;
$$ language plpgsql;


-- TABLES
-- 1. Users
CREATE TABLE users (
  user_id       bigserial PRIMARY KEY,
  username      citext UNIQUE NOT NULL,
  email         citext UNIQUE NOT NULL,
  password_hash text  NOT NULL,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);
-- using citext unique will automatically create indexes
create trigger trg_users_updated_at
before update on users
for each row
execute function set_updated_at();
-- passwords are not visible into the database,


-- 2. Wild-type proteins and plasmids (WT-proteins info and plasmids FASTA sequences- from Uniprot)
create table wild_type_proteins (
    wt_id bigserial primary key,
    user_id bigint not null,
    uniprot_id varchar(20) not null,
    protein_name varchar(255),
    organism varchar(255),
    amino_acid_sequence text not null,
    sequence_length int not null,
    plasmid_name varchar(255),
    plasmid_sequence text not null,
    created_at timestamptz default now(),
    foreign key (user_id) references users(user_id) on delete cascade,
    unique (uniprot_id, user_id)
);

create index idx_wt_user on wild_type_proteins (user_id);


-- 3.Protein Feature table (from Uniprot)
create table protein_features (
    feature_id bigserial primary key,
    wt_id bigint not null,
    feature_type varchar(100) not null,
    description text,
    start_position int not null check (start_position > 0),
    end_position int not null check (end_position >= start_position),
    foreign key (wt_id) references wild_type_proteins(wt_id) on delete cascade
);

create index idx_feature_wt on protein_features (wt_id);
create index idx_feature_type on protein_features (feature_type);


-- 4. Experiments (experiments associated with the WT protein and user)
create table experiments (
    experiment_id bigserial primary key,
    user_id bigint not null,
    wt_id bigint not null,
    name varchar(255) not null, -- indicate domain, active site and binding site
    description text,
    created_at timestamptz default now(),
updated_at timestamptz default now(),
    foreign key (user_id) references users(user_id) on delete cascade,
foreign key (wt_id) references wild_type_proteins(wt_id) on delete cascade
);

create index idx_exp_user on experiments (user_id);
create index idx_exp_wt on experiments (wt_id);

create trigger trg_experiments_updated_at
before update on experiments
for each row
execute function set_updated_at();
-- this is the feature table for all the features, taken from the Uniprot website

-- *** implementation of analysis stqtus column for pogress tracking.
DO $$
BEGIN
    ALTER TABLE experiments 
    ADD COLUMN IF NOT EXISTS analysis_status TEXT;
END $$;
-- This is for the whole Direct Evolution project, rather than having it mixed up with the generations, which should be in a separate section


-- 5. Generations
create table generations (
    generation_id bigserial primary key,
    experiment_id bigint not null,
    generation_number int not null,
    created_at timestamptz default now(),
    foreign key (experiment_id) references experiments(experiment_id) on delete cascade,
    unique (experiment_id, generation_number)
);

create index idx_gen_experiment on generations (experiment_id);
-- direct evolution structure (multiple generations of evolution circles)


-- 6. Variants table (library for variants- both plasmid and protein- storage and links to parent-variant lineage)
create table variants (
    variant_id bigserial primary key,
    generation_id bigint not null,
    parent_variant_id bigint null,
    plasmid_variant_index varchar(50) not null,
    assembled_dna_sequence text,
    protein_sequence text,
    created_at timestamptz default now(),
    foreign key (generation_id) references generations(generation_id) on delete cascade,
foreign key (parent_variant_id) references variants(variant_id) on delete set null,
    unique (generation_id, plasmid_variant_index)
);

create index idx_variant_generation on variants (generation_id);
create index idx_variant_parent on variants (parent_variant_id);
-- track parent variant for lineage tracing, and also the generation it belongs to


-- 7. Mutations (DNA and protein mutations data storage per variant)
create table mutations (
    mutation_id bigserial primary key,
    variant_id bigint not null,
    mutation_type varchar(10) not null check (mutation_type in ('dna', 'protein')),
    position int not null check (position > 0),
    original char(1) not null,
    mutated char(1) not null,
    is_synonymous boolean,
    annotation text,
    foreign key (variant_id) references variants(variant_id) on delete cascade
);

create index idx_mut_variant on mutations (variant_id);
create index idx_mut_type on mutations (mutation_type);
create index idx_mut_position on mutations (position);

create unique index uq_mut
on mutations (variant_id, mutation_type, position, original, mutated); -- avoids duplicate mutation entries for the same variant


-- 8. Wild type controls per generation
create table wild_type_controls (
    wt_control_id bigserial primary key,
    generation_id bigint not null,
    wt_id bigint not null,
    created_at timestamptz default now(),
    foreign key (generation_id) references generations(generation_id) on delete cascade,
foreign key (wt_id) references wild_type_proteins(wt_id) on delete cascade,
    unique (generation_id, wt_id)
);

create index idx_wt_control_generation on wild_type_controls (generation_id);

DO $$
BEGIN
    IF to_regclass('public.metrics') IS NOT NULL THEN
        CREATE UNIQUE INDEX IF NOT EXISTS uq_metrics_wt_simple
        ON metrics (wt_control_id, metric_name, metric_type)
        WHERE wt_control_id IS NOT NULL;
    END IF;
END $$;


-- 9. Metrics (raw, normalised, derived metrics from variants and WT controls)

create table metrics (
metric_id bigserial primary key,
-- your trigger will fill this, but keep it not null if you want
generation_id bigint not null,

variant_id bigint null,
wt_control_id bigint null,

metric_name varchar(255) not null,
metric_type varchar(20) not null check (metric_type in ('raw','normalized','derived')),
value double precision not null,
unit varchar(50),
created_at timestamptz default now(),

foreign key (generation_id) references generations(generation_id) on delete cascade,
foreign key (variant_id) references variants(variant_id) on delete cascade,
foreign key (wt_control_id) references wild_type_controls(wt_control_id) on delete cascade,

check (
    (variant_id is not null and wt_control_id is null)
    or
    (variant_id is null and wt_control_id is not null)
)

);

-- trigger function (must exist before trigger)
create or replace function metrics_set_generation_id()
returns trigger as $$
begin
if (new.variant_id is null and new.wt_control_id is null) or
(new.variant_id is not null and new.wt_control_id is not null) then
raise exception 'exactly one of variant_id or wt_control_id must be set';
end if;

if new.variant_id is not null then
select v.generation_id into new.generation_id
from variants v
where v.variant_id = new.variant_id;

if new.generation_id is null then
  raise exception 'invalid variant_id %, cannot derive generation_id', new.variant_id;
end if;

else
select wtc.generation_id into new.generation_id
from wild_type_controls wtc
where wtc.wt_control_id = new.wt_control_id;

if new.generation_id is null then
  raise exception 'invalid wt_control_id %, cannot derive generation_id', new.wt_control_id;
end if;

end if;

return new;
end;
$$ language plpgsql;

drop trigger if exists trg_metrics_set_generation on metrics;

create trigger trg_metrics_set_generation
before insert or update on metrics
for each row
execute function metrics_set_generation_id();

-- normal (non-unique) indexes (after table exists)
create index if not exists idx_metric_generation on metrics (generation_id);
create index if not exists idx_metric_variant on metrics (variant_id);
create index if not exists idx_metric_name on metrics (metric_name);
create index if not exists idx_metrics_name_type on metrics(metric_name, metric_type);

-- uniqueness rules - only one entry per metric name and type for each variant or WT control
create unique index if not exists uq_metrics_variant
on metrics (generation_id, variant_id, metric_name, metric_type)
where variant_id is not null;

create unique index if not exists uq_metrics_wt
on metrics (generation_id, wt_control_id, metric_name, metric_type)
where wt_control_id is not null;


-- 10. Experiment metadata table (extras from TSV/JSON parsing)
create table experiment_metadata (
    metadata_id bigserial primary key,
    experiment_id bigint not null,
    field_name varchar(255) not null,
    field_value text,
    foreign key (experiment_id) references experiments(experiment_id) on delete cascade,
unique (experiment_id, field_name)
);

create index idx_meta_experiment on experiment_metadata (experiment_id);
create index idx_meta_field on experiment_metadata (field_name);

alter table variants add column if not exists extra_metadata jsonb;
create index if not exists idx_variants_extra_metadata on variants using gin (extra_metadata);
-- this data is very dynamic considering it depends on all the other data together and is subject to a change


-- 11. Variant sequence analysis table for  storing results from sequence analysis (e.g. stability predictions, structural predictions, etc.)
create table if not exists variant_sequence_analysis (
vsa_id bigserial primary key,
variant_id bigint not null references variants(variant_id) on delete cascade,

-- analysis bookkeeping
analysis_version text not null default 'v1',
status text not null default 'queued',  -- queued/running/success/failed
error_message text,

-- orf / gene calling details (important for circular plasmids)
orf_start int,
orf_end int,
is_circular_wrap boolean default false,
strand smallint, -- +1 or -1

-- translation/qc
translated_protein_sequence text,
has_internal_stop boolean,
qc_flags jsonb,

created_at timestamptz not null default now(),
updated_at timestamptz not null default now(),

unique (variant_id, analysis_version)
);

create index if not exists idx_vsa_variant on variant_sequence_analysis(variant_id);

create trigger trg_vsa_updated_at
before update on variant_sequence_analysis
for each row
execute function set_updated_at();

alter table mutations add column if not exists vsa_id bigint
references variant_sequence_analysis(vsa_id) on delete cascade;



-- -----------------------------------------------------------------------------



-- Metrics and lineage-related functions and triggers 

-- Metrics definitions and links to metrics table
create table if not exists metric_definitions (
    metric_definition_id bigserial primary key,
    name text not null,
    description text,
    unit text,
    metric_type text not null check (metric_type in ('raw', 'normalized', 'derived')),
    unique (name)
);

-- populate metric_definitions with common metrics (if not already present)
insert into metric_definitions (name, description, unit, metric_type)
values
('dna_yield_raw','Raw DNA quantification','fg','raw'),
('protein_yield_raw','Raw protein quantification','pg','raw'),
('dna_yield_norm','DNA normalised to WT baseline','ratio','normalized'),
('protein_yield_norm','Protein normalised to WT baseline','ratio','normalized'),
('activity_score','dna_yield_norm / protein_yield_norm','ratio','derived')
on conflict (name) do nothing;  

-- Add the FK column to metrics — but keep metric_name
alter table metrics add column if not exists metric_definition_id bigint;

-- Fill the FK for existing rows (This links existing metrics.metric_name to the definitions table.)
update metrics m        
set metric_definition_id = md.metric_definition_id
from metric_definitions md
where m.metric_name = md.name
and m.metric_definition_id is null; 

-- Add the FK constraint (but only if it doesn't already exist, to avoid issues with existing data)
do $$
begin
    if not exists (
        select 1
        from information_schema.table_constraints
        where table_schema = 'public'
          and table_name = 'metrics'
          and constraint_name = 'fk_metrics_metric_definition'
    ) then
        alter table metrics
        add constraint fk_metrics_metric_definition
        foreign key (metric_definition_id)
        references metric_definitions(metric_definition_id);
    end if;
end $$;

-- Add a trigger to auto-fill metric_definition_id when someone inserts a metric by name:
create or replace function set_metric_definition_id()
returns trigger as $$       
begin
    if new.metric_definition_id is null and new.metric_name is not null then
        select md.metric_definition_id into new.metric_definition_id
        from metric_definitions md
        where md.name = new.metric_name;
    end if;
    return new;
end;    
$$ language plpgsql;

drop trigger if exists trg_set_metric_definition_id on metrics;

create trigger trg_set_metric_definition_id
before insert or update on metrics
for each row
execute function set_metric_definition_id();


-- -----------------------------------------------------------------



-- Lineage closure table and related triggers/functions for maintaining ancestor-descendant relationships between variants, to enable efficient lineage queries and network visualizations.
-- VARIANT LINEAGE CLOSURE TABLE
create table if not exists variant_lineage_closure (
    ancestor_id bigint not null,
    descendant_id bigint not null,
    distance int not null check (distance >= 0),
    primary key (ancestor_id, descendant_id),
    foreign key (ancestor_id) references variants(variant_id) on delete cascade,
    foreign key (descendant_id) references variants(variant_id) on delete cascade
);

create index if not exists idx_closure_desc on variant_lineage_closure (descendant_id);

-- Optional backfill for lineage closure should live in a separate script
-- to avoid destructive actions in schema migrations.

-- Maintain the trigger on intent
create or replace function vlc_after_variant_insert()
returns trigger as $$
begin
insert into variant_lineage_closure (ancestor_id, descendant_id, distance) -- self-relationship for the new variant
values (new.variant_id, new.variant_id, 0)
on conflict do nothing;

if new.parent_variant_id is not null then -- if there is a parent, need to add relationships to all ancestors of the parent
    insert into variant_lineage_closure (ancestor_id, descendant_id, distance)
    select c.ancestor_id, new.variant_id, c.distance + 1
    from variant_lineage_closure c
    where c.descendant_id = new.parent_variant_id
    on conflict do nothing;
end if;

return new; 
end;
$$ language plpgsql;

drop trigger if exists trg_vlc_after_variant_insert on variants;

create trigger trg_vlc_after_variant_insert
after insert on variants
for each row
execute function vlc_after_variant_insert();

-- Maintain and update after trigger (re-parenting prevention)
create or replace function prevent_variant_reparent()
returns trigger as $$
begin
if new.parent_variant_id is distinct from old.parent_variant_id then
raise exception 'Re-parenting not allowed for variant_id=%', old.variant_id;
end if;
return new;
end;
$$ language plpgsql;

drop trigger if exists trg_prevent_variant_reparent on variants;

create trigger trg_prevent_variant_reparent
before update of parent_variant_id on variants
for each row
execute function prevent_variant_reparent();    


-- Views used for lineage/network plots
create or replace view v_variant_edges as
select parent_variant_id as source,
       variant_id as target
from variants
where parent_variant_id is not null;

create or replace view v_variant_nodes as
select v.variant_id,
       v.parent_variant_id,
       g.experiment_id,
       g.generation_number,
       v.plasmid_variant_index,
       ms.value as activity_score,
       coalesce(pm.protein_mut_count, 0) as protein_mutations
from variants v
join generations g on g.generation_id = v.generation_id
left join metrics ms
  on ms.variant_id = v.variant_id
 and ms.metric_name = 'activity_score'
 and ms.metric_type = 'derived'
left join (
    select mutations.variant_id,
           count(*) as protein_mut_count
    from mutations
    where mutations.mutation_type = 'protein'
    group by mutations.variant_id
) pm on pm.variant_id = v.variant_id;

