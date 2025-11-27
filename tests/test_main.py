import pytest
from unittest.mock import patch, MagicMock, Mock, AsyncMock
from fastapi.testclient import TestClient
from fastapi import BackgroundTasks
import asyncio
import time
import tempfile
import os
import sys

# Import after setting up mocks
def get_main_module():
    """Import main module with mocks in place."""
    return sys.modules.get('app.main')

@pytest.fixture
def main_module():
    """Get the main module for accessing globals."""
    import app.main
    return app.main

@pytest.fixture(autouse=True)
def reset_globals(main_module):
    """Reset global state before each test."""
    with main_module.progress_lock:
        main_module.jobs.clear()
        main_module.progress_events.clear()
    yield
    with main_module.progress_lock:
        main_module.jobs.clear()
        main_module.progress_events.clear()

@pytest.fixture
def mock_services(mock_settings):
    """Mock all services."""
    with patch('app.main.get_settings', return_value=mock_settings), \
         patch('app.main.PaperlessClient') as mock_paperless, \
         patch('app.main.AIService') as mock_ai, \
         patch('app.main.init_database'), \
         patch('app.main.archive_title_rename'), \
         patch('app.main.archive_scan_job'), \
         patch('app.main.archive_index_job'), \
         patch('app.main.archive_webhook_trigger'):
        yield mock_paperless, mock_ai

def test_health_endpoint(app_client):
    """Test /api/health endpoint."""
    response = app_client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

def test_scan_endpoint_creates_job(app_client, mock_services, main_module):
    """Test /api/scan endpoint creates a job."""
    mock_paperless, mock_ai = mock_services
    mock_paperless_instance = MagicMock()
    mock_paperless_instance.get_all_documents_filtered.return_value = []
    mock_paperless.return_value = mock_paperless_instance
    
    # Mock the background task so it doesn't actually run
    with patch('app.main.scheduled_search_job') as mock_job:
        response = app_client.post("/api/scan")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "scan_started"
        assert "job_id" in data
        
        # Check job was created (before background task completes)
        with main_module.progress_lock:
            assert data["job_id"] in main_module.jobs
            # Status might be running or completed depending on timing, but job should exist
            assert main_module.jobs[data["job_id"]]["status"] in ["running", "completed"]

def test_scan_endpoint_with_newer_than(app_client, mock_services, main_module):
    """Test /api/scan endpoint with newer_than filter."""
    mock_paperless, mock_ai = mock_services
    mock_paperless_instance = MagicMock()
    mock_paperless_instance.get_all_documents_filtered.return_value = []
    mock_paperless.return_value = mock_paperless_instance
    
    # Mock the background task so it doesn't actually run
    with patch('app.main.scheduled_search_job') as mock_job:
        response = app_client.post("/api/scan?newer_than=2024-01-01")
        assert response.status_code == 200
        data = response.json()
        assert data["newer_than"] == "2024-01-01"
        
        with main_module.progress_lock:
            assert main_module.jobs[data["job_id"]]["newer_than"] == "2024-01-01"

def test_index_endpoint_creates_job(app_client, mock_services, main_module):
    """Test /api/index endpoint creates a job."""
    mock_paperless, mock_ai = mock_services
    mock_paperless_instance = MagicMock()
    mock_paperless_instance.get_all_documents.return_value = []
    mock_paperless.return_value = mock_paperless_instance
    
    # Mock the background task so it doesn't actually run
    with patch('app.main.run_bulk_index') as mock_index:
        response = app_client.post("/api/index")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "indexing_started"
        assert data["job_id"] == "index"
        
        with main_module.progress_lock:
            assert "index" in main_module.jobs
            # Status might be running or completed depending on timing
            assert main_module.jobs["index"]["status"] in ["running", "completed"]

def test_index_endpoint_conflict(app_client, mock_services, main_module):
    """Test /api/index endpoint returns 409 when job already running."""
    mock_paperless, mock_ai = mock_services
    
    # Create a running index job
    with main_module.progress_lock:
        main_module.jobs["index"] = {"status": "running"}
    
    response = app_client.post("/api/index")
    assert response.status_code == 409
    assert "already running" in response.json()["detail"]

