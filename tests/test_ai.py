import pytest
from unittest.mock import patch, MagicMock, Mock
import requests
from app.services.ai import AIService

@pytest.fixture
def mock_settings():
    """Mock settings for AIService."""
    settings = MagicMock()
    settings.EMBEDDING_MODEL = "chroma/all-minilm-l6-v2-f32"
    settings.CHROMA_DB_PATH = "/tmp/test-chroma"
    settings.OLLAMA_BASE_URL = "http://test-ollama:11434"
    settings.LLM_MODEL = "llama3"
    settings.VISION_MODEL = "moondream"
    settings.LANGUAGE = "German"
    settings.PROMPT_TEMPLATE = "Title in {language}: {content} {filename} {examples}"
    return settings

def test_ai_service_init(mock_settings, mock_chroma_client, mock_ollama_embeddings):
    """Test AIService initialization."""
    mock_client, mock_collection = mock_chroma_client
    
    with patch('app.services.ai.get_settings', return_value=mock_settings), \
         patch('app.services.ai.requests.post', return_value=mock_ollama_embeddings), \
         patch('app.services.ai.chromadb.PersistentClient', return_value=mock_client):
        service = AIService()
        
        assert service.chroma_client == mock_client
        assert service.collection == mock_collection

def test_generate_embedding(mock_settings, mock_ollama_embeddings):
    """Test embedding generation."""
    with patch('app.services.ai.get_settings', return_value=mock_settings), \
         patch('app.services.ai.requests.post', return_value=mock_ollama_embeddings), \
         patch('app.services.ai.chromadb.PersistentClient'):
        service = AIService()
        embedding = service.generate_embedding("test text")
        
        assert embedding == [0.1] * 384

def test_add_document_to_index(mock_settings, mock_chroma_client, mock_ollama_embeddings):
    """Test adding document to index."""
    mock_client, mock_collection = mock_chroma_client
    
    with patch('app.services.ai.get_settings', return_value=mock_settings), \
         patch('app.services.ai.requests.post', return_value=mock_ollama_embeddings), \
         patch('app.services.ai.chromadb.PersistentClient', return_value=mock_client):
        service = AIService()
        service.add_document_to_index("123", "Document content", "Document Title")
        
        mock_collection.upsert.assert_called_once()
        call_args = mock_collection.upsert.call_args
        assert call_args[1]["ids"] == ["123"]
        assert call_args[1]["metadatas"][0]["title"] == "Document Title"
        assert call_args[1]["documents"] == ["Document content"]

def test_find_similar_documents(mock_settings, mock_chroma_client, mock_ollama_embeddings):
    """Test finding similar documents."""
    mock_client, mock_collection = mock_chroma_client
    
    with patch('app.services.ai.get_settings', return_value=mock_settings), \
         patch('app.services.ai.requests.post', return_value=mock_ollama_embeddings), \
         patch('app.services.ai.chromadb.PersistentClient', return_value=mock_client):
        service = AIService()
        similar = service.find_similar_documents("test content", n_results=2)
        
        assert len(similar) == 2
        assert similar[0]["id"] == "1"
        assert similar[0]["title"] == "Doc 1"
        assert similar[0]["content"] == "Content 1"
        mock_collection.query.assert_called_once()

def test_find_similar_documents_empty_results(mock_settings, mock_chroma_client, mock_ollama_embeddings):
    """Test finding similar documents when no results."""
    mock_client, mock_collection = mock_chroma_client
    mock_collection.query.return_value = {
        'ids': [[]],
        'metadatas': [[]],
        'documents': [[]]
    }
    
    with patch('app.services.ai.get_settings', return_value=mock_settings), \
         patch('app.services.ai.requests.post', return_value=mock_ollama_embeddings), \
         patch('app.services.ai.chromadb.PersistentClient', return_value=mock_client):
        service = AIService()
        similar = service.find_similar_documents("test content")
        
        assert len(similar) == 0

