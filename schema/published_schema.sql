--
-- PostgreSQL database dump
--

\restrict uXBG7rgzGylZBSh4AeInOH9A5fa9b93TpngWPPeRnCzSphAFdzub8NyCha5yukZ

-- Dumped from database version 18.2 (Homebrew)
-- Dumped by pg_dump version 18.2 (Homebrew)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: citext; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS citext WITH SCHEMA public;


--
-- Name: EXTENSION citext; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION citext IS 'data type for case-insensitive character strings';


--
-- Name: metrics_set_generation_id(); Type: FUNCTION; Schema: public; Owner: mariapaolaluciani
--

CREATE FUNCTION public.metrics_set_generation_id() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  -- Enforce exactly one of variant_id or wt_control_id
  IF (NEW.variant_id IS NULL AND NEW.wt_control_id IS NULL) OR
     (NEW.variant_id IS NOT NULL AND NEW.wt_control_id IS NOT NULL) THEN
    RAISE EXCEPTION 'Exactly one of variant_id or wt_control_id must be set';
  END IF;

  -- Derive generation_id
  IF NEW.variant_id IS NOT NULL THEN
    SELECT v.generation_id INTO NEW.generation_id
    FROM variants v
    WHERE v.variant_id = NEW.variant_id;

    IF NEW.generation_id IS NULL THEN
      RAISE EXCEPTION 'Invalid variant_id %, cannot derive generation_id', NEW.variant_id;
    END IF;

  ELSE
    SELECT wtc.generation_id INTO NEW.generation_id
    FROM wild_type_controls wtc
    WHERE wtc.wt_control_id = NEW.wt_control_id;

    IF NEW.generation_id IS NULL THEN
      RAISE EXCEPTION 'Invalid wt_control_id %, cannot derive generation_id', NEW.wt_control_id;
    END IF;
  END IF;

  RETURN NEW;
END;
$$;


ALTER FUNCTION public.metrics_set_generation_id() OWNER TO mariapaolaluciani;

--
-- Name: set_metric_definition_id(); Type: FUNCTION; Schema: public; Owner: mariapaolaluciani
--

CREATE FUNCTION public.set_metric_definition_id() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  IF NEW.metric_definition_id IS NULL AND NEW.metric_name IS NOT NULL THEN
    SELECT md.metric_definition_id INTO NEW.metric_definition_id
    FROM metric_definitions md
    WHERE md.name = NEW.metric_name;
  END IF;
  RETURN NEW;
END;
$$;


ALTER FUNCTION public.set_metric_definition_id() OWNER TO mariapaolaluciani;

--
-- Name: set_updated_at(); Type: FUNCTION; Schema: public; Owner: mariapaolaluciani
--

CREATE FUNCTION public.set_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
  NEW.updated_at = CURRENT_TIMESTAMP;
  RETURN NEW;
END;
$$;


ALTER FUNCTION public.set_updated_at() OWNER TO mariapaolaluciani;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: experiment_metadata; Type: TABLE; Schema: public; Owner: mariapaolaluciani
--

CREATE TABLE public.experiment_metadata (
    metadata_id bigint NOT NULL,
    experiment_id bigint NOT NULL,
    field_name character varying(255) NOT NULL,
    field_value text
);


ALTER TABLE public.experiment_metadata OWNER TO mariapaolaluciani;

--
-- Name: experiment_metadata_metadata_id_seq; Type: SEQUENCE; Schema: public; Owner: mariapaolaluciani
--

CREATE SEQUENCE public.experiment_metadata_metadata_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.experiment_metadata_metadata_id_seq OWNER TO mariapaolaluciani;

--
-- Name: experiment_metadata_metadata_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: mariapaolaluciani
--

ALTER SEQUENCE public.experiment_metadata_metadata_id_seq OWNED BY public.experiment_metadata.metadata_id;


--
-- Name: experiments; Type: TABLE; Schema: public; Owner: mariapaolaluciani
--

CREATE TABLE public.experiments (
    experiment_id bigint NOT NULL,
    user_id bigint NOT NULL,
    wt_id bigint NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now(),
    extra_metadata jsonb
);


ALTER TABLE public.experiments OWNER TO mariapaolaluciani;

--
-- Name: experiments_experiment_id_seq; Type: SEQUENCE; Schema: public; Owner: mariapaolaluciani
--

CREATE SEQUENCE public.experiments_experiment_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.experiments_experiment_id_seq OWNER TO mariapaolaluciani;

--
-- Name: experiments_experiment_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: mariapaolaluciani
--

ALTER SEQUENCE public.experiments_experiment_id_seq OWNED BY public.experiments.experiment_id;


--
-- Name: generations; Type: TABLE; Schema: public; Owner: mariapaolaluciani
--

