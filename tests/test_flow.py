import unittest
from unittest.mock import patch, MagicMock
import sys

# Mock dependencies that might not be installed locally
sys.modules['chromadb'] = MagicMock()
sys.modules['chromadb.config'] = MagicMock()
sys.modules['sentence_transformers'] = MagicMock()
sys.modules['apscheduler'] = MagicMock()
sys.modules['apscheduler.schedulers'] = MagicMock()
sys.modules['apscheduler.schedulers.background'] = MagicMock()
sys.modules['requests'] = MagicMock()
sys.modules['fastapi'] = MagicMock()
sys.modules['pydantic'] = MagicMock()
sys.modules['pydantic_settings'] = MagicMock()

# We need to mock BaseSettings specifically because config.py inherits from it
mock_pydantic_settings = MagicMock()
class MockBaseSettings:
    def __init__(self, **kwargs):
        pass
    class Config:
        env_file = ".env"
mock_pydantic_settings.BaseSettings = MockBaseSettings
sys.modules['pydantic_settings'] = mock_pydantic_settings

# Mock app.config
mock_config = MagicMock()
mock_settings = MagicMock()
mock_settings.PAPERLESS_API_URL = "http://mock-paperless"
mock_settings.PAPERLESS_API_TOKEN = "mock-token"
mock_settings.OLLAMA_BASE_URL = "http://mock-ollama"
mock_settings.EMBEDDING_MODEL = "mock-model"
mock_settings.CHROMA_DB_PATH = "/tmp/mock-chroma"
mock_settings.LLM_MODEL = "mock-llama"
mock_settings.CRON_SCHEDULE = "*/30 * * * *"

mock_config.get_settings.return_value = mock_settings
sys.modules['app.config'] = mock_config

from app.services.ai import AIService
from app.services.paperless import PaperlessClient
from app.main import process_document

class TestPaperlessAIRenamer(unittest.TestCase):

    @patch('app.services.ai.requests.post')
    @patch('app.services.ai.SentenceTransformer')
    @patch('app.services.ai.chromadb.PersistentClient')
    def test_ai_service_generate_title(self, mock_chroma, mock_sentence_transformer, mock_post):
        # Mock Embedding
        mock_model = MagicMock()
        mock_embedding_output = MagicMock()
        mock_embedding_output.tolist.return_value = [0.1, 0.2, 0.3]
        mock_model.encode.return_value = mock_embedding_output
        mock_sentence_transformer.return_value = mock_model
        
        # Mock Chroma
        mock_collection = MagicMock()
        mock_collection.query.return_value = {'ids': [], 'metadatas': [], 'documents': []}
        mock_client = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_chroma.return_value = mock_client

        # Mock Ollama Response
        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "New Title"}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        service = AIService()
        title = service.generate_title("Some content", "scan.pdf")
        self.assertEqual(title, "New Title")

    @patch('app.services.paperless.requests.get')
    @patch('app.services.paperless.requests.patch')
    def test_paperless_client(self, mock_patch, mock_get):
        # Mock Get Document
        mock_get_response = MagicMock()
        mock_get_response.json.return_value = {"id": 1, "title": "scan.pdf", "content": "text"}
        mock_get_response.raise_for_status.return_value = None
        mock_get.return_value = mock_get_response

        # Mock Update Document
        mock_patch_response = MagicMock()
        mock_patch_response.raise_for_status.return_value = None
        mock_patch.return_value = mock_patch_response

        client = PaperlessClient()
        doc = client.get_document(1)
        self.assertEqual(doc['title'], "scan.pdf")
        
        success = client.update_document(1, "New Title")
        self.assertTrue(success)

    @patch('app.main.paperless_client')
    @patch('app.main.ai_service')
    def test_process_document(self, mock_ai, mock_paperless):
        # Setup Mocks
        mock_paperless.get_document.return_value = {"id": 1, "title": "scan.pdf", "content": "Invoice 123"}
        mock_ai.generate_title.return_value = "Invoice 2023-10-01"
        
        # Run
        process_document(1)
        
        # Verify
        mock_paperless.update_document.assert_called_with(1, "Invoice 2023-10-01")
        mock_ai.add_document_to_index.assert_called_with("1", "Invoice 123", "Invoice 2023-10-01")

if __name__ == '__main__':
    unittest.main()