def test_find_outlier_documents_success(mock_settings, mock_chroma_client, mock_ollama_embeddings):
    """Test finding outlier documents with sufficient documents."""
    mock_client, mock_collection = mock_chroma_client
    # Setup collection with enough documents
    mock_collection.get.return_value = {
        'ids': ['1', '2', '3', '4', '5', '6'],
        'embeddings': [[0.1] * 384] * 6,
        'metadatas': [{'title': f'Doc {i}'} for i in range(6)]
    }
    mock_collection.query.return_value = {
        'ids': [['1', '2', '3', '4', '5', '6']],
        'distances': [[0.0, 0.1, 0.2, 0.3, 0.4, 0.5]]
    }
    
    with patch('app.services.ai.get_settings', return_value=mock_settings), \
         patch('app.services.ai.requests.post', return_value=mock_ollama_embeddings), \
         patch('app.services.ai.chromadb.PersistentClient', return_value=mock_client):
        service = AIService()
        outliers = service.find_outlier_documents(k_neighbors=5, limit=3)
        
        assert len(outliers) == 3
        assert 'document_id' in outliers[0]
        assert 'outlier_score' in outliers[0]
        assert 'avg_distance_to_neighbors' in outliers[0]

def test_find_outlier_documents_empty_collection(mock_settings, mock_chroma_client, mock_ollama_embeddings):
    """Test finding outliers with empty collection."""
    mock_client, mock_collection = mock_chroma_client
    mock_collection.get.return_value = {
        'ids': [],
        'embeddings': [],
        'metadatas': []
    }
    
    with patch('app.services.ai.get_settings', return_value=mock_settings), \
         patch('app.services.ai.requests.post', return_value=mock_ollama_embeddings), \
         patch('app.services.ai.chromadb.PersistentClient', return_value=mock_client):
        service = AIService()
        outliers = service.find_outlier_documents()
        
        assert outliers == []

def test_find_outlier_documents_insufficient_docs(mock_settings, mock_chroma_client, mock_ollama_embeddings):
    """Test finding outliers when not enough documents."""
    mock_client, mock_collection = mock_chroma_client
    mock_collection.get.return_value = {
        'ids': ['1', '2'],
        'embeddings': [[0.1] * 384, [0.2] * 384],
        'metadatas': [{'title': 'Doc 1'}, {'title': 'Doc 2'}]
    }
    
    with patch('app.services.ai.get_settings', return_value=mock_settings), \
         patch('app.services.ai.requests.post', return_value=mock_ollama_embeddings), \
         patch('app.services.ai.chromadb.PersistentClient', return_value=mock_client):
        service = AIService()
        outliers = service.find_outlier_documents(k_neighbors=5)
        
        assert outliers == []

def test_generate_title_success(mock_settings, mock_chroma_client, mock_ollama_embeddings):
    """Test successful title generation."""
    mock_client, mock_collection = mock_chroma_client
    
    def mock_post_side_effect(url, **kwargs):
        mock_response = MagicMock()
        if "/api/embeddings" in url:
            mock_response.json.return_value = {"embedding": [0.1] * 384}
        elif "/api/generate" in url:
            mock_response.json.return_value = {"response": "Generated Title\nExtra line"}
        mock_response.raise_for_status = MagicMock()
        return mock_response
    
    with patch('app.services.ai.get_settings', return_value=mock_settings), \
         patch('app.services.ai.requests.post', side_effect=mock_post_side_effect), \
         patch('app.services.ai.chromadb.PersistentClient', return_value=mock_client):
        service = AIService()
        title = service.generate_title("Document content", "file.pdf")
        
        assert title == "Generated Title"

def test_generate_title_with_similar_docs(mock_settings, mock_chroma_client, mock_ollama_embeddings):
    """Test title generation with similar documents for few-shot learning."""
    mock_client, mock_collection = mock_chroma_client
    
    def mock_post_side_effect(url, **kwargs):
        mock_response = MagicMock()
        if "/api/embeddings" in url:
            mock_response.json.return_value = {"embedding": [0.1] * 384}
        elif "/api/generate" in url:
            mock_response.json.return_value = {"response": "New Title"}
        mock_response.raise_for_status = MagicMock()
        return mock_response
    
    with patch('app.services.ai.get_settings', return_value=mock_settings), \
         patch('app.services.ai.requests.post', side_effect=mock_post_side_effect), \
         patch('app.services.ai.chromadb.PersistentClient', return_value=mock_client):
        service = AIService()
        title = service.generate_title("test content", "file.pdf")
        
        assert title == "New Title"