CREATE TABLE public.generations (
    generation_id bigint NOT NULL,
    experiment_id bigint NOT NULL,
    generation_number integer NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.generations OWNER TO mariapaolaluciani;

--
-- Name: generations_generation_id_seq; Type: SEQUENCE; Schema: public; Owner: mariapaolaluciani
--

CREATE SEQUENCE public.generations_generation_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.generations_generation_id_seq OWNER TO mariapaolaluciani;

--
-- Name: generations_generation_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: mariapaolaluciani
--

ALTER SEQUENCE public.generations_generation_id_seq OWNED BY public.generations.generation_id;


--
-- Name: metric_definitions; Type: TABLE; Schema: public; Owner: mariapaolaluciani
--

CREATE TABLE public.metric_definitions (
    metric_definition_id bigint NOT NULL,
    name text NOT NULL,
    description text,
    unit text,
    metric_type text NOT NULL,
    CONSTRAINT metric_definitions_metric_type_check CHECK ((metric_type = ANY (ARRAY['raw'::text, 'normalized'::text, 'derived'::text])))
);


ALTER TABLE public.metric_definitions OWNER TO mariapaolaluciani;

--
-- Name: metric_definitions_metric_definition_id_seq; Type: SEQUENCE; Schema: public; Owner: mariapaolaluciani
--

CREATE SEQUENCE public.metric_definitions_metric_definition_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.metric_definitions_metric_definition_id_seq OWNER TO mariapaolaluciani;

--
-- Name: metric_definitions_metric_definition_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: mariapaolaluciani
--

ALTER SEQUENCE public.metric_definitions_metric_definition_id_seq OWNED BY public.metric_definitions.metric_definition_id;


--
-- Name: metrics; Type: TABLE; Schema: public; Owner: mariapaolaluciani
--

CREATE TABLE public.metrics (
    metric_id bigint NOT NULL,
    generation_id bigint NOT NULL,
    variant_id bigint,
    wt_control_id bigint,
    metric_name character varying(255) NOT NULL,
    metric_type character varying(20) NOT NULL,
    value double precision NOT NULL,
    unit character varying(50),
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    metric_definition_id bigint,
    CONSTRAINT metrics_check CHECK ((((variant_id IS NOT NULL) AND (wt_control_id IS NULL)) OR ((variant_id IS NULL) AND (wt_control_id IS NOT NULL)))),
    CONSTRAINT metrics_metric_type_check CHECK (((metric_type)::text = ANY ((ARRAY['raw'::character varying, 'normalized'::character varying, 'derived'::character varying])::text[])))
);


ALTER TABLE public.metrics OWNER TO mariapaolaluciani;

--
-- Name: metrics_metric_id_seq; Type: SEQUENCE; Schema: public; Owner: mariapaolaluciani
--

CREATE SEQUENCE public.metrics_metric_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.metrics_metric_id_seq OWNER TO mariapaolaluciani;

--
-- Name: metrics_metric_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: mariapaolaluciani
--

ALTER SEQUENCE public.metrics_metric_id_seq OWNED BY public.metrics.metric_id;


--
-- Name: mutations; Type: TABLE; Schema: public; Owner: mariapaolaluciani
--

CREATE TABLE public.mutations (
    mutation_id bigint NOT NULL,
    variant_id bigint NOT NULL,
    mutation_type character varying(10) NOT NULL,
    "position" integer NOT NULL,
    original character(1) NOT NULL,
    mutated character(1) NOT NULL,
    is_synonymous boolean,
    annotation text,
    CONSTRAINT chk_mutation_dna_bases CHECK ((((mutation_type)::text <> 'dna'::text) OR ((original = ANY (ARRAY['A'::bpchar, 'C'::bpchar, 'G'::bpchar, 'T'::bpchar])) AND (mutated = ANY (ARRAY['A'::bpchar, 'C'::bpchar, 'G'::bpchar, 'T'::bpchar]))))),
    CONSTRAINT chk_mutation_protein_aas CHECK ((((mutation_type)::text <> 'protein'::text) OR ((original = ANY (ARRAY['A'::bpchar, 'C'::bpchar, 'D'::bpchar, 'E'::bpchar, 'F'::bpchar, 'G'::bpchar, 'H'::bpchar, 'I'::bpchar, 'K'::bpchar, 'L'::bpchar, 'M'::bpchar, 'N'::bpchar, 'P'::bpchar, 'Q'::bpchar, 'R'::bpchar, 'S'::bpchar, 'T'::bpchar, 'V'::bpchar, 'W'::bpchar, 'Y'::bpchar, 'X'::bpchar, '*'::bpchar])) AND (mutated = ANY (ARRAY['A'::bpchar, 'C'::bpchar, 'D'::bpchar, 'E'::bpchar, 'F'::bpchar, 'G'::bpchar, 'H'::bpchar, 'I'::bpchar, 'K'::bpchar, 'L'::bpchar, 'M'::bpchar, 'N'::bpchar, 'P'::bpchar, 'Q'::bpchar, 'R'::bpchar, 'S'::bpchar, 'T'::bpchar, 'V'::bpchar, 'W'::bpchar, 'Y'::bpchar, 'X'::bpchar, '*'::bpchar]))))),
    CONSTRAINT mutations_mutation_type_check CHECK (((mutation_type)::text = ANY ((ARRAY['dna'::character varying, 'protein'::character varying])::text[]))),
    CONSTRAINT mutations_position_check CHECK (("position" > 0))
);


ALTER TABLE public.mutations OWNER TO mariapaolaluciani;

--
-- Name: mutations_mutation_id_seq; Type: SEQUENCE; Schema: public; Owner: mariapaolaluciani
--

CREATE SEQUENCE public.mutations_mutation_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.mutations_mutation_id_seq OWNER TO mariapaolaluciani;

--
-- Name: mutations_mutation_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: mariapaolaluciani
--

ALTER SEQUENCE public.mutations_mutation_id_seq OWNED BY public.mutations.mutation_id;


--
-- Name: protein_features; Type: TABLE; Schema: public; Owner: mariapaolaluciani
--

CREATE TABLE public.protein_features (
    feature_id bigint NOT NULL,
    wt_id bigint NOT NULL,
    feature_type character varying(100) NOT NULL,
    description text,
    start_position integer NOT NULL,
    end_position integer NOT NULL,
    CONSTRAINT protein_features_check CHECK ((end_position >= start_position)),
    CONSTRAINT protein_features_start_position_check CHECK ((start_position > 0))
);


ALTER TABLE public.protein_features OWNER TO mariapaolaluciani;

--
-- Name: protein_features_feature_id_seq; Type: SEQUENCE; Schema: public; Owner: mariapaolaluciani
--

CREATE SEQUENCE public.protein_features_feature_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.protein_features_feature_id_seq OWNER TO mariapaolaluciani;

--
-- Name: protein_features_feature_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: mariapaolaluciani
--

ALTER SEQUENCE public.protein_features_feature_id_seq OWNED BY public.protein_features.feature_id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: mariapaolaluciani
--

CREATE TABLE public.users (
    user_id bigint NOT NULL,
    username public.citext NOT NULL,
    email public.citext NOT NULL,
    password_hash text NOT NULL,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.users OWNER TO mariapaolaluciani;

--
-- Name: users_user_id_seq; Type: SEQUENCE; Schema: public; Owner: mariapaolaluciani
--

CREATE SEQUENCE public.users_user_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.users_user_id_seq OWNER TO mariapaolaluciani;

--
-- Name: users_user_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: mariapaolaluciani
--

ALTER SEQUENCE public.users_user_id_seq OWNED BY public.users.user_id;


--
-- Name: variants; Type: TABLE; Schema: public; Owner: mariapaolaluciani
--

CREATE TABLE public.variants (
    variant_id bigint NOT NULL,
    generation_id bigint NOT NULL,
    parent_variant_id bigint,
    plasmid_variant_index character varying(50) NOT NULL,
    assembled_dna_sequence text,
    protein_sequence text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    extra_metadata jsonb
);


ALTER TABLE public.variants OWNER TO mariapaolaluciani;

--
-- Name: variants_variant_id_seq; Type: SEQUENCE; Schema: public; Owner: mariapaolaluciani
--

CREATE SEQUENCE public.variants_variant_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.variants_variant_id_seq OWNER TO mariapaolaluciani;

--
-- Name: variants_variant_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: mariapaolaluciani
--

ALTER SEQUENCE public.variants_variant_id_seq OWNED BY public.variants.variant_id;


--
-- Name: wild_type_controls; Type: TABLE; Schema: public; Owner: mariapaolaluciani
--

CREATE TABLE public.wild_type_controls (
    wt_control_id bigint NOT NULL,
    generation_id bigint NOT NULL,
    wt_id bigint NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.wild_type_controls OWNER TO mariapaolaluciani;

--
-- Name: wild_type_controls_wt_control_id_seq; Type: SEQUENCE; Schema: public; Owner: mariapaolaluciani
--

CREATE SEQUENCE public.wild_type_controls_wt_control_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.wild_type_controls_wt_control_id_seq OWNER TO mariapaolaluciani;

--
-- Name: wild_type_controls_wt_control_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: mariapaolaluciani
--

ALTER SEQUENCE public.wild_type_controls_wt_control_id_seq OWNED BY public.wild_type_controls.wt_control_id;


--
-- Name: wild_type_proteins; Type: TABLE; Schema: public; Owner: mariapaolaluciani
--

CREATE TABLE public.wild_type_proteins (
    wt_id bigint NOT NULL,
    user_id bigint NOT NULL,
    uniprot_id character varying(20) NOT NULL,
    protein_name character varying(255),
    organism character varying(255),
    amino_acid_sequence text NOT NULL,
    sequence_length integer NOT NULL,
    plasmid_name character varying(255),
    plasmid_sequence text NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.wild_type_proteins OWNER TO mariapaolaluciani;

--
-- Name: wild_type_proteins_wt_id_seq; Type: SEQUENCE; Schema: public; Owner: mariapaolaluciani
--

CREATE SEQUENCE public.wild_type_proteins_wt_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.wild_type_proteins_wt_id_seq OWNER TO mariapaolaluciani;

--
-- Name: wild_type_proteins_wt_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: mariapaolaluciani
--

ALTER SEQUENCE public.wild_type_proteins_wt_id_seq OWNED BY public.wild_type_proteins.wt_id;


--
-- Name: experiment_metadata metadata_id; Type: DEFAULT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.experiment_metadata ALTER COLUMN metadata_id SET DEFAULT nextval('public.experiment_metadata_metadata_id_seq'::regclass);


--
-- Name: experiments experiment_id; Type: DEFAULT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.experiments ALTER COLUMN experiment_id SET DEFAULT nextval('public.experiments_experiment_id_seq'::regclass);


--
-- Name: generations generation_id; Type: DEFAULT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.generations ALTER COLUMN generation_id SET DEFAULT nextval('public.generations_generation_id_seq'::regclass);


--
-- Name: metric_definitions metric_definition_id; Type: DEFAULT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.metric_definitions ALTER COLUMN metric_definition_id SET DEFAULT nextval('public.metric_definitions_metric_definition_id_seq'::regclass);


--
-- Name: metrics metric_id; Type: DEFAULT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.metrics ALTER COLUMN metric_id SET DEFAULT nextval('public.metrics_metric_id_seq'::regclass);


--
-- Name: mutations mutation_id; Type: DEFAULT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.mutations ALTER COLUMN mutation_id SET DEFAULT nextval('public.mutations_mutation_id_seq'::regclass);


--
-- Name: protein_features feature_id; Type: DEFAULT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.protein_features ALTER COLUMN feature_id SET DEFAULT nextval('public.protein_features_feature_id_seq'::regclass);


--
-- Name: users user_id; Type: DEFAULT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.users ALTER COLUMN user_id SET DEFAULT nextval('public.users_user_id_seq'::regclass);


--
-- Name: variants variant_id; Type: DEFAULT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.variants ALTER COLUMN variant_id SET DEFAULT nextval('public.variants_variant_id_seq'::regclass);


--
-- Name: wild_type_controls wt_control_id; Type: DEFAULT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.wild_type_controls ALTER COLUMN wt_control_id SET DEFAULT nextval('public.wild_type_controls_wt_control_id_seq'::regclass);


--
-- Name: wild_type_proteins wt_id; Type: DEFAULT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.wild_type_proteins ALTER COLUMN wt_id SET DEFAULT nextval('public.wild_type_proteins_wt_id_seq'::regclass);


--
-- Name: experiment_metadata experiment_metadata_pkey; Type: CONSTRAINT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.experiment_metadata
    ADD CONSTRAINT experiment_metadata_pkey PRIMARY KEY (metadata_id);


--
-- Name: experiments experiments_pkey; Type: CONSTRAINT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.experiments
    ADD CONSTRAINT experiments_pkey PRIMARY KEY (experiment_id);


--
-- Name: generations generations_experiment_id_generation_number_key; Type: CONSTRAINT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.generations
    ADD CONSTRAINT generations_experiment_id_generation_number_key UNIQUE (experiment_id, generation_number);


--
-- Name: generations generations_pkey; Type: CONSTRAINT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.generations
    ADD CONSTRAINT generations_pkey PRIMARY KEY (generation_id);


--
-- Name: metric_definitions metric_definitions_name_key; Type: CONSTRAINT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.metric_definitions
    ADD CONSTRAINT metric_definitions_name_key UNIQUE (name);


--
-- Name: metric_definitions metric_definitions_pkey; Type: CONSTRAINT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.metric_definitions
    ADD CONSTRAINT metric_definitions_pkey PRIMARY KEY (metric_definition_id);


--
-- Name: metrics metrics_pkey; Type: CONSTRAINT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.metrics
    ADD CONSTRAINT metrics_pkey PRIMARY KEY (metric_id);


--
-- Name: mutations mutations_pkey; Type: CONSTRAINT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.mutations
    ADD CONSTRAINT mutations_pkey PRIMARY KEY (mutation_id);


--
-- Name: protein_features protein_features_pkey; Type: CONSTRAINT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.protein_features
    ADD CONSTRAINT protein_features_pkey PRIMARY KEY (feature_id);


--
-- Name: experiment_metadata uq_experiment_field; Type: CONSTRAINT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.experiment_metadata
    ADD CONSTRAINT uq_experiment_field UNIQUE (experiment_id, field_name);


--
-- Name: metrics uq_metrics_variant_triplet; Type: CONSTRAINT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.metrics
    ADD CONSTRAINT uq_metrics_variant_triplet UNIQUE (variant_id, metric_name, metric_type);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (user_id);


--
-- Name: users users_username_key; Type: CONSTRAINT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_username_key UNIQUE (username);


--
-- Name: variants variants_generation_id_plasmid_variant_index_key; Type: CONSTRAINT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.variants
    ADD CONSTRAINT variants_generation_id_plasmid_variant_index_key UNIQUE (generation_id, plasmid_variant_index);


--
-- Name: variants variants_pkey; Type: CONSTRAINT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.variants
    ADD CONSTRAINT variants_pkey PRIMARY KEY (variant_id);


--
-- Name: wild_type_controls wild_type_controls_generation_id_wt_id_key; Type: CONSTRAINT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.wild_type_controls
    ADD CONSTRAINT wild_type_controls_generation_id_wt_id_key UNIQUE (generation_id, wt_id);


--
-- Name: wild_type_controls wild_type_controls_pkey; Type: CONSTRAINT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.wild_type_controls
    ADD CONSTRAINT wild_type_controls_pkey PRIMARY KEY (wt_control_id);


--
-- Name: wild_type_proteins wild_type_proteins_pkey; Type: CONSTRAINT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.wild_type_proteins
    ADD CONSTRAINT wild_type_proteins_pkey PRIMARY KEY (wt_id);


--
-- Name: wild_type_proteins wild_type_proteins_uniprot_id_user_id_key; Type: CONSTRAINT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.wild_type_proteins
    ADD CONSTRAINT wild_type_proteins_uniprot_id_user_id_key UNIQUE (uniprot_id, user_id);


--
-- Name: idx_email; Type: INDEX; Schema: public; Owner: mariapaolaluciani
--

CREATE INDEX idx_email ON public.users USING btree (email);


--
-- Name: idx_exp_user; Type: INDEX; Schema: public; Owner: mariapaolaluciani
--

CREATE INDEX idx_exp_user ON public.experiments USING btree (user_id);


--
-- Name: idx_exp_wt; Type: INDEX; Schema: public; Owner: mariapaolaluciani
--

CREATE INDEX idx_exp_wt ON public.experiments USING btree (wt_id);


--
-- Name: idx_experiments_extra_metadata; Type: INDEX; Schema: public; Owner: mariapaolaluciani
--

CREATE INDEX idx_experiments_extra_metadata ON public.experiments USING gin (extra_metadata);


--
-- Name: idx_feature_type; Type: INDEX; Schema: public; Owner: mariapaolaluciani
--

CREATE INDEX idx_feature_type ON public.protein_features USING btree (feature_type);


--
-- Name: idx_feature_wt; Type: INDEX; Schema: public; Owner: mariapaolaluciani
--

CREATE INDEX idx_feature_wt ON public.protein_features USING btree (wt_id);


--
-- Name: idx_gen_experiment; Type: INDEX; Schema: public; Owner: mariapaolaluciani
--

CREATE INDEX idx_gen_experiment ON public.generations USING btree (experiment_id);


--
-- Name: idx_meta_experiment; Type: INDEX; Schema: public; Owner: mariapaolaluciani
--

CREATE INDEX idx_meta_experiment ON public.experiment_metadata USING btree (experiment_id);


--
-- Name: idx_meta_field; Type: INDEX; Schema: public; Owner: mariapaolaluciani
--

CREATE INDEX idx_meta_field ON public.experiment_metadata USING btree (field_name);


--
-- Name: idx_metric_generation; Type: INDEX; Schema: public; Owner: mariapaolaluciani
--

CREATE INDEX idx_metric_generation ON public.metrics USING btree (generation_id);


--
-- Name: idx_metric_name; Type: INDEX; Schema: public; Owner: mariapaolaluciani
--

CREATE INDEX idx_metric_name ON public.metrics USING btree (metric_name);


--
-- Name: idx_metric_variant; Type: INDEX; Schema: public; Owner: mariapaolaluciani
--

CREATE INDEX idx_metric_variant ON public.metrics USING btree (variant_id);


--
-- Name: idx_metrics_name_type; Type: INDEX; Schema: public; Owner: mariapaolaluciani
--

CREATE INDEX idx_metrics_name_type ON public.metrics USING btree (metric_name, metric_type);


--
-- Name: idx_mut_position; Type: INDEX; Schema: public; Owner: mariapaolaluciani
--

CREATE INDEX idx_mut_position ON public.mutations USING btree ("position");


--
-- Name: idx_mut_type; Type: INDEX; Schema: public; Owner: mariapaolaluciani
--

CREATE INDEX idx_mut_type ON public.mutations USING btree (mutation_type);


--
-- Name: idx_mut_variant; Type: INDEX; Schema: public; Owner: mariapaolaluciani
--

CREATE INDEX idx_mut_variant ON public.mutations USING btree (variant_id);


--
-- Name: idx_username; Type: INDEX; Schema: public; Owner: mariapaolaluciani
--

CREATE INDEX idx_username ON public.users USING btree (username);


--
-- Name: idx_variant_generation; Type: INDEX; Schema: public; Owner: mariapaolaluciani
--

CREATE INDEX idx_variant_generation ON public.variants USING btree (generation_id);


--
-- Name: idx_variant_parent; Type: INDEX; Schema: public; Owner: mariapaolaluciani
--

CREATE INDEX idx_variant_parent ON public.variants USING btree (parent_variant_id);


--
-- Name: idx_variants_extra_metadata; Type: INDEX; Schema: public; Owner: mariapaolaluciani
--

CREATE INDEX idx_variants_extra_metadata ON public.variants USING gin (extra_metadata);


--
-- Name: idx_wt_control_generation; Type: INDEX; Schema: public; Owner: mariapaolaluciani
--

CREATE INDEX idx_wt_control_generation ON public.wild_type_controls USING btree (generation_id);


--
-- Name: idx_wt_user; Type: INDEX; Schema: public; Owner: mariapaolaluciani
--

CREATE INDEX idx_wt_user ON public.wild_type_proteins USING btree (user_id);


--
-- Name: uq_metrics_variant; Type: INDEX; Schema: public; Owner: mariapaolaluciani
--

CREATE UNIQUE INDEX uq_metrics_variant ON public.metrics USING btree (generation_id, variant_id, metric_name, metric_type) WHERE (variant_id IS NOT NULL);


--
-- Name: uq_metrics_variant_simple; Type: INDEX; Schema: public; Owner: mariapaolaluciani
--

CREATE UNIQUE INDEX uq_metrics_variant_simple ON public.metrics USING btree (variant_id, metric_name, metric_type) WHERE (variant_id IS NOT NULL);


--
-- Name: uq_metrics_wt; Type: INDEX; Schema: public; Owner: mariapaolaluciani
--

CREATE UNIQUE INDEX uq_metrics_wt ON public.metrics USING btree (generation_id, wt_control_id, metric_name, metric_type) WHERE (wt_control_id IS NOT NULL);


--
-- Name: uq_metrics_wt_simple; Type: INDEX; Schema: public; Owner: mariapaolaluciani
--

CREATE UNIQUE INDEX uq_metrics_wt_simple ON public.metrics USING btree (wt_control_id, metric_name, metric_type) WHERE (wt_control_id IS NOT NULL);


--
-- Name: uq_mut; Type: INDEX; Schema: public; Owner: mariapaolaluciani
--

CREATE UNIQUE INDEX uq_mut ON public.mutations USING btree (variant_id, mutation_type, "position", original, mutated);


--
-- Name: experiments trg_experiments_updated_at; Type: TRIGGER; Schema: public; Owner: mariapaolaluciani
--

CREATE TRIGGER trg_experiments_updated_at BEFORE UPDATE ON public.experiments FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.experiments DISABLE TRIGGER trg_experiments_updated_at;


--
-- Name: metrics trg_metrics_set_generation; Type: TRIGGER; Schema: public; Owner: mariapaolaluciani
--

CREATE TRIGGER trg_metrics_set_generation BEFORE INSERT OR UPDATE ON public.metrics FOR EACH ROW EXECUTE FUNCTION public.metrics_set_generation_id();

ALTER TABLE public.metrics DISABLE TRIGGER trg_metrics_set_generation;


--
-- Name: metrics trg_set_metric_definition_id; Type: TRIGGER; Schema: public; Owner: mariapaolaluciani
--

CREATE TRIGGER trg_set_metric_definition_id BEFORE INSERT OR UPDATE ON public.metrics FOR EACH ROW EXECUTE FUNCTION public.set_metric_definition_id();

ALTER TABLE public.metrics DISABLE TRIGGER trg_set_metric_definition_id;


--
-- Name: users trg_users_updated_at; Type: TRIGGER; Schema: public; Owner: mariapaolaluciani
--

CREATE TRIGGER trg_users_updated_at BEFORE UPDATE ON public.users FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE public.users DISABLE TRIGGER trg_users_updated_at;


--
-- Name: experiment_metadata experiment_metadata_experiment_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.experiment_metadata
    ADD CONSTRAINT experiment_metadata_experiment_id_fkey FOREIGN KEY (experiment_id) REFERENCES public.experiments(experiment_id) ON DELETE CASCADE;


--
-- Name: experiments experiments_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.experiments
    ADD CONSTRAINT experiments_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: experiments experiments_wt_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.experiments
    ADD CONSTRAINT experiments_wt_id_fkey FOREIGN KEY (wt_id) REFERENCES public.wild_type_proteins(wt_id) ON DELETE CASCADE;


--
-- Name: metrics fk_metrics_metric_definition; Type: FK CONSTRAINT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.metrics
    ADD CONSTRAINT fk_metrics_metric_definition FOREIGN KEY (metric_definition_id) REFERENCES public.metric_definitions(metric_definition_id);


--
-- Name: generations generations_experiment_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.generations
    ADD CONSTRAINT generations_experiment_id_fkey FOREIGN KEY (experiment_id) REFERENCES public.experiments(experiment_id) ON DELETE CASCADE;


--
-- Name: metrics metrics_generation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.metrics
    ADD CONSTRAINT metrics_generation_id_fkey FOREIGN KEY (generation_id) REFERENCES public.generations(generation_id) ON DELETE CASCADE;


--
-- Name: metrics metrics_variant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.metrics
    ADD CONSTRAINT metrics_variant_id_fkey FOREIGN KEY (variant_id) REFERENCES public.variants(variant_id) ON DELETE CASCADE;


--
-- Name: metrics metrics_wt_control_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.metrics
    ADD CONSTRAINT metrics_wt_control_id_fkey FOREIGN KEY (wt_control_id) REFERENCES public.wild_type_controls(wt_control_id) ON DELETE CASCADE;


--
-- Name: mutations mutations_variant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.mutations
    ADD CONSTRAINT mutations_variant_id_fkey FOREIGN KEY (variant_id) REFERENCES public.variants(variant_id) ON DELETE CASCADE;


--
-- Name: protein_features protein_features_wt_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.protein_features
    ADD CONSTRAINT protein_features_wt_id_fkey FOREIGN KEY (wt_id) REFERENCES public.wild_type_proteins(wt_id) ON DELETE CASCADE;


--
-- Name: variants variants_generation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.variants
    ADD CONSTRAINT variants_generation_id_fkey FOREIGN KEY (generation_id) REFERENCES public.generations(generation_id) ON DELETE CASCADE;


--
-- Name: variants variants_parent_variant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.variants
    ADD CONSTRAINT variants_parent_variant_id_fkey FOREIGN KEY (parent_variant_id) REFERENCES public.variants(variant_id) ON DELETE SET NULL;


--
-- Name: wild_type_controls wild_type_controls_generation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.wild_type_controls
    ADD CONSTRAINT wild_type_controls_generation_id_fkey FOREIGN KEY (generation_id) REFERENCES public.generations(generation_id) ON DELETE CASCADE;


--
-- Name: wild_type_controls wild_type_controls_wt_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.wild_type_controls
    ADD CONSTRAINT wild_type_controls_wt_id_fkey FOREIGN KEY (wt_id) REFERENCES public.wild_type_proteins(wt_id) ON DELETE CASCADE;


--
-- Name: wild_type_proteins wild_type_proteins_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: mariapaolaluciani
--

ALTER TABLE ONLY public.wild_type_proteins
    ADD CONSTRAINT wild_type_proteins_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(user_id) ON DELETE CASCADE;


--
-- Name: bio_pub; Type: PUBLICATION; Schema: -; Owner: mariapaolaluciani
--

CREATE PUBLICATION bio_pub WITH (publish = 'insert, update, delete, truncate');


ALTER PUBLICATION bio_pub OWNER TO mariapaolaluciani;

--
-- Name: bio_pub experiment_metadata; Type: PUBLICATION TABLE; Schema: public; Owner: mariapaolaluciani
--

ALTER PUBLICATION bio_pub ADD TABLE ONLY public.experiment_metadata;


--
-- Name: bio_pub experiments; Type: PUBLICATION TABLE; Schema: public; Owner: mariapaolaluciani
--

ALTER PUBLICATION bio_pub ADD TABLE ONLY public.experiments;


--
-- Name: bio_pub generations; Type: PUBLICATION TABLE; Schema: public; Owner: mariapaolaluciani
--

ALTER PUBLICATION bio_pub ADD TABLE ONLY public.generations;


--
-- Name: bio_pub metrics; Type: PUBLICATION TABLE; Schema: public; Owner: mariapaolaluciani
--

ALTER PUBLICATION bio_pub ADD TABLE ONLY public.metrics;


--
-- Name: bio_pub mutations; Type: PUBLICATION TABLE; Schema: public; Owner: mariapaolaluciani
--

ALTER PUBLICATION bio_pub ADD TABLE ONLY public.mutations;


--
-- Name: bio_pub protein_features; Type: PUBLICATION TABLE; Schema: public; Owner: mariapaolaluciani
--

ALTER PUBLICATION bio_pub ADD TABLE ONLY public.protein_features;


--
-- Name: bio_pub users; Type: PUBLICATION TABLE; Schema: public; Owner: mariapaolaluciani
--

ALTER PUBLICATION bio_pub ADD TABLE ONLY public.users;


--
-- Name: bio_pub variants; Type: PUBLICATION TABLE; Schema: public; Owner: mariapaolaluciani
--

ALTER PUBLICATION bio_pub ADD TABLE ONLY public.variants;


--
-- Name: bio_pub wild_type_proteins; Type: PUBLICATION TABLE; Schema: public; Owner: mariapaolaluciani
--

ALTER PUBLICATION bio_pub ADD TABLE ONLY public.wild_type_proteins;


--
-- Name: SCHEMA public; Type: ACL; Schema: -; Owner: pg_database_owner
--

GRANT USAGE ON SCHEMA public TO bio727p_role;
GRANT USAGE ON SCHEMA public TO repl_user;


--
-- Name: TABLE experiment_metadata; Type: ACL; Schema: public; Owner: mariapaolaluciani
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.experiment_metadata TO bio727p_role;
GRANT SELECT ON TABLE public.experiment_metadata TO repl_user;


--
-- Name: SEQUENCE experiment_metadata_metadata_id_seq; Type: ACL; Schema: public; Owner: mariapaolaluciani
--

GRANT ALL ON SEQUENCE public.experiment_metadata_metadata_id_seq TO bio727p_role;


--
-- Name: TABLE experiments; Type: ACL; Schema: public; Owner: mariapaolaluciani
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.experiments TO bio727p_role;
GRANT SELECT ON TABLE public.experiments TO repl_user;


--
-- Name: SEQUENCE experiments_experiment_id_seq; Type: ACL; Schema: public; Owner: mariapaolaluciani
--

GRANT ALL ON SEQUENCE public.experiments_experiment_id_seq TO bio727p_role;


--
-- Name: TABLE generations; Type: ACL; Schema: public; Owner: mariapaolaluciani
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.generations TO bio727p_role;
GRANT SELECT ON TABLE public.generations TO repl_user;


--
-- Name: SEQUENCE generations_generation_id_seq; Type: ACL; Schema: public; Owner: mariapaolaluciani
--

GRANT ALL ON SEQUENCE public.generations_generation_id_seq TO bio727p_role;


--
-- Name: TABLE metric_definitions; Type: ACL; Schema: public; Owner: mariapaolaluciani
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.metric_definitions TO bio727p_role;
GRANT SELECT ON TABLE public.metric_definitions TO repl_user;


--
-- Name: SEQUENCE metric_definitions_metric_definition_id_seq; Type: ACL; Schema: public; Owner: mariapaolaluciani
--

GRANT ALL ON SEQUENCE public.metric_definitions_metric_definition_id_seq TO bio727p_role;


--
-- Name: TABLE metrics; Type: ACL; Schema: public; Owner: mariapaolaluciani
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.metrics TO bio727p_role;
GRANT SELECT ON TABLE public.metrics TO repl_user;


--
-- Name: SEQUENCE metrics_metric_id_seq; Type: ACL; Schema: public; Owner: mariapaolaluciani
--

GRANT ALL ON SEQUENCE public.metrics_metric_id_seq TO bio727p_role;


--
-- Name: TABLE mutations; Type: ACL; Schema: public; Owner: mariapaolaluciani
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.mutations TO bio727p_role;
GRANT SELECT ON TABLE public.mutations TO repl_user;


--
-- Name: SEQUENCE mutations_mutation_id_seq; Type: ACL; Schema: public; Owner: mariapaolaluciani
--

GRANT ALL ON SEQUENCE public.mutations_mutation_id_seq TO bio727p_role;


--
-- Name: TABLE protein_features; Type: ACL; Schema: public; Owner: mariapaolaluciani
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.protein_features TO bio727p_role;
GRANT SELECT ON TABLE public.protein_features TO repl_user;


--
-- Name: SEQUENCE protein_features_feature_id_seq; Type: ACL; Schema: public; Owner: mariapaolaluciani
--

GRANT ALL ON SEQUENCE public.protein_features_feature_id_seq TO bio727p_role;


--
-- Name: TABLE users; Type: ACL; Schema: public; Owner: mariapaolaluciani
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.users TO bio727p_role;
GRANT SELECT ON TABLE public.users TO repl_user;


--
-- Name: SEQUENCE users_user_id_seq; Type: ACL; Schema: public; Owner: mariapaolaluciani
--

GRANT ALL ON SEQUENCE public.users_user_id_seq TO bio727p_role;


--
-- Name: TABLE variants; Type: ACL; Schema: public; Owner: mariapaolaluciani
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.variants TO bio727p_role;
GRANT SELECT ON TABLE public.variants TO repl_user;


--
-- Name: SEQUENCE variants_variant_id_seq; Type: ACL; Schema: public; Owner: mariapaolaluciani
--

GRANT ALL ON SEQUENCE public.variants_variant_id_seq TO bio727p_role;


--
-- Name: TABLE wild_type_controls; Type: ACL; Schema: public; Owner: mariapaolaluciani
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.wild_type_controls TO bio727p_role;
GRANT SELECT ON TABLE public.wild_type_controls TO repl_user;


--
-- Name: SEQUENCE wild_type_controls_wt_control_id_seq; Type: ACL; Schema: public; Owner: mariapaolaluciani
--

GRANT ALL ON SEQUENCE public.wild_type_controls_wt_control_id_seq TO bio727p_role;


--
-- Name: TABLE wild_type_proteins; Type: ACL; Schema: public; Owner: mariapaolaluciani
--

GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.wild_type_proteins TO bio727p_role;
GRANT SELECT ON TABLE public.wild_type_proteins TO repl_user;


--
-- Name: SEQUENCE wild_type_proteins_wt_id_seq; Type: ACL; Schema: public; Owner: mariapaolaluciani
--

GRANT ALL ON SEQUENCE public.wild_type_proteins_wt_id_seq TO bio727p_role;


--
-- Name: DEFAULT PRIVILEGES FOR SEQUENCES; Type: DEFAULT ACL; Schema: public; Owner: mariapaolaluciani
--

ALTER DEFAULT PRIVILEGES FOR ROLE mariapaolaluciani IN SCHEMA public GRANT ALL ON SEQUENCES TO bio727p_role;


--
-- Name: DEFAULT PRIVILEGES FOR TABLES; Type: DEFAULT ACL; Schema: public; Owner: mariapaolaluciani
--

ALTER DEFAULT PRIVILEGES FOR ROLE mariapaolaluciani IN SCHEMA public GRANT SELECT,INSERT,DELETE,UPDATE ON TABLES TO bio727p_role;
ALTER DEFAULT PRIVILEGES FOR ROLE mariapaolaluciani IN SCHEMA public GRANT SELECT ON TABLES TO repl_user;


--
-- PostgreSQL database dump complete
--

\unrestrict uXBG7rgzGylZBSh4AeInOH9A5fa9b93TpngWPPeRnCzSphAFdzub8NyCha5yukZ

