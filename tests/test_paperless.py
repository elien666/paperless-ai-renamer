import pytest
from unittest.mock import patch, MagicMock, Mock
import requests
from app.services.paperless import PaperlessClient

@pytest.fixture
def mock_settings():
    """Mock settings for PaperlessClient."""
    settings = MagicMock()
    settings.PAPERLESS_API_URL = "http://test-paperless:8000"
    settings.PAPERLESS_API_TOKEN = "test-token"
    return settings

def test_paperless_client_init(mock_settings):
    """Test PaperlessClient initialization."""
    # Need to clear the cache and patch get_settings properly
    from app.services.paperless import get_settings
    if hasattr(get_settings, 'cache_clear'):
        get_settings.cache_clear()
    
    # Also need to patch the module-level settings
    with patch('app.services.paperless.get_settings', return_value=mock_settings), \
         patch('app.services.paperless.settings', mock_settings):
        client = PaperlessClient()
        assert client.base_url == "http://test-paperless:8000"
        assert "Token test-token" in client.headers["Authorization"]
        assert "application/json; version=2" in client.headers["Accept"]

def test_paperless_client_url_normalization(mock_settings):
    """Test that base_url is normalized (trailing slash removed)."""
    mock_settings.PAPERLESS_API_URL = "http://test-paperless:8000/"
    # Need to clear the cache
    from app.services.paperless import get_settings
    if hasattr(get_settings, 'cache_clear'):
        get_settings.cache_clear()
    
    # Also need to patch the module-level settings
    with patch('app.services.paperless.get_settings', return_value=mock_settings), \
         patch('app.services.paperless.settings', mock_settings):
        client = PaperlessClient()
        assert client.base_url == "http://test-paperless:8000"

def test_get_document_success(mock_settings):
    """Test successful document retrieval."""
    with patch('app.services.paperless.get_settings', return_value=mock_settings), \
         patch('app.services.paperless.requests.get') as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": 1, "title": "Test Doc", "content": "Content"}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        client = PaperlessClient()
        doc = client.get_document(1)
        
        assert doc["id"] == 1
        assert doc["title"] == "Test Doc"
        mock_get.assert_called_once()
        assert "api/documents/1/" in mock_get.call_args[0][0]

def test_get_document_not_found(mock_settings):
    """Test document retrieval when document doesn't exist."""
    with patch('app.services.paperless.get_settings', return_value=mock_settings), \
         patch('app.services.paperless.requests.get') as mock_get:
        mock_get.side_effect = requests.HTTPError("404 Not Found")
        
        client = PaperlessClient()
        doc = client.get_document(999)
        
        assert doc is None

def test_get_document_network_error(mock_settings):
    """Test document retrieval with network error."""
    with patch('app.services.paperless.get_settings', return_value=mock_settings), \
         patch('app.services.paperless.requests.get') as mock_get:
        mock_get.side_effect = requests.RequestException("Connection error")
        
        client = PaperlessClient()
        doc = client.get_document(1)
        
        assert doc is None

def test_update_document_success(mock_settings):
    """Test successful document update."""
    with patch('app.services.paperless.get_settings', return_value=mock_settings), \
         patch('app.services.paperless.requests.patch') as mock_patch:
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_patch.return_value = mock_response
        
        client = PaperlessClient()
        result = client.update_document(1, "New Title")
        
        assert result is True
        mock_patch.assert_called_once()
        call_args = mock_patch.call_args
        assert "api/documents/1/" in call_args[0][0]
        assert call_args[1]["json"] == {"title": "New Title"}

def test_update_document_error(mock_settings):
    """Test document update with error."""
    with patch('app.services.paperless.get_settings', return_value=mock_settings), \
         patch('app.services.paperless.requests.patch') as mock_patch:
        mock_patch.side_effect = requests.RequestException("Update failed")
        
        client = PaperlessClient()
        result = client.update_document(1, "New Title")
        
        assert result is False

