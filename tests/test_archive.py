import pytest
import os
import sqlite3
import tempfile
from datetime import datetime
from unittest.mock import patch

from app.services.archive import (
    get_db_path,
    init_database,
    archive_index_job,
    archive_scan_job,
    archive_title_rename,
    archive_webhook_trigger,
    query_archive
)

def test_get_db_path_with_env_var():
    """Test get_db_path with CHROMA_DB_PATH environment variable."""
    with tempfile.TemporaryDirectory() as tmpdir:
        chroma_path = os.path.join(tmpdir, "chroma")
        with patch.dict(os.environ, {"CHROMA_DB_PATH": chroma_path}):
            db_path = get_db_path()
            expected = os.path.join(tmpdir, "archive.db")
            assert db_path == expected

def test_get_db_path_with_chroma_suffix():
    """Test get_db_path when CHROMA_DB_PATH ends with /chroma."""
    with tempfile.TemporaryDirectory() as tmpdir:
        chroma_path = os.path.join(tmpdir, "chroma")
        with patch.dict(os.environ, {"CHROMA_DB_PATH": chroma_path}):
            db_path = get_db_path()
            # Should use parent directory
            assert os.path.dirname(db_path) == tmpdir
            assert db_path.endswith("archive.db")

def test_get_db_path_without_env_var():
    """Test get_db_path without environment variable (fallback to project root)."""
    # Clear environment
    with patch.dict(os.environ, {}, clear=True):
        db_path = get_db_path()
        # Should be in data directory relative to project root
        assert "archive.db" in db_path
        assert os.path.isdir(os.path.dirname(db_path)) or os.path.exists(os.path.dirname(db_path))

