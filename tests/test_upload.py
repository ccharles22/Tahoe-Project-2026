"""Tests for file upload endpoints.
"""

import os
import json
import pytest
import tempfile
from unittest.mock import patch
import sys

# Ensure the repository root is on sys.path so `from app import create_app` works
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Ensure modules that read DATABASE_URL at import time use an in-memory DB for tests
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import create_app
from parsing.models import Base, engine, Variant, get_db_session, close_db_session


@pytest.fixture
def app():
    """Create test Flask app with in-memory database."""
    # Override DATABASE_URL for testing
    os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
    
    app = create_app()
    app.config['TESTING'] = True
    
    # Create tables
    with app.app_context():
        Base.metadata.create_all(bind=engine)
    
    yield app
    
    # Cleanup
    with app.app_context():
        Base.metadata.drop_all(bind=engine)
        close_db_session()


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture
def sample_tsv_file():
    """Create a temporary sample TSV file."""
    content = """variant_index	generation	parent_variant_index	dna_yield	protein_yield	assembled_dna_sequence
1	0		100.5	50.2	ATGCGATCGATCGATCG
2	1	1	120.3	55.8	ATGCGATCGATCGATCGATC
"""
    
    temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.tsv')
    temp_file.write(content)
    temp_file.close()
    
    yield temp_file.name
    
    # Cleanup
    if os.path.exists(temp_file.name):
        os.unlink(temp_file.name)


@pytest.fixture
def sample_json_file():
    """Create a temporary sample JSON file."""
    content = [
        {
            "variant_index": 1,
            "generation": 0,
            "parent_variant_index": None,
            "dna_yield": 100.5,
            "protein_yield": 50.2,
            "assembled_dna_sequence": "ATGCGATCGATCGATCG"
        },
        {
            "variant_index": 2,
            "generation": 1,
            "parent_variant_index": 1,
            "dna_yield": 120.3,
            "protein_yield": 55.8,
            "assembled_dna_sequence": "ATGCGATCGATCGATCGATC"
        }
    ]
    
    temp_file = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json')
    json.dump(content, temp_file)
    temp_file.close()
    
    yield temp_file.name
    
    # Cleanup
    if os.path.exists(temp_file.name):
        os.unlink(temp_file.name)


def test_health_endpoint(client):
    """Test health check endpoint."""
    response = client.get('/parsing/health')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['status'] == 'ok'


def test_upload_valid_tsv(client, sample_tsv_file):
    """Test uploading a valid TSV file."""
    with open(sample_tsv_file, 'rb') as f:
        response = client.post(
            '/parsing/upload',
            data={
                'file': (f, 'test.tsv'),
                'experiment_id': 1
            },
            content_type='multipart/form-data'
        )
    
    assert response.status_code == 200
    data = json.loads(response.data)
    
    assert data['success'] is True
    assert data['total_records'] == 2
    assert data['inserted_count'] == 2
    
    # Verify database records
    session = get_db_session()
    try:
        variants = session.query(Variant).filter_by(experiment_id=1).all()
        assert len(variants) == 2
        assert variants[0].variant_index == 1
        assert variants[0].generation == 0
        assert variants[0].parent_variant_index is None
        assert variants[1].variant_index == 2
        assert variants[1].generation == 1
        assert variants[1].parent_variant_index == 1
    finally:
        session.close()
        close_db_session()


def test_upload_valid_json(client, sample_json_file):
    """Test uploading a valid JSON file."""
    with open(sample_json_file, 'rb') as f:
        response = client.post(
            '/parsing/upload',
            data={
                'file': (f, 'test.json'),
                'experiment_id': 2
            },
            content_type='multipart/form-data'
        )
    
    assert response.status_code == 200
    data = json.loads(response.data)
    
    assert data['success'] is True
    assert data['total_records'] == 2
    assert data['inserted_count'] == 2
    
    # Verify database records
    session = get_db_session()
    try:
        variants = session.query(Variant).filter_by(experiment_id=2).all()
        assert len(variants) == 2
    finally:
        session.close()
        close_db_session()


def test_upload_invalid_extension(client):
    """Test uploading a file with invalid extension."""
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.txt')
    temp_file.write(b'some content')
    temp_file.close()
    
    try:
        with open(temp_file.name, 'rb') as f:
            response = client.post(
                '/parsing/upload',
                data={
                    'file': (f, 'test.txt'),
                    'experiment_id': 1
                },
                content_type='multipart/form-data'
            )
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
        assert 'Invalid file extension' in data['error']
    finally:
        os.unlink(temp_file.name)


def test_upload_no_file(client):
    """Test upload without providing a file."""
    response = client.post(
        '/parsing/upload',
        data={'experiment_id': 1},
        content_type='multipart/form-data'
    )
    
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data
    assert 'No file provided' in data['error']


def test_upload_db_rollback_on_error(client, sample_tsv_file):
    """Test that database rolls back on error during insert."""
    
    # Patch session.commit to raise an exception
    with patch('parsing.routes.get_db_session') as mock_get_session:
        mock_session = mock_get_session.return_value
        mock_session.add.return_value = None
        mock_session.commit.side_effect = Exception("Simulated DB error")
        mock_session.rollback.return_value = None
        mock_session.close.return_value = None
        
        with open(sample_tsv_file, 'rb') as f:
            response = client.post(
                '/parsing/upload',
                data={
                    'file': (f, 'test.tsv'),
                    'experiment_id': 99
                },
                content_type='multipart/form-data'
            )
        
        assert response.status_code == 500
        data = json.loads(response.data)
        assert 'error' in data
        assert data['error'] == 'Database error'
        
        # Verify rollback was called
        mock_session.rollback.assert_called_once()
    
    # Verify no records were inserted (using real session)
    session = get_db_session()
    try:
        variants = session.query(Variant).filter_by(experiment_id=99).all()
        assert len(variants) == 0
    finally:
        session.close()
        close_db_session()
