import os
from datetime import datetime

from flask_login import UserMixin

from .extensions import db


def _user_table_args():
    db_url = os.getenv("DATABASE_URL", "")
    if db_url.startswith("sqlite"):
        return {"extend_existing": True}
    return {"schema": "public", "extend_existing": True}

class User(db.Model, UserMixin):
    __tablename__ = "users"
    __table_args__ = _user_table_args()

    user_id = db.Column(db.BigInteger, primary_key=True)
    username = db.Column(db.String(255), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(64), nullable=False)  # matches your DB CHAR(64)

    created_at = db.Column(db.DateTime, server_default=db.text("CURRENT_TIMESTAMP"))
    updated_at = db.Column(db.DateTime, server_default=db.text("CURRENT_TIMESTAMP"))

    def get_id(self) -> str:
        # Flask-Login expects a string
        return str(self.user_id)
    


class Experiment(db.Model):
    __tablename__ = "experiments"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(64), nullable=True)
    status = db.Column(db.String(32), nullable=False, default="CREATED")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    wt = db.relationship("WildtypeProtein", uselist=False, backref="experiment", cascade="all, delete-orphan")
    plasmid = db.relationship("Plasmid", uselist=False, backref="experiment", cascade="all, delete-orphan")
    validation = db.relationship("StagingValidation", uselist=False, backref="experiment", cascade="all, delete-orphan")


class WildtypeProtein(db.Model):
    __tablename__ = "wildtype_protein"
    experiment_id = db.Column(db.Integer, db.ForeignKey("experiments.id"), primary_key=True)

    uniprot_accession = db.Column(db.String(32), nullable=False)
    wt_protein_sequence = db.Column(db.Text, nullable=True)
    features_json = db.Column(db.Text, nullable=True)
    protein_length = db.Column(db.Integer, nullable=True)
    plasmid_length = db.Column(db.Integer, nullable=True)


class Plasmid(db.Model):
    __tablename__ = "plasmid"
    experiment_id = db.Column(db.Integer, db.ForeignKey("experiments.id"), primary_key=True)
    dna_sequence = db.Column(db.Text, nullable=False)


class StagingValidation(db.Model):
    __tablename__ = "staging_validation"
    experiment_id = db.Column(db.Integer, db.ForeignKey("experiments.id"), primary_key=True)

    is_valid = db.Column(db.Boolean, nullable=False, default=False)
    identity = db.Column(db.Float, nullable=True)
    coverage = db.Column(db.Float, nullable=True)

    strand = db.Column(db.String(1), nullable=True)
    start_nt = db.Column(db.Integer, nullable=True)
    end_nt = db.Column(db.Integer, nullable=True)
    wraps = db.Column(db.Boolean, nullable=True)

    message = db.Column(db.Text, nullable=True)


class Variant(db.Model):
    __tablename__ = "variants"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    experiment_id = db.Column(db.Integer, nullable=False, index=True)
    variant_index = db.Column(db.Integer, nullable=False)
    generation = db.Column(db.Integer, nullable=False)
    parent_variant_index = db.Column(db.Integer, nullable=True)
    assembled_dna_sequence = db.Column(db.Text, nullable=False)
    # Allow yields to be nullable to tolerate upstream missing or malformed values.
    dna_yield = db.Column(db.Float, nullable=True)
    protein_yield = db.Column(db.Float, nullable=True)
    additional_metadata = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("experiment_id", "variant_index", name="uq_experiment_variant"),
    )

    def __repr__(self) -> str:
        return (
            f"<Variant(id={self.id}, experiment={self.experiment_id}, "
            f"variant={self.variant_index}, gen={self.generation})>"
        )