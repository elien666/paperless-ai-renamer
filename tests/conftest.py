import pytest
import tempfile
import os
from unittest.mock import MagicMock, Mock, patch
from fastapi.testclient import TestClient
from typing import Generator
import sys

# Mock external dependencies before importing app modules
sys.modules['chromadb'] = MagicMock()
sys.modules['chromadb.config'] = MagicMock()
# sentence-transformers removed - using Ollama for embeddings
sys.modules['apscheduler'] = MagicMock()
sys.modules['apscheduler.schedulers'] = MagicMock()
sys.modules['apscheduler.schedulers.background'] = MagicMock()

@pytest.fixture
def mock_settings():
    """Mock settings with all required fields."""
    from unittest.mock import MagicMock
    settings = MagicMock()
    settings.PAPERLESS_API_URL = "http://test-paperless:8000"
    settings.PAPERLESS_API_TOKEN = "test-token"
    settings.OLLAMA_BASE_URL = "http://test-ollama:11434"
    settings.CRON_SCHEDULE = "*/30 * * * *"
    settings.ENABLE_SCHEDULER = False
    settings.BAD_TITLE_REGEX = "^Scan.*"
    settings.DRY_RUN = False
    settings.EMBEDDING_MODEL = "chroma/all-minilm-l6-v2-f32"
    settings.CHROMA_DB_PATH = "/tmp/test-chroma"
    settings.LLM_MODEL = "llama3"
    settings.VISION_MODEL = "moondream"
    settings.LANGUAGE = "German"
    settings.PROMPT_TEMPLATE = """You are a document title generator. Your task is to create ONE concise title for the document below.

IMPORTANT: Generate the title in {language} language.

RULES:
- Generate ONLY ONE title
- Output ONLY the title text, nothing else
- Do NOT include explanations, alternatives, or multiple options
- Do NOT include the file extension
- Keep it short and descriptive
- The title MUST be in {language} language

{examples}

Document Content:
{content}

Original Filename: {filename}

Generate ONE title in {language} (one line only):"""
    return settings

@pytest.fixture
def mock_chroma_client():
    """Mock ChromaDB client and collection."""
    mock_collection = MagicMock()
    mock_collection.get.return_value = {
        'ids': ['1', '2', '3'],
        'embeddings': [[0.1] * 384, [0.2] * 384, [0.3] * 384],
        'metadatas': [
            {'title': 'Doc 1'},
            {'title': 'Doc 2'},
            {'title': 'Doc 3'}
        ],
        'documents': ['Content 1', 'Content 2', 'Content 3']
    }
    mock_collection.query.return_value = {
        'ids': [['1', '2']],
        'metadatas': [[{'title': 'Doc 1'}, {'title': 'Doc 2'}]],
        'documents': [['Content 1', 'Content 2']],
        'distances': [[0.1, 0.2]]
    }
    mock_collection.upsert = MagicMock()
    
    mock_client = MagicMock()
    mock_client.get_or_create_collection.return_value = mock_collection
    mock_client.get.return_value = mock_collection
    
    return mock_client, mock_collection

@pytest.fixture
def mock_ollama_embeddings():
    """Mock Ollama embeddings API response."""
    mock_response = MagicMock()
    mock_response.json.return_value = {"embedding": [0.1] * 384}
    mock_response.raise_for_status = MagicMock()
    return mock_response

@pytest.fixture
def mock_requests():
    """Mock requests for Ollama and Paperless API calls."""
    with patch('app.services.ai.requests') as mock_req, \
         patch('app.services.paperless.requests') as mock_paperless_req:
        yield mock_req, mock_paperless_req

@pytest.fixture
def temp_db_path():
    """Create a temporary database path for archive tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "archive.db")
        yield db_path

@pytest.fixture
def app_client(mock_settings):
    """FastAPI test client with mocked dependencies."""
    with patch('app.config.get_settings', return_value=mock_settings), \
         patch('app.services.ai.requests') as mock_requests, \
         patch('app.services.ai.chromadb.PersistentClient') as mock_chroma, \
         patch('app.services.archive.get_db_path') as mock_db_path:
        
        # Setup Ollama embeddings mock
        mock_response = MagicMock()
        mock_response.json.return_value = {"embedding": [0.1] * 384}
        mock_response.raise_for_status = MagicMock()
        mock_requests.post.return_value = mock_response
        
        mock_collection = MagicMock()
        mock_collection.get.return_value = {
            'ids': [],
            'embeddings': [],
            'metadatas': [],
            'documents': []
        }
        mock_collection.query.return_value = {
            'ids': [[]],
            'metadatas': [[]],
            'documents': [[]],
            'distances': [[]]
        }
        mock_chroma_client = MagicMock()
        mock_chroma_client.get_or_create_collection.return_value = mock_collection
        mock_chroma.return_value = mock_chroma_client
        
        # Use tempfile for archive DB
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "archive.db")
            mock_db_path.return_value = db_path
            
            # Import app after mocks are set up
            from app.main import app
            client = TestClient(app)
            yield client

@pytest.fixture
def mock_event_loop():
    """Mock event loop for async tests."""
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()

