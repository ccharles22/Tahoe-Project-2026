import os
from datetime import datetime

from flask_login import UserMixin

from .extensions import db


# ---------------------------------------------------------------------------
# Models mapped to the EXISTING Postgres tables in bio727p_group_project.
# Column names and types match the remote schema exactly.
# ---------------------------------------------------------------------------

class User(db.Model, UserMixin):
    __tablename__ = "users"
    __table_args__ = {"schema": "public", "extend_existing": True}

    user_id = db.Column(db.BigInteger, primary_key=True)
    username = db.Column(db.String(255), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.Text, nullable=False)

    created_at = db.Column(db.DateTime(timezone=True), server_default=db.text("now()"))
    updated_at = db.Column(db.DateTime(timezone=True), server_default=db.text("now()"))

    def get_id(self) -> str:
        return str(self.user_id)


class WildtypeProtein(db.Model):
    __tablename__ = "wild_type_proteins"
    __table_args__ = {"extend_existing": True}

    wt_id = db.Column(db.BigInteger, primary_key=True)
    user_id = db.Column(db.BigInteger, db.ForeignKey("public.users.user_id"), nullable=False)
    uniprot_id = db.Column(db.String(32), unique=True, nullable=False)
    protein_name = db.Column(db.String, nullable=True)
    organism = db.Column(db.String, nullable=True)
    amino_acid_sequence = db.Column(db.Text, nullable=False)
    sequence_length = db.Column(db.Integer, nullable=False)
    plasmid_name = db.Column(db.String, nullable=True)
    plasmid_sequence = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.text("CURRENT_TIMESTAMP"))

    experiments = db.relationship("Experiment", backref="wt", lazy=True)
    features = db.relationship("ProteinFeature", backref="wt_protein", lazy=True, cascade="all, delete-orphan")


class ProteinFeature(db.Model):
    __tablename__ = "protein_features"
    __table_args__ = {"extend_existing": True}

    feature_id = db.Column(db.BigInteger, primary_key=True)
    wt_id = db.Column(db.BigInteger, db.ForeignKey("wild_type_proteins.wt_id"), nullable=False)
    feature_type = db.Column(db.String, nullable=False)
    description = db.Column(db.Text, nullable=True)
    start_position = db.Column(db.Integer, nullable=True)
    end_position = db.Column(db.Integer, nullable=True)


class Experiment(db.Model):
    __tablename__ = "experiments"
    __table_args__ = {"extend_existing": True}

    experiment_id = db.Column(db.BigInteger, primary_key=True)
    user_id = db.Column(db.BigInteger, db.ForeignKey("public.users.user_id"), nullable=False)
    wt_id = db.Column(db.BigInteger, db.ForeignKey("wild_type_proteins.wt_id"), nullable=False)
    name = db.Column(db.String, nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), server_default=db.text("now()"))
    updated_at = db.Column(db.DateTime(timezone=True), server_default=db.text("now()"))
    extra_metadata = db.Column(db.JSON, nullable=True)

    generations = db.relationship("Generation", backref="experiment", lazy=True, cascade="all, delete-orphan")


class Generation(db.Model):
    __tablename__ = "generations"
    __table_args__ = {"extend_existing": True}

    generation_id = db.Column(db.BigInteger, primary_key=True)
    experiment_id = db.Column(db.BigInteger, db.ForeignKey("experiments.experiment_id"), nullable=False)
    generation_number = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.text("CURRENT_TIMESTAMP"))

    variants = db.relationship("Variant", backref="generation", lazy=True, cascade="all, delete-orphan")


class Variant(db.Model):
    __tablename__ = "variants"
    __table_args__ = {"extend_existing": True}

    variant_id = db.Column(db.BigInteger, primary_key=True)
    generation_id = db.Column(db.BigInteger, db.ForeignKey("generations.generation_id"), nullable=False)
    parent_variant_id = db.Column(db.BigInteger, db.ForeignKey("variants.variant_id"), nullable=True)
    plasmid_variant_index = db.Column(db.String, nullable=False)
    assembled_dna_sequence = db.Column(db.Text, nullable=True)
    protein_sequence = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.text("CURRENT_TIMESTAMP"))
    extra_metadata = db.Column(db.JSON, nullable=True)

    metrics = db.relationship("Metric", backref="variant", lazy=True, cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return (
            f"<Variant(variant_id={self.variant_id}, gen_id={self.generation_id}, "
            f"index={self.plasmid_variant_index})>"
        )


class Metric(db.Model):
    __tablename__ = "metrics"
    __table_args__ = {"extend_existing": True}

    metric_id = db.Column(db.BigInteger, primary_key=True)
    generation_id = db.Column(db.BigInteger, db.ForeignKey("generations.generation_id"), nullable=False)
    variant_id = db.Column(db.BigInteger, db.ForeignKey("variants.variant_id"), nullable=True)
    wt_control_id = db.Column(db.BigInteger, db.ForeignKey("wild_type_controls.wt_control_id"), nullable=True)
    metric_definition_id = db.Column(db.BigInteger, db.ForeignKey("metric_definitions.metric_definition_id"), nullable=True)
    metric_name = db.Column(db.String, nullable=False)
    metric_type = db.Column(db.String, nullable=False)
    value = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String, nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.text("CURRENT_TIMESTAMP"))


class MetricDefinition(db.Model):
    __tablename__ = "metric_definitions"
    __table_args__ = {"extend_existing": True}

    metric_definition_id = db.Column(db.BigInteger, primary_key=True)
    name = db.Column(db.Text, unique=True, nullable=False)
    description = db.Column(db.Text, nullable=True)
    unit = db.Column(db.Text, nullable=True)
    metric_type = db.Column(db.Text, nullable=False)


class WildtypeControl(db.Model):
    __tablename__ = "wild_type_controls"
    __table_args__ = {"extend_existing": True}

    wt_control_id = db.Column(db.BigInteger, primary_key=True)
    generation_id = db.Column(db.BigInteger, db.ForeignKey("generations.generation_id"), nullable=False)
    wt_id = db.Column(db.BigInteger, db.ForeignKey("wild_type_proteins.wt_id"), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.text("CURRENT_TIMESTAMP"))


# ---------------------------------------------------------------------------
# StagingValidation — in-memory only (no DB table).
# Your Postgres user doesn't have CREATE TABLE permission, so we store
# validation results transiently via Flask session.
# ---------------------------------------------------------------------------