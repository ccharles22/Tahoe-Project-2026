"""
SQLAlchemy models and database setup for variant storage.
"""

import os
import json
import logging
from datetime import datetime
from sqlalchemy import (
    create_engine, 
    Column, 
    Integer, 
    Float, 
    String, 
    Text, 
    DateTime,
    UniqueConstraint
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session

# Configure logging
logger = logging.getLogger(__name__)

# Get database URL from environment.
# Fail fast if not provided to avoid silently writing to a local SQLite file.
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Set it to the Bio727p Postgres URL before starting the app."
    )

# Create engine
engine = create_engine(
    DATABASE_URL,
    connect_args={'check_same_thread': False} if 'sqlite' in DATABASE_URL else {}
)

# Create session factory
SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))

# Base class for models
Base = declarative_base()


class Experiment(Base):
    """Model for experiment table - matches existing DB schema."""
    __tablename__ = 'experiments'
    
    experiment_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    wt_id = Column(Integer, nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
    extra_metadata = Column(Text, nullable=True)  # jsonb
    
    def __repr__(self):
        return f"<Experiment(id={self.experiment_id}, name={self.name})>"


class Generation(Base):
    """Model for generation table - matches existing DB schema."""
    __tablename__ = 'generations'
    
    generation_id = Column(Integer, primary_key=True, autoincrement=True)
    experiment_id = Column(Integer, nullable=False, index=True)
    generation_number = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint('experiment_id', 'generation_number', name='generations_experiment_id_generation_number_key'),
    )
    
    def __repr__(self):
        return f"<Generation(id={self.generation_id}, exp={self.experiment_id}, gen={self.generation_number})>"


class Variant(Base):
    """Model for storing variant experimental data - matches existing DB schema."""
    
    __tablename__ = 'variants'
    
    variant_id = Column(Integer, primary_key=True, autoincrement=True)
    generation_id = Column(Integer, nullable=False, index=True)
    parent_variant_id = Column(Integer, nullable=True, index=True)
    plasmid_variant_index = Column(String(50), nullable=False)
    assembled_dna_sequence = Column(Text, nullable=True)
    protein_sequence = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Unique constraint: same plasmid_variant_index cannot exist twice in same generation
    __table_args__ = (
        UniqueConstraint('generation_id', 'plasmid_variant_index', name='variants_generation_id_plasmid_variant_index_key'),
    )
    
    def __repr__(self):
        return f"<Variant(id={self.variant_id}, gen_id={self.generation_id}, index={self.plasmid_variant_index})>"


class Metric(Base):
    """Model for metrics table - stores dna_yield, protein_yield, etc."""
    __tablename__ = 'metrics'
    
    metric_id = Column(Integer, primary_key=True, autoincrement=True)
    generation_id = Column(Integer, nullable=False, index=True)
    variant_id = Column(Integer, nullable=True, index=True)
    wt_control_id = Column(Integer, nullable=True)
    metric_name = Column(String(255), nullable=False, index=True)
    metric_type = Column(String(20), nullable=False)  # 'raw', 'normalized', 'derived'
    value = Column(Float, nullable=False)
    unit = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<Metric(id={self.metric_id}, name={self.metric_name}, value={self.value})>"


def init_db():
    """
    Verify database connection and check if tables exist.
    Does NOT create tables - assumes they already exist in the database.
    """
    # Ensure data directory exists if using SQLite
    if 'sqlite' in DATABASE_URL:
        db_path = DATABASE_URL.replace('sqlite:///', '')
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)
    
    # For PostgreSQL, just verify connection by checking if tables exist
    try:
        session = SessionLocal()
        # Check if main tables exist by attempting to query them
        session.query(Variant).first()
        session.close()
        logger.info(f"Database connection verified at {DATABASE_URL}")
    except Exception as e:
        logger.warning(f"Database connection issue: {e}")
        # If tables don't exist and it's SQLite, create them
        if 'sqlite' in DATABASE_URL:
            Base.metadata.create_all(bind=engine)
            logger.info(f"Database tables created at {DATABASE_URL}")


def get_db_session():
    """
    Get a database session.
    Caller is responsible for closing it.
    """
    return SessionLocal()


def close_db_session():
    """Close the scoped session."""
    SessionLocal.remove()


if __name__ == '__main__':
    # Allow running as script to initialize DB
    init_db()
