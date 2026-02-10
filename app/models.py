from flask_login import UserMixin
from datetime import datetime
from .extensions import db

class User(db.Model, UserMixin):
    __tablename__ = "users"
    __table_args__ = {"schema": "public", "extend_existing": True}

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