def test_get_db_path_creates_directory():
    """Test that get_db_path creates the directory if it doesn't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        chroma_path = os.path.join(tmpdir, "new_dir", "chroma")
        with patch.dict(os.environ, {"CHROMA_DB_PATH": chroma_path}):
            db_path = get_db_path()
            # Directory should be created
            assert os.path.isdir(os.path.dirname(db_path))

def test_init_database_creates_tables(temp_db_path):
    """Test that init_database creates all required tables."""
    with patch('app.services.archive.get_db_path', return_value=temp_db_path):
        init_database()
        
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        
        # Check all tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        assert 'index_jobs' in tables
        assert 'scan_jobs' in tables
        assert 'title_renames' in tables
        assert 'webhook_triggers' in tables
        
        conn.close()

def test_init_database_creates_indexes(temp_db_path):
    """Test that init_database creates indexes."""
    with patch('app.services.archive.get_db_path', return_value=temp_db_path):
        init_database()
        
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        
        # Check indexes exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = [row[0] for row in cursor.fetchall()]
        
        assert 'idx_index_jobs_timestamp' in indexes
        assert 'idx_scan_jobs_timestamp' in indexes
        assert 'idx_title_renames_timestamp' in indexes
        assert 'idx_title_renames_document_id' in indexes
        assert 'idx_webhook_triggers_timestamp' in indexes
        assert 'idx_webhook_triggers_document_id' in indexes
        
        conn.close()

def test_init_database_idempotent(temp_db_path):
    """Test that init_database can be called multiple times safely."""
    with patch('app.services.archive.get_db_path', return_value=temp_db_path):
        init_database()
        init_database()  # Call again
        
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM index_jobs")
        conn.close()

def test_archive_index_job(temp_db_path):
    """Test archiving an index job."""
    with patch('app.services.archive.get_db_path', return_value=temp_db_path):
        init_database()
        archive_index_job(documents_indexed=42)
        
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM index_jobs")
        rows = cursor.fetchall()
        conn.close()
        
        assert len(rows) == 1
        assert rows[0][2] == 42  # documents_indexed column

def test_archive_index_job_with_timestamp(temp_db_path):
    """Test archiving an index job with custom timestamp."""
    with patch('app.services.archive.get_db_path', return_value=temp_db_path):
        init_database()
        timestamp = "2024-01-01T12:00:00"
        archive_index_job(documents_indexed=10, timestamp=timestamp)
        
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT timestamp FROM index_jobs")
        row = cursor.fetchone()
        conn.close()
        
        assert row[0] == timestamp

def test_archive_scan_job(temp_db_path):
    """Test archiving a scan job."""
    with patch('app.services.archive.get_db_path', return_value=temp_db_path):
        init_database()
        archive_scan_job(total_documents=100, bad_title_documents=5)
        
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM scan_jobs")
        rows = cursor.fetchall()
        conn.close()
        
        assert len(rows) == 1
        assert rows[0][2] == 100  # total_documents
        assert rows[0][3] == 5     # bad_title_documents

def test_archive_title_rename(temp_db_path):
    """Test archiving a title rename."""
    with patch('app.services.archive.get_db_path', return_value=temp_db_path):
        init_database()
        archive_title_rename(document_id=123, old_title="Old Title", new_title="New Title")
        
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM title_renames")
        rows = cursor.fetchall()
        conn.close()
        
        assert len(rows) == 1
        assert rows[0][2] == 123  # document_id
        assert rows[0][3] == "Old Title"  # old_title
        assert rows[0][4] == "New Title"  # new_title

def test_archive_webhook_trigger(temp_db_path):
    """Test archiving a webhook trigger."""
    with patch('app.services.archive.get_db_path', return_value=temp_db_path):
        init_database()
        archive_webhook_trigger(document_id=456)
        
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM webhook_triggers")
        rows = cursor.fetchall()
        conn.close()
        
        assert len(rows) == 1
        assert rows[0][2] == 456  # document_id

def test_query_archive_index_type(temp_db_path):
    """Test querying archive for index type."""
    with patch('app.services.archive.get_db_path', return_value=temp_db_path):
        init_database()
        archive_index_job(documents_indexed=10, timestamp="2024-01-01T10:00:00")
        archive_index_job(documents_indexed=20, timestamp="2024-01-02T10:00:00")
        
        result = query_archive(archive_type='index', page=1, limit=10)
        
        assert result['total'] == 2
        assert len(result['items']) == 2
        assert result['page'] == 1
        assert result['limit'] == 10
        assert result['has_more'] is False

def test_query_archive_pagination(temp_db_path):
    """Test archive pagination."""
    with patch('app.services.archive.get_db_path', return_value=temp_db_path):
        init_database()
        # Create 5 records
        for i in range(5):
            archive_index_job(documents_indexed=i, timestamp=f"2024-01-0{i+1}T10:00:00")
        
        # First page
        result1 = query_archive(archive_type='index', page=1, limit=2)
        assert result1['total'] == 5
        assert len(result1['items']) == 2
        assert result1['has_more'] is True
        
        # Second page
        result2 = query_archive(archive_type='index', page=2, limit=2)
        assert result2['total'] == 5
        assert len(result2['items']) == 2
        assert result2['has_more'] is True
        
        # Last page
        result3 = query_archive(archive_type='index', page=3, limit=2)
        assert result3['total'] == 5
        assert len(result3['items']) == 1
        assert result3['has_more'] is False

def test_query_archive_date_filtering(temp_db_path):
    """Test archive date filtering."""
    with patch('app.services.archive.get_db_path', return_value=temp_db_path):
        init_database()
        archive_index_job(documents_indexed=10, timestamp="2024-01-01T10:00:00")
        archive_index_job(documents_indexed=20, timestamp="2024-01-15T10:00:00")
        archive_index_job(documents_indexed=30, timestamp="2024-02-01T10:00:00")
        
        # Filter by start_date
        result = query_archive(archive_type='index', start_date="2024-01-15T00:00:00")
        assert result['total'] == 2
        
        # Filter by end_date
        result = query_archive(archive_type='index', end_date="2024-01-20T00:00:00")
        assert result['total'] == 2
        
        # Filter by both
        result = query_archive(
            archive_type='index',
            start_date="2024-01-01T00:00:00",
            end_date="2024-01-20T00:00:00"
        )
        assert result['total'] == 2

def test_query_archive_all_types(temp_db_path):
    """Test querying all archive types."""
    with patch('app.services.archive.get_db_path', return_value=temp_db_path):
        init_database()
        archive_index_job(documents_indexed=10)
        archive_scan_job(total_documents=100, bad_title_documents=5)
        archive_title_rename(document_id=1, old_title="Old", new_title="New")
        archive_webhook_trigger(document_id=2)
        
        assert query_archive('index')['total'] == 1
        assert query_archive('scan')['total'] == 1
        assert query_archive('rename')['total'] == 1
        assert query_archive('webhook')['total'] == 1

def test_query_archive_invalid_type(temp_db_path):
    """Test that query_archive raises ValueError for invalid type."""
    with patch('app.services.archive.get_db_path', return_value=temp_db_path):
        init_database()
        with pytest.raises(ValueError, match="Invalid archive_type"):
            query_archive(archive_type='invalid')

def test_query_archive_ordering(temp_db_path):
    """Test that archive results are ordered by timestamp DESC."""
    with patch('app.services.archive.get_db_path', return_value=temp_db_path):
        init_database()
        archive_index_job(documents_indexed=10, timestamp="2024-01-01T10:00:00")
        archive_index_job(documents_indexed=20, timestamp="2024-01-03T10:00:00")
        archive_index_job(documents_indexed=30, timestamp="2024-01-02T10:00:00")
        
        result = query_archive(archive_type='index')
        timestamps = [item['timestamp'] for item in result['items']]
        
        # Should be descending order
        assert timestamps == sorted(timestamps, reverse=True)