def test_search_documents_basic(mock_settings):
    """Test basic document search."""
    with patch('app.services.paperless.get_settings', return_value=mock_settings), \
         patch('app.services.paperless.requests.get') as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": [{"id": 1, "title": "Doc 1"}]}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        client = PaperlessClient()
        results = client.search_documents("test query")
        
        assert len(results) == 1
        assert results[0]["id"] == 1
        mock_get.assert_called_once()
        assert mock_get.call_args[1]["params"]["query"] == "test query"

def test_search_documents_with_date_filter(mock_settings):
    """Test document search with newer_than date filter."""
    with patch('app.services.paperless.get_settings', return_value=mock_settings), \
         patch('app.services.paperless.requests.get') as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": []}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        client = PaperlessClient()
        client.search_documents("query", newer_than="2024-01-01")
        
        params = mock_get.call_args[1]["params"]
        assert params["query"] == "query"
        assert params["created__date__gt"] == "2024-01-01"

def test_search_documents_error(mock_settings):
    """Test document search with error."""
    with patch('app.services.paperless.get_settings', return_value=mock_settings), \
         patch('app.services.paperless.requests.get') as mock_get:
        mock_get.side_effect = requests.RequestException("Search failed")
        
        client = PaperlessClient()
        results = client.search_documents("query")
        
        assert results == []

def test_get_all_documents_basic(mock_settings):
    """Test getting all documents without pagination."""
    with patch('app.services.paperless.get_settings', return_value=mock_settings), \
         patch('app.services.paperless.requests.get') as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": [{"id": 1}], "next": None}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        client = PaperlessClient()
        results = client.get_all_documents()
        
        assert len(results) == 1
        assert results[0]["id"] == 1

def test_get_all_documents_pagination(mock_settings):
    """Test getting all documents with pagination."""
    with patch('app.services.paperless.get_settings', return_value=mock_settings), \
         patch('app.services.paperless.requests.get') as mock_get:
        # First page
        response1 = MagicMock()
        response1.json.return_value = {
            "results": [{"id": 1}],
            "next": "http://test-paperless:8000/api/documents/?page=2"
        }
        response1.raise_for_status.return_value = None
        
        # Second page
        response2 = MagicMock()
        response2.json.return_value = {"results": [{"id": 2}], "next": None}
        response2.raise_for_status.return_value = None
        
        mock_get.side_effect = [response1, response2]
        
        client = PaperlessClient()
        results = client.get_all_documents()
        
        assert len(results) == 2
        assert results[0]["id"] == 1
        assert results[1]["id"] == 2
        assert mock_get.call_count == 2

def test_get_all_documents_with_older_than(mock_settings):
    """Test getting all documents with older_than filter."""
    with patch('app.services.paperless.get_settings', return_value=mock_settings), \
         patch('app.services.paperless.requests.get') as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": [], "next": None}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        client = PaperlessClient()
        client.get_all_documents(older_than="2024-01-01")
        
        # Check that params were set correctly
        call_args = mock_get.call_args_list[0]
        # The first call uses the prepared request URL
        assert "created__date__lt" in str(call_args) or "2024-01-01" in str(call_args)

def test_get_all_documents_error_handling(mock_settings):
    """Test error handling in get_all_documents."""
    with patch('app.services.paperless.get_settings', return_value=mock_settings), \
         patch('app.services.paperless.requests.get') as mock_get:
        # First call succeeds, second fails
        response1 = MagicMock()
        response1.json.return_value = {
            "results": [{"id": 1}],
            "next": "http://test-paperless:8000/api/documents/?page=2"
        }
        response1.raise_for_status.return_value = None
        
        mock_get.side_effect = [response1, requests.RequestException("Error")]
        
        client = PaperlessClient()
        results = client.get_all_documents()
        
        # Should return partial results
        assert len(results) == 1

def test_get_all_documents_filtered_basic(mock_settings):
    """Test getting filtered documents."""
    with patch('app.services.paperless.get_settings', return_value=mock_settings), \
         patch('app.services.paperless.requests.get') as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": [{"id": 1}], "next": None}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        client = PaperlessClient()
        results = client.get_all_documents_filtered(newer_than="2024-01-01")
        
        assert len(results) == 1

