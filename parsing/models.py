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

# Get database URL from environment or default to SQLite
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///data/variants.db')

# Create engine
engine = create_engine(
    DATABASE_URL,
    connect_args={'check_same_thread': False} if 'sqlite' in DATABASE_URL else {}
)

# Create session factory
SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))

# Base class for models
Base = declarative_base()


class Variant(Base):
    """Model for storing variant experimental data."""
    
    __tablename__ = 'variants'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    experiment_id = Column(Integer, nullable=False, index=True)
    variant_index = Column(Integer, nullable=False)
    generation = Column(Integer, nullable=False)
    parent_variant_index = Column(Integer, nullable=True)
    assembled_dna_sequence = Column(Text, nullable=False)
    # Allow yields to be nullable to tolerate upstream missing or malformed values.
    dna_yield = Column(Float, nullable=True)
    protein_yield = Column(Float, nullable=True)
    additional_metadata = Column(Text, nullable=True)  # JSON as text
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Unique constraint: same variant_index cannot exist twice in same experiment
    __table_args__ = (
        UniqueConstraint('experiment_id', 'variant_index', name='uq_experiment_variant'),
    )
    
    def __repr__(self):
        return f"<Variant(id={self.id}, experiment={self.experiment_id}, variant={self.variant_index}, gen={self.generation})>"


def init_db():
    """
    Create all database tables.
    Run this once to set up the database.
    """
    # Ensure data directory exists if using SQLite
    if 'sqlite' in DATABASE_URL:
        db_path = DATABASE_URL.replace('sqlite:///', '')
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)
    
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