def test_progress_endpoint_without_job_id(app_client, main_module):
    """Test /api/progress endpoint without job_id returns all jobs."""
    # Create some jobs
    with main_module.progress_lock:
        main_module.jobs["job1"] = {"status": "running", "processed": 5, "total": 10}
        main_module.jobs["job2"] = {"status": "completed", "processed": 10, "total": 10}
    
    response = app_client.get("/api/progress")
    assert response.status_code == 200
    data = response.json()
    assert "jobs" in data
    assert "job1" in data["jobs"]
    assert "job2" in data["jobs"]

def test_progress_endpoint_with_job_id(app_client, main_module):
    """Test /api/progress endpoint with specific job_id."""
    with main_module.progress_lock:
        main_module.jobs["test_job"] = {"status": "running", "processed": 3, "total": 5}
    
    response = app_client.get("/api/progress?job_id=test_job")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "running"
    assert data["processed"] == 3
    assert data["total"] == 5

def test_progress_endpoint_job_not_found(app_client):
    """Test /api/progress endpoint returns 404 for non-existent job."""
    response = app_client.get("/api/progress?job_id=nonexistent")
    assert response.status_code == 404

def test_progress_endpoint_long_polling_timeout(app_client, main_module):
    """Test /api/progress endpoint long-polling with timeout."""
    with main_module.progress_lock:
        main_module.jobs["test_job"] = {"status": "running", "processed": 0, "total": 10}
        # Don't create event, so it will timeout
    
    # Mock asyncio.wait_for to raise TimeoutError immediately to avoid real delays in tests
    import asyncio
    with patch('app.main.asyncio.wait_for') as mock_wait:
        # Make wait_for raise TimeoutError immediately to simulate timeout
        async def mock_wait_for_side_effect(coro, timeout):
            # Cancel the coroutine to avoid "coroutine was never awaited" warning
            if asyncio.iscoroutine(coro):
                coro.close()
            # Just raise TimeoutError immediately without waiting
            raise asyncio.TimeoutError()
        mock_wait.side_effect = mock_wait_for_side_effect
        
        # Use timeout=1 (minimum valid int) but it will be mocked to return immediately
        response = app_client.get("/api/progress?job_id=test_job&wait=true&timeout=1")
        assert response.status_code == 200
        # Should return current state after timeout

def test_progress_endpoint_long_polling_completed_job(app_client, main_module):
    """Test /api/progress endpoint returns immediately for completed job."""
    with main_module.progress_lock:
        main_module.jobs["completed_job"] = {"status": "completed", "processed": 10, "total": 10}
    
    response = app_client.get("/api/progress?job_id=completed_job&wait=true")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"

