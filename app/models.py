from datetime import datetime
from app.db import db

class Experiment(db.Model):
    __tablename__ = "experiments"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(64), nullable=True) # optional user association
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
    features_json = db.Column(db.Text, nullable=True)   # store JSON as text for now
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

    strand = db.Column(db.String(1), nullable=True)   # "+" or "-"
    start_nt = db.Column(db.Integer, nullable=True)
    end_nt = db.Column(db.Integer, nullable=True)
    wraps = db.Column(db.Boolean, nullable=True)

    message = db.Column(db.Text, nullable=True)
    