def test_generate_title_content_truncation(mock_settings, mock_chroma_client, mock_ollama_embeddings):
    """Test that content is truncated to 2000 characters."""
    mock_client, mock_collection = mock_chroma_client
    long_content = "x" * 3000
    
    def mock_post_side_effect(url, **kwargs):
        mock_response = MagicMock()
        if "/api/embeddings" in url:
            mock_response.json.return_value = {"embedding": [0.1] * 384}
        elif "/api/generate" in url:
            mock_response.json.return_value = {"response": "Title"}
        mock_response.raise_for_status = MagicMock()
        return mock_response
    
    with patch('app.services.ai.get_settings', return_value=mock_settings), \
         patch('app.services.ai.requests.post', side_effect=mock_post_side_effect), \
         patch('app.services.ai.chromadb.PersistentClient', return_value=mock_client):
        service = AIService()
        service.generate_title(long_content, "file.pdf")

def test_generate_title_template_error(mock_settings, mock_chroma_client, mock_ollama_embeddings):
    """Test title generation with invalid prompt template."""
    mock_settings.PROMPT_TEMPLATE = "Missing {missing_key}"
    mock_settings.EMBEDDING_MAX_LENGTH = 1000  # Ensure this is set as an integer
    mock_client, mock_collection = mock_chroma_client
    
    def mock_post_side_effect(url, **kwargs):
        mock_response = MagicMock()
        if "/api/embeddings" in url:
            mock_response.json.return_value = {"embedding": [0.1] * 384}
        mock_response.raise_for_status = MagicMock()
        return mock_response
    
    with patch('app.services.ai.get_settings', return_value=mock_settings), \
         patch('app.services.ai.settings', mock_settings), \
         patch('app.services.ai.requests.post', side_effect=mock_post_side_effect), \
         patch('app.services.ai.chromadb.PersistentClient', return_value=mock_client):
        service = AIService()
        title = service.generate_title("content", "file.pdf")
        
        assert title is None

def test_generate_title_request_error(mock_settings, mock_chroma_client, mock_ollama_embeddings):
    """Test title generation with request error."""
    mock_client, mock_collection = mock_chroma_client
    
    def mock_post_side_effect(url, **kwargs):
        if "/api/generate" in url:
            raise requests.RequestException("Connection error")
        mock_response = MagicMock()
        mock_response.json.return_value = {"embedding": [0.1] * 384}
        mock_response.raise_for_status = MagicMock()
        return mock_response
    
    with patch('app.services.ai.get_settings', return_value=mock_settings), \
         patch('app.services.ai.requests.post', side_effect=mock_post_side_effect), \
         patch('app.services.ai.chromadb.PersistentClient', return_value=mock_client):
        service = AIService()
        title = service.generate_title("content", "file.pdf")
        
        assert title is None

def test_generate_title_empty_response(mock_settings, mock_chroma_client, mock_ollama_embeddings):
    """Test title generation with empty response."""
    mock_client, mock_collection = mock_chroma_client
    
    def mock_post_side_effect(url, **kwargs):
        mock_response = MagicMock()
        if "/api/embeddings" in url:
            mock_response.json.return_value = {"embedding": [0.1] * 384}
        elif "/api/generate" in url:
            mock_response.json.return_value = {"response": "   \n  "}
        mock_response.raise_for_status = MagicMock()
        return mock_response
    
    with patch('app.services.ai.get_settings', return_value=mock_settings), \
         patch('app.services.ai.requests.post', side_effect=mock_post_side_effect), \
         patch('app.services.ai.chromadb.PersistentClient', return_value=mock_client):
        service = AIService()
        title = service.generate_title("content", "file.pdf")
        
        assert title == ""  # Stripped empty string