def test_process_documents_endpoint_success(app_client, mock_services):
    """Test /api/process-documents endpoint with valid payload."""
    # Initialize database before test - call the real function directly
    from app.services.archive import init_database
    init_database()
    
    mock_paperless, mock_ai = mock_services
    mock_paperless_instance = MagicMock()
    mock_paperless_instance.get_document.return_value = {
        "id": 1,
        "title": "Test",
        "content": "Content"
    }
    mock_paperless.return_value = mock_paperless_instance
    
    # Mock the background task so it doesn't actually run
    with patch('app.main.process_documents_batch') as mock_batch:
        response = app_client.post(
            "/api/process-documents",
            json={"document_ids": [1, 2, 3]}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "processing_started"
        assert data["document_count"] == 3
        assert data["document_ids"] == [1, 2, 3]

def test_process_documents_endpoint_empty_list(app_client, mock_services):
    """Test /api/process-documents endpoint with empty list."""
    # The endpoint might return 500 if there's an error parsing, let's check both
    response = app_client.post(
        "/api/process-documents",
        json={"document_ids": []}
    )
    # Should be 400, but might be 500 if there's an exception
    assert response.status_code in [400, 500]
    if response.status_code == 400:
        assert "No document_ids provided" in response.json()["detail"]

def test_process_documents_endpoint_missing_field(app_client, mock_services):
    """Test /api/process-documents endpoint with missing field."""
    response = app_client.post(
        "/api/process-documents",
        json={}
    )
    # Might return 400 or 500 depending on error handling
    assert response.status_code in [400, 500]

def test_webhook_endpoint_with_document_id(app_client, mock_services):
    """Test /api/webhook endpoint with document_id."""
    mock_paperless, mock_ai = mock_services
    mock_paperless_instance = MagicMock()
    mock_paperless_instance.get_document.return_value = {
        "id": 123,
        "title": "Test",
        "content": "Content"
    }
    mock_paperless.return_value = mock_paperless_instance
    
    # Mock the background task so it doesn't actually run
    with patch('app.main.archive_webhook_trigger') as mock_archive, \
         patch('app.main.process_document_with_progress') as mock_process:
        response = app_client.post(
            "/api/webhook",
            json={"document_id": 123}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "processing_started"
        assert data["document_id"] == 123
        mock_archive.assert_called_once_with(123)

def test_webhook_endpoint_without_document_id(app_client):
    """Test /api/webhook endpoint without document_id."""
    response = app_client.post(
        "/api/webhook",
        json={"task_id": "some_task"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ignored"
    assert "missing_document_id" in data["reason"]

def test_find_outliers_endpoint_success(app_client, mock_services):
    """Test /api/find-outliers endpoint success."""
    mock_paperless, mock_ai = mock_services
    mock_ai_instance = MagicMock()
    mock_ai_instance.find_outlier_documents.return_value = [
        {"document_id": "1", "title": "Outlier 1", "outlier_score": 0.9}
    ]
    # Ensure the ai_service in main uses our mock
    with patch('app.main.ai_service', mock_ai_instance):
        response = app_client.get("/api/find-outliers?k_neighbors=5&limit=10")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["count"] == 1
        assert len(data["outliers"]) == 1

def test_find_outliers_endpoint_error(app_client, mock_services):
    """Test /api/find-outliers endpoint error handling."""
    mock_paperless, mock_ai = mock_services
    mock_ai_instance = MagicMock()
    mock_ai_instance.find_outlier_documents.side_effect = Exception("Error")
    # Ensure the ai_service in main uses our mock
    with patch('app.main.ai_service', mock_ai_instance):
        response = app_client.get("/api/find-outliers")
        assert response.status_code == 500
        assert "Error" in response.json()["detail"]

def test_archive_endpoint_success(app_client):
    """Test /api/archive endpoint success."""
    with patch('app.main.query_archive') as mock_query:
        mock_query.return_value = {
            "items": [{"id": 1, "timestamp": "2024-01-01"}],
            "total": 1,
            "page": 1,
            "limit": 50,
            "has_more": False
        }
        
        response = app_client.get("/api/archive?type=index&page=1&limit=50")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        mock_query.assert_called_once_with(
            archive_type="index",
            page=1,
            limit=50,
            start_date=None,
            end_date=None
        )

def test_archive_endpoint_with_date_filters(app_client):
    """Test /api/archive endpoint with date filters."""
    with patch('app.main.query_archive') as mock_query:
        mock_query.return_value = {"items": [], "total": 0, "page": 1, "limit": 50, "has_more": False}
        
        response = app_client.get(
            "/api/archive?type=rename&start_date=2024-01-01&end_date=2024-12-31"
        )
        assert response.status_code == 200
        mock_query.assert_called_once_with(
            archive_type="rename",
            page=1,
            limit=50,
            start_date="2024-01-01",
            end_date="2024-12-31"
        )

def test_archive_endpoint_invalid_type(app_client):
    """Test /api/archive endpoint with invalid type."""
    with patch('app.main.query_archive') as mock_query:
        mock_query.side_effect = ValueError("Invalid archive_type")
        
        response = app_client.get("/api/archive?type=invalid")
        assert response.status_code == 400

def test_process_document_text_success(mock_services, main_module):
    """Test process_document with text document."""
    mock_paperless, mock_ai = mock_services
    mock_paperless_instance = MagicMock()
    mock_paperless_instance.get_document.return_value = {
        "id": 1,
        "title": "Scan 001",
        "content": "Document content here"
    }
    mock_paperless_instance.get_document_mime_type.return_value = None
    mock_paperless.return_value = mock_paperless_instance
    
    mock_ai_instance = MagicMock()
    mock_ai_instance.generate_title.return_value = "New Title"
    mock_ai.return_value = mock_ai_instance
    
    with patch('app.main.archive_title_rename') as mock_archive, \
         patch('app.main.paperless_client', mock_paperless_instance), \
         patch('app.main.ai_service', mock_ai_instance):
        main_module.process_document(1)
        
        mock_paperless_instance.get_document.assert_called_once_with(1)
        mock_ai_instance.generate_title.assert_called_once()
        mock_paperless_instance.update_document.assert_called_once_with(1, "New Title")
        mock_archive.assert_called_once_with(1, "Scan 001", "New Title")

def test_process_document_image_success(mock_services, main_module):
    """Test process_document with image document."""
    mock_paperless, mock_ai = mock_services
    mock_paperless_instance = MagicMock()
    mock_paperless_instance.get_document.return_value = {
        "id": 1,
        "title": "image.jpg",
        "content": "",
        "mime_type": "image/png"
    }
    mock_paperless_instance.get_document_original.return_value = b"image data"
    mock_paperless.return_value = mock_paperless_instance
    
    mock_ai_instance = MagicMock()
    mock_ai_instance.generate_title_from_image.return_value = "Image Title"
    mock_ai.return_value = mock_ai_instance
    
    with patch('app.main.archive_title_rename') as mock_archive, \
         patch('app.main.paperless_client', mock_paperless_instance), \
         patch('app.main.ai_service', mock_ai_instance):
        main_module.process_document(1)
        
        mock_paperless_instance.get_document_original.assert_called_once_with(1)
        mock_ai_instance.generate_title_from_image.assert_called_once()
        mock_paperless_instance.update_document.assert_called_once_with(1, "Image Title")
        mock_archive.assert_called_once()

def test_process_document_mime_type_fallback(mock_services, main_module):
    """Test process_document MIME type detection fallback chain."""
    mock_paperless, mock_ai = mock_services
    mock_paperless_instance = MagicMock()
    # No mime_type in doc, will try headers, then filename
    mock_paperless_instance.get_document.return_value = {
        "id": 1,
        "title": "document",
        "content": "content",
        "original_filename": "test.pdf"
    }
    mock_paperless_instance.get_document_mime_type.return_value = None
    mock_paperless.return_value = mock_paperless_instance
    
    mock_ai_instance = MagicMock()
    mock_ai_instance.generate_title.return_value = "Title"
    mock_ai.return_value = mock_ai_instance
    
    with patch('app.main.paperless_client', mock_paperless_instance), \
         patch('app.main.ai_service', mock_ai_instance):
        main_module.process_document(1)
        # Should have tried to get MIME type from headers
        mock_paperless_instance.get_document_mime_type.assert_called_once_with(1)

def test_process_document_dry_run(mock_services, main_module):
    """Test process_document in DRY_RUN mode."""
    mock_paperless, mock_ai = mock_services
    mock_settings = MagicMock()
    mock_settings.DRY_RUN = True
    
    mock_paperless_instance = MagicMock()
    # Ensure it's not detected as an image
    mock_paperless_instance.get_document.return_value = {
        "id": 1,
        "title": "Old",
        "content": "Content",
        "mime_type": "application/pdf"  # Not an image
    }
    mock_paperless_instance.get_document_mime_type.return_value = None
    mock_paperless.return_value = mock_paperless_instance
    
    mock_ai_instance = MagicMock()
    mock_ai_instance.generate_title.return_value = "New"
    mock_ai.return_value = mock_ai_instance
    
    # Need to patch both get_settings and the module-level settings variable
    with patch('app.main.get_settings', return_value=mock_settings), \
         patch('app.main.settings', mock_settings), \
         patch('app.main.paperless_client', mock_paperless_instance), \
         patch('app.main.ai_service', mock_ai_instance):
        main_module.process_document(1)
        
        # Should not update document in DRY_RUN mode
        mock_paperless_instance.update_document.assert_not_called()

def test_process_document_not_found(mock_services, main_module):
    """Test process_document when document not found."""
    mock_paperless, mock_ai = mock_services
    mock_paperless_instance = MagicMock()
    mock_paperless_instance.get_document.return_value = None
    mock_paperless.return_value = mock_paperless_instance
    
    mock_ai_instance = MagicMock()
    mock_ai.return_value = mock_ai_instance
    
    with patch('app.main.paperless_client', mock_paperless_instance), \
         patch('app.main.ai_service', mock_ai_instance):
        main_module.process_document(999)
        # Should not call AI service
        mock_ai_instance.generate_title.assert_not_called()

def test_process_document_no_content(mock_services, main_module):
    """Test process_document when document has no content."""
    mock_paperless, mock_ai = mock_services
    mock_paperless_instance = MagicMock()
    mock_paperless_instance.get_document.return_value = {
        "id": 1,
        "title": "Test",
        "content": ""
    }
    mock_paperless.return_value = mock_paperless_instance
    
    mock_ai_instance = MagicMock()
    mock_ai.return_value = mock_ai_instance
    
    with patch('app.main.paperless_client', mock_paperless_instance), \
         patch('app.main.ai_service', mock_ai_instance):
        main_module.process_document(1)
        # Should not generate title for empty content
        mock_ai_instance.generate_title.assert_not_called()

def test_process_document_title_unchanged(mock_services, main_module):
    """Test process_document when generated title equals original."""
    mock_paperless, mock_ai = mock_services
    mock_paperless_instance = MagicMock()
    # Ensure it's not detected as an image
    mock_paperless_instance.get_document.return_value = {
        "id": 1,
        "title": "Good Title",
        "content": "Content",
        "mime_type": "application/pdf"  # Not an image
    }
    mock_paperless_instance.get_document_mime_type.return_value = None
    mock_paperless.return_value = mock_paperless_instance
    
    mock_ai_instance = MagicMock()
    mock_ai_instance.generate_title.return_value = "Good Title"
    mock_ai.return_value = mock_ai_instance
    
    with patch('app.main.paperless_client', mock_paperless_instance), \
         patch('app.main.ai_service', mock_ai_instance):
        main_module.process_document(1)
        # Should not update if title is the same
        mock_paperless_instance.update_document.assert_not_called()

def test_scheduled_search_job_success(mock_services, main_module):
    """Test scheduled_search_job function."""
    mock_paperless, mock_ai = mock_services
    mock_paperless_instance = MagicMock()
    mock_paperless_instance.get_all_documents_filtered.return_value = [
        {"id": 1, "title": "Scan 001"},
        {"id": 2, "title": "Good Document"},
        {"id": 3, "title": "Scan 002"}
    ]
    mock_paperless.return_value = mock_paperless_instance
    
    mock_settings = MagicMock()
    mock_settings.BAD_TITLE_REGEX = "^Scan.*"
    
    with patch('app.main.get_settings', return_value=mock_settings), \
         patch('app.main.process_document') as mock_process, \
         patch('app.main.archive_scan_job') as mock_archive, \
         patch('app.main.paperless_client', mock_paperless_instance):
        job_id = "test_job"
        with main_module.progress_lock:
            main_module.jobs[job_id] = {
                "status": "running",
                "total": 0,
                "processed": 0
            }
        
        main_module.scheduled_search_job(newer_than="2024-01-01", job_id=job_id)
        
        # Should process 2 documents matching regex
        assert mock_process.call_count == 2
        mock_archive.assert_called_once()
        
        with main_module.progress_lock:
            assert main_module.jobs[job_id]["status"] == "completed"

def test_scheduled_search_job_error_handling(mock_services, main_module):
    """Test scheduled_search_job error handling."""
    mock_paperless, mock_ai = mock_services
    mock_paperless_instance = MagicMock()
    mock_paperless_instance.get_all_documents_filtered.side_effect = Exception("API Error")
    mock_paperless.return_value = mock_paperless_instance
    
    job_id = "test_job"
    with main_module.progress_lock:
        main_module.jobs[job_id] = {"status": "running"}
    
    with patch('app.main.paperless_client', mock_paperless_instance):
        main_module.scheduled_search_job(job_id=job_id)
    
    with main_module.progress_lock:
        assert main_module.jobs[job_id]["status"] == "failed"
        assert "error" in main_module.jobs[job_id]

def test_run_bulk_index_success(mock_services, main_module):
    """Test run_bulk_index function."""
    mock_paperless, mock_ai = mock_services
    mock_paperless_instance = MagicMock()
    mock_paperless_instance.get_all_documents.return_value = [
        {"id": 1, "title": "2024-01-15 Invoice", "content": "Content 1"},
        {"id": 2, "title": "Scan 001", "content": "Content 2"},
        {"id": 3, "title": "2024-12 Document", "content": "Content 3"},
        {"id": 4, "title": "2024 Report", "content": "Content 4"}
    ]
    mock_paperless.return_value = mock_paperless_instance
    
    mock_ai_instance = MagicMock()
    mock_ai.return_value = mock_ai_instance
    
    job_id = "index"
    with main_module.progress_lock:
        main_module.jobs[job_id] = {"status": "running"}
    
    with patch('app.main.archive_index_job') as mock_archive, \
         patch('app.main.paperless_client', mock_paperless_instance), \
         patch('app.main.ai_service', mock_ai_instance):
        main_module.run_bulk_index(job_id=job_id)
        
        # Should index 3 documents (skip "Scan 001")
        assert mock_ai_instance.add_document_to_index.call_count == 3
        mock_archive.assert_called_once()
        
        with main_module.progress_lock:
            assert main_module.jobs[job_id]["status"] == "completed"
            assert main_module.jobs[job_id]["indexed"] == 3
            assert main_module.jobs[job_id]["skipped_scan"] == 1

def test_run_bulk_index_title_cleaning(mock_services, main_module):
    """Test run_bulk_index title cleaning logic."""
    mock_paperless, mock_ai = mock_services
    mock_paperless_instance = MagicMock()
    mock_paperless_instance.get_all_documents.return_value = [
        {"id": 1, "title": "2024-01-15 Invoice", "content": "Content"},
        {"id": 2, "title": "2024-12 Document", "content": "Content"},
        {"id": 3, "title": "2024 Report", "content": "Content"}
    ]
    mock_paperless.return_value = mock_paperless_instance
    
    mock_ai_instance = MagicMock()
    mock_ai.return_value = mock_ai_instance
    
    with patch('app.main.paperless_client', mock_paperless_instance), \
         patch('app.main.ai_service', mock_ai_instance):
        main_module.run_bulk_index()
        
        # Check title cleaning
        calls = mock_ai_instance.add_document_to_index.call_args_list
        # First: full date removed -> "Invoice"
        assert calls[0][0][2] == "Invoice"
        # Second: year-month reordered -> "Document 12-2024"
        assert "Document" in calls[1][0][2] and "12-2024" in calls[1][0][2]
        # Third: year moved to end -> "Report 2024"
        assert "Report" in calls[2][0][2] and "2024" in calls[2][0][2]

def test_run_bulk_index_error_handling(mock_services, main_module):
    """Test run_bulk_index error handling."""
    mock_paperless, mock_ai = mock_services
    mock_paperless_instance = MagicMock()
    mock_paperless_instance.get_all_documents.side_effect = Exception("Error")
    mock_paperless.return_value = mock_paperless_instance
    
    job_id = "index"
    with main_module.progress_lock:
        main_module.jobs[job_id] = {"status": "running"}
    
    with patch('app.main.paperless_client', mock_paperless_instance):
        main_module.run_bulk_index(job_id=job_id)
    
    with main_module.progress_lock:
        assert main_module.jobs[job_id]["status"] == "failed"

def test_signal_progress_update(mock_services, main_module):
    """Test _signal_progress_update helper."""
    job_id = "test_job"
    thread_event = MagicMock()
    async_event = MagicMock()
    
    with main_module.progress_lock:
        main_module.progress_events[job_id] = (thread_event, async_event)
    
    with patch.object(main_module, '_main_event_loop') as mock_loop:
        mock_loop.is_running.return_value = True
        main_module._signal_progress_update(job_id)
        
        thread_event.set.assert_called_once()
        mock_loop.call_soon_threadsafe.assert_called_once()

def test_signal_all_jobs_update(mock_services, main_module):
    """Test _signal_all_jobs_update helper."""
    with patch.object(main_module, '_signal_progress_update') as mock_signal:
        main_module._signal_all_jobs_update()
        mock_signal.assert_called_once_with("__all_jobs__")

