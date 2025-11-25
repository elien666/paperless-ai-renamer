import chromadb
from chromadb.config import Settings as ChromaSettings
from sentence_transformers import SentenceTransformer
import requests
import logging
from typing import List, Dict, Any, Optional
from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

class AIService:
    def __init__(self):
        # Initialize Embedding Model
        logger.info(f"Loading embedding model: {settings.EMBEDDING_MODEL}")
        self.embedding_model = SentenceTransformer(settings.EMBEDDING_MODEL)
        
        # Initialize ChromaDB
        logger.info(f"Initializing ChromaDB at {settings.CHROMA_DB_PATH}")
        self.chroma_client = chromadb.PersistentClient(path=settings.CHROMA_DB_PATH)
        self.collection = self.chroma_client.get_or_create_collection(name="paperless_docs")

    def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for a given text."""
        return self.embedding_model.encode(text).tolist()

    def add_document_to_index(self, doc_id: str, content: str, title: str):
        """Add a document to the vector index."""
        embedding = self.generate_embedding(content)
        self.collection.upsert(
            ids=[str(doc_id)],
            embeddings=[embedding],
            documents=[content],
            metadatas=[{"title": title}]
        )
        logger.info(f"Indexed document {doc_id}")

    def find_similar_documents(self, content: str, n_results: int = 3) -> List[Dict[str, Any]]:
        """Find similar documents to use as context."""
        embedding = self.generate_embedding(content)
        results = self.collection.query(
            query_embeddings=[embedding],
            n_results=n_results
        )
        
        similar_docs = []
        if results['ids'] and results['metadatas']:
            for i in range(len(results['ids'][0])):
                similar_docs.append({
                    "id": results['ids'][0][i],
                    "title": results['metadatas'][0][i]['title'],
                    "content": results['documents'][0][i]
                })
        return similar_docs

    def generate_title(self, content: str, original_filename: str) -> str:
        """Generate a new title using Ollama and RAG."""
        
        # 1. Find similar documents for few-shot learning
        similar_docs = self.find_similar_documents(content)
        
        # 2. Construct Prompt
        examples_text = ""
        if similar_docs:
            examples_text = "Here are some examples of how similar documents were named:\n"
            for doc in similar_docs:
                examples_text += f"- Content snippet: {doc['content'][:200]}... -> Title: {doc['title']}\n"
        
        try:
            prompt = settings.PROMPT_TEMPLATE.format(
                examples=examples_text,
                content=content[:2000],
                filename=original_filename
            )
        except KeyError as e:
            logger.error(f"Invalid prompt template: missing key {e}")
            return original_filename

        # 3. Call Ollama
        try:
            payload = {
                "model": settings.LLM_MODEL,
                "prompt": prompt,
                "stream": False
            }
            response = requests.post(f"{settings.OLLAMA_BASE_URL}/api/generate", json=payload)
            response.raise_for_status()
            result = response.json()
            raw_response = result.get("response", "").strip()
            
            # Take only the first non-empty line to avoid multiple titles
            new_title = raw_response.split('\n')[0].strip()
            
            logger.info(f"Generated title: {new_title}")
            return new_title
        except requests.RequestException as e:
            logger.error(f"Error calling Ollama: {e}")
            return original_filename # Fallback