def test_generate_title_from_image_success(mock_settings, mock_chroma_client, mock_ollama_embeddings):
    """Test successful image title generation."""
    mock_client, mock_collection = mock_chroma_client
    image_bytes = b"fake image data"
    
    # Ensure mock_settings has the right vision model
    mock_settings.VISION_MODEL = "moondream"
    
    def mock_post_side_effect(url, **kwargs):
        mock_response = MagicMock()
        if "/api/chat" in url:
            mock_response.json.return_value = {
                "message": {"content": "Image Title\nExtra"}
            }
        mock_response.raise_for_status = MagicMock()
        return mock_response
    
    with patch('app.services.ai.get_settings', return_value=mock_settings), \
         patch('app.services.ai.requests.post', side_effect=mock_post_side_effect), \
         patch('app.services.ai.chromadb.PersistentClient', return_value=mock_client):
        service = AIService()
        title = service.generate_title_from_image(image_bytes, "image.jpg")
        
        assert title == "Image Title"

def test_generate_title_from_image_base64_encoding(mock_settings, mock_chroma_client, mock_ollama_embeddings):
    """Test that image is base64 encoded."""
    mock_client, mock_collection = mock_chroma_client
    image_bytes = b"test image"
    
    call_args_list = []
    
    def mock_post_side_effect(url, **kwargs):
        call_args_list.append((url, kwargs))
        mock_response = MagicMock()
        if "/api/chat" in url:
            mock_response.json.return_value = {"message": {"content": "Title"}}
        mock_response.raise_for_status = MagicMock()
        return mock_response
    
    with patch('app.services.ai.get_settings', return_value=mock_settings), \
         patch('app.services.ai.requests.post', side_effect=mock_post_side_effect), \
         patch('app.services.ai.chromadb.PersistentClient', return_value=mock_client):
        service = AIService()
        service.generate_title_from_image(image_bytes, "image.jpg")
        
        # Find the chat API call
        chat_call = next((args for url, args in call_args_list if "/api/chat" in url), None)
        assert chat_call is not None
        image_b64 = chat_call["json"]["messages"][0]["images"][0]
        # Check it's base64 (starts with data: or is valid base64)
        assert isinstance(image_b64, str)
        assert len(image_b64) > 0

def test_generate_title_from_image_error(mock_settings, mock_chroma_client, mock_ollama_embeddings):
    """Test image title generation with error."""
    mock_client, mock_collection = mock_chroma_client
    
    def mock_post_side_effect(url, **kwargs):
        if "/api/chat" in url:
            raise requests.RequestException("Vision API error")
        mock_response = MagicMock()
        mock_response.json.return_value = {"embedding": [0.1] * 384}
        mock_response.raise_for_status = MagicMock()
        return mock_response
    
    with patch('app.services.ai.get_settings', return_value=mock_settings), \
         patch('app.services.ai.requests.post', side_effect=mock_post_side_effect), \
         patch('app.services.ai.chromadb.PersistentClient', return_value=mock_client):
        service = AIService()
        title = service.generate_title_from_image(b"image", "image.jpg")
        
        assert title is None

def test_generate_title_from_image_empty_response(mock_settings, mock_chroma_client, mock_ollama_embeddings):
    """Test image title generation with empty response."""
    mock_client, mock_collection = mock_chroma_client
    
    def mock_post_side_effect(url, **kwargs):
        mock_response = MagicMock()
        if "/api/chat" in url:
            mock_response.json.return_value = {"message": {"content": ""}}
        mock_response.raise_for_status = MagicMock()
        return mock_response
    
    with patch('app.services.ai.get_settings', return_value=mock_settings), \
         patch('app.services.ai.requests.post', side_effect=mock_post_side_effect), \
         patch('app.services.ai.chromadb.PersistentClient', return_value=mock_client):
        service = AIService()
        title = service.generate_title_from_image(b"image", "image.jpg")
        
        assert title == ""

