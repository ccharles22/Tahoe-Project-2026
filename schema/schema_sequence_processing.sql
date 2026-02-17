BEGIN;

CREATE TABLE IF NOT EXISTS users (
  user_id BIGSERIAL PRIMARY KEY,
  username TEXT UNIQUE NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS wild_type_proteins (
  wt_id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
  uniprot_id TEXT,
  amino_acid_sequence TEXT NOT NULL,
  plasmid_sequence TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS experiments (
  experiment_id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
  wt_id BIGINT NOT NULL REFERENCES wild_type_proteins(wt_id) ON DELETE RESTRICT,
  analysis_status TEXT,
  extra_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS generations (
  generation_id BIGSERIAL PRIMARY KEY,
  experiment_id BIGINT NOT NULL REFERENCES experiments(experiment_id) ON DELETE CASCADE,
  generation_number INT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (experiment_id, generation_number)
);

CREATE TABLE IF NOT EXISTS variants (
  variant_id BIGSERIAL PRIMARY KEY,
  generation_id BIGINT NOT NULL REFERENCES generations(generation_id) ON DELETE CASCADE,
  plasmid_variant_index TEXT,
  parent_variant_index TEXT,
  assembled_dna_sequence TEXT NOT NULL,
  protein_sequence TEXT,
  extra_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_variants_generation_id ON variants(generation_id);
CREATE INDEX IF NOT EXISTS idx_generations_experiment_id ON generations(experiment_id);
CREATE INDEX IF NOT EXISTS gin_experiments_extra_metadata ON experiments USING gin (extra_metadata);
CREATE INDEX IF NOT EXISTS gin_variants_extra_metadata ON variants USING gin (extra_metadata);


CREATE TABLE IF NOT EXISTS experiment_uniprot_staging (
  experiment_id BIGINT NOT NULL REFERENCES experiments(experiment_id) ON DELETE CASCADE,
  user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
  accession TEXT NOT NULL,
  protein_sequence TEXT NOT NULL,
  retrieved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (experiment_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_eus_experiment_id ON experiment_uniprot_staging(experiment_id);
CREATE INDEX IF NOT EXISTS idx_eus_user_id ON experiment_uniprot_staging(user_id);
CREATE INDEX IF NOT EXISTS idx_eus_accession ON experiment_uniprot_staging(accession);

CREATE TABLE IF NOT EXISTS experiment_wt_mapping (
  experiment_id BIGINT NOT NULL REFERENCES experiments(experiment_id) ON DELETE CASCADE,
  user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
  mapping_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  mapped_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (experiment_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_ewm_experiment_id ON experiment_wt_mapping(experiment_id);
CREATE INDEX IF NOT EXISTS idx_ewm_user_id ON experiment_wt_mapping(user_id);

CREATE TABLE IF NOT EXISTS variant_sequence_analysis (
  analysis_id BIGSERIAL PRIMARY KEY,
  variant_id BIGINT NOT NULL REFERENCES variants(variant_id) ON DELETE CASCADE,
  experiment_id BIGINT NOT NULL REFERENCES experiments(experiment_id) ON DELETE CASCADE,
  user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
  analysed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  analysis_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  UNIQUE (variant_id, user_id, analysed_at)
);

CREATE INDEX IF NOT EXISTS idx_vsa_variant_id ON variant_sequence_analysis(variant_id);
CREATE INDEX IF NOT EXISTS idx_vsa_experiment_id ON variant_sequence_analysis(experiment_id);
CREATE INDEX IF NOT EXISTS idx_vsa_user_id ON variant_sequence_analysis(user_id);
CREATE INDEX IF NOT EXISTS idx_vsa_analysed_at ON variant_sequence_analysis(analysed_at);

CREATE INDEX IF NOT EXISTS gin_vsa_analysis_json ON variant_sequence_analysis USING gin (analysis_json);

CREATE TABLE IF NOT EXISTS variant_mutations (
  mutation_id BIGSERIAL PRIMARY KEY,
  analysis_id BIGINT NOT NULL
    REFERENCES variant_sequence_analysis(analysis_id) ON DELETE CASCADE,
  mutation_type TEXT NOT NULL,
  codon_index_1based INT,
  aa_position_1based INT,
  wt_codon TEXT,
  var_codon TEXT,
  wt_aa TEXT,
  var_aa TEXT,
  notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_vm_analysis_id ON variant_mutations(analysis_id);
CREATE INDEX IF NOT EXISTS idx_vm_type ON variant_mutations(mutation_type);
CREATE INDEX IF NOT EXISTS idx_vm_aa_pos ON variant_mutations(aa_position_1based);

CREATE OR REPLACE VIEW v_variants_with_experiment AS
SELECT
  v.variant_id,
  v.generation_id,
  g.generation_number,
  g.experiment_id,
  e.user_id AS experiment_owner_user_id,
  v.plasmid_variant_index,
  v.parent_variant_index,
  v.created_at
FROM variants v
JOIN generations g ON g.generation_id = v.generation_id
JOIN experiments e ON e.experiment_id = g.experiment_id;

CREATE OR REPLACE VIEW v_variant_analysis_latest AS
SELECT DISTINCT ON (vsa.variant_id, vsa.user_id)
  vsa.analysis_id,
  vsa.variant_id,
  vsa.experiment_id,
  vsa.user_id,
  vsa.analysed_at,
  vsa.analysis_json
FROM variant_sequence_analysis vsa
ORDER BY vsa.variant_id, vsa.user_id, vsa.analysed_at DESC;

CREATE OR REPLACE VIEW v_variant_analysis_flat AS
SELECT
  vw.experiment_id,
  vw.generation_number,
  vw.variant_id,
  l.user_id AS namespace_user_id,
  l.analysed_at,
  l.analysis_id,
  l.analysis_json
FROM v_variants_with_experiment vw
LEFT JOIN v_variant_analysis_latest l
  ON l.variant_id = vw.variant_id;

CREATE OR REPLACE VIEW v_experiment_wt_mapping AS
SELECT
  ewm.experiment_id,
  ewm.user_id,
  ewm.mapped_at,
  ewm.mapping_json
FROM experiment_wt_mapping ewm;

CREATE OR REPLACE VIEW v_experiment_uniprot_staging AS
SELECT
  eus.experiment_id,
  eus.user_id,
  eus.accession,
  eus.retrieved_at,
  eus.protein_sequence
FROM experiment_uniprot_staging eus;

COMMIT;