def test_get_all_documents_filtered_pagination(mock_settings):
    """Test filtered documents with pagination."""
    with patch('app.services.paperless.get_settings', return_value=mock_settings), \
         patch('app.services.paperless.requests.get') as mock_get:
        response1 = MagicMock()
        response1.json.return_value = {
            "results": [{"id": 1}],
            "next": "http://test-paperless:8000/api/documents/?page=2"
        }
        response1.raise_for_status.return_value = None
        
        response2 = MagicMock()
        response2.json.return_value = {"results": [{"id": 2}], "next": None}
        response2.raise_for_status.return_value = None
        
        mock_get.side_effect = [response1, response2]
        
        client = PaperlessClient()
        results = client.get_all_documents_filtered()
        
        assert len(results) == 2

def test_get_document_original_success(mock_settings):
    """Test successful original document retrieval."""
    with patch('app.services.paperless.get_settings', return_value=mock_settings), \
         patch('app.services.paperless.requests.get') as mock_get:
        mock_response = MagicMock()
        mock_response.content = b"PDF content here"
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        client = PaperlessClient()
        content = client.get_document_original(1)
        
        assert content == b"PDF content here"
        assert "download" in mock_get.call_args[0][0]
        assert "original=true" in mock_get.call_args[0][0]

def test_get_document_original_error(mock_settings):
    """Test original document retrieval with error."""
    with patch('app.services.paperless.get_settings', return_value=mock_settings), \
         patch('app.services.paperless.requests.get') as mock_get:
        mock_get.side_effect = requests.RequestException("Download failed")
        
        client = PaperlessClient()
        content = client.get_document_original(1)
        
        assert content is None

def test_get_document_mime_type_success(mock_settings):
    """Test successful MIME type retrieval."""
    with patch('app.services.paperless.get_settings', return_value=mock_settings), \
         patch('app.services.paperless.requests.head') as mock_head:
        mock_response = MagicMock()
        mock_response.headers = {"Content-Type": "image/png; charset=utf-8"}
        mock_response.raise_for_status.return_value = None
        mock_head.return_value = mock_response
        
        client = PaperlessClient()
        mime_type = client.get_document_mime_type(1)
        
        assert mime_type == "image/png"
        mock_head.assert_called_once()

def test_get_document_mime_type_no_content_type(mock_settings):
    """Test MIME type retrieval when Content-Type header is missing."""
    with patch('app.services.paperless.get_settings', return_value=mock_settings), \
         patch('app.services.paperless.requests.head') as mock_head:
        mock_response = MagicMock()
        mock_response.headers = {}
        mock_response.raise_for_status.return_value = None
        mock_head.return_value = mock_response
        
        client = PaperlessClient()
        mime_type = client.get_document_mime_type(1)
        
        assert mime_type is None

def test_get_document_mime_type_error(mock_settings):
    """Test MIME type retrieval with error."""
    with patch('app.services.paperless.get_settings', return_value=mock_settings), \
         patch('app.services.paperless.requests.head') as mock_head:
        mock_head.side_effect = requests.RequestException("HEAD failed")
        
        client = PaperlessClient()
        mime_type = client.get_document_mime_type(1)
        
        assert mime_type is None

def test_get_document_mime_type_charset_handling(mock_settings):
    """Test that MIME type extraction handles charset correctly."""
    with patch('app.services.paperless.get_settings', return_value=mock_settings), \
         patch('app.services.paperless.requests.head') as mock_head:
        mock_response = MagicMock()
        mock_response.headers = {"Content-Type": "application/pdf; charset=binary"}
        mock_response.raise_for_status.return_value = None
        mock_head.return_value = mock_response
        
        client = PaperlessClient()
        mime_type = client.get_document_mime_type(1)
        
        assert mime_type == "application/pdf"

