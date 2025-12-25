import chromadb
import requests
import logging
from typing import List, Dict, Any, Optional
from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

class AIService:
    def __init__(self):
        # Embedding model is now handled via Ollama API
        logger.info(f"Using Ollama embedding model: {settings.EMBEDDING_MODEL}")
        
        # Initialize ChromaDB
        logger.info(f"Initializing ChromaDB at {settings.CHROMA_DB_PATH}")
        self.chroma_client = chromadb.PersistentClient(path=settings.CHROMA_DB_PATH)
        self.collection = self.chroma_client.get_or_create_collection(name="paperless_docs")

    def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for a given text using Ollama API.
        
        Truncates text to EMBEDDING_MAX_LENGTH characters to avoid context length errors.
        Attempts to truncate at word boundaries when possible.
        """
        # Truncate text if it exceeds the maximum length
        max_length = settings.EMBEDDING_MAX_LENGTH
        if len(text) > max_length:
            # Try to truncate at a word boundary (space or newline)
            truncated_text = text[:max_length]
            # Find the last space or newline within the truncated text
            last_space = max(
                truncated_text.rfind(' '),
                truncated_text.rfind('\n'),
                truncated_text.rfind('\t')
            )
            # If we found a word boundary reasonably close to the limit, use it
            # (rfind returns -1 if not found, so we check for >= 0)
            if last_space >= 0 and last_space > max_length * 0.9:  # At least 90% of max_length
                truncated_text = truncated_text[:last_space].strip()
            else:
                truncated_text = truncated_text.strip()
            logger.warning(f"Text truncated from {len(text)} to {len(truncated_text)} characters for embedding")
        else:
            truncated_text = text
        
        try:
            payload = {
                "model": settings.EMBEDDING_MODEL,
                "prompt": truncated_text
            }
            response = requests.post(f"{settings.OLLAMA_BASE_URL}/api/embeddings", json=payload)
            response.raise_for_status()
            result = response.json()
            embedding = result.get("embedding", [])
            if not embedding:
                raise ValueError("Empty embedding returned from Ollama")
            return embedding
        except requests.RequestException as e:
            error_msg = f"Error calling Ollama for embeddings: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

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

    def find_outlier_documents(self, k_neighbors: int = 5, limit: int = 50) -> List[Dict[str, Any]]:
        """Find documents that are outliers in the vector space.
        
        Returns documents sorted by their average distance to K nearest neighbors.
        Higher distance = more isolated = likely poor title.
        """
        logger.info(f"Finding outliers with k={k_neighbors}, limit={limit}")
        
        # Get all documents from the collection, explicitly including embeddings
        all_docs = self.collection.get(include=['embeddings', 'metadatas'])
        
        if not all_docs['ids'] or len(all_docs['ids']) < k_neighbors + 1:
            logger.warning(f"Not enough documents in index ({len(all_docs['ids']) if all_docs['ids'] else 0}). Need at least {k_neighbors + 1}.")
            return []
        
        outlier_scores = []
        
        # For each document, find its K nearest neighbors and calculate average distance
        for i, doc_id in enumerate(all_docs['ids']):
            # Query for K+1 neighbors (includes the document itself)
            results = self.collection.query(
                query_embeddings=[all_docs['embeddings'][i]],
                n_results=k_neighbors + 1
            )
            
            # Calculate average distance to neighbors (excluding itself at index 0)
            if results['distances'] and len(results['distances'][0]) > 1:
                distances = results['distances'][0][1:]  # Skip first (self)
                avg_distance = sum(distances) / len(distances)
                
                outlier_scores.append({
                    "document_id": doc_id,
                    "title": all_docs['metadatas'][i].get('title', 'N/A'),
                    "outlier_score": round(avg_distance, 4),
                    "avg_distance_to_neighbors": round(avg_distance, 4)
                })
        
        # Sort by outlier score (highest first) and limit results
        outlier_scores.sort(key=lambda x: x['outlier_score'], reverse=True)
        top_outliers = outlier_scores[:limit]
        
        logger.info(f"Found {len(top_outliers)} outliers out of {len(all_docs['ids'])} documents")
        return top_outliers

    def generate_title(self, content: str, original_filename: str) -> Optional[str]:
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
                language=settings.LANGUAGE,
                examples=examples_text,
                content=content[:2000],
                filename=original_filename
            )
        except KeyError as e:
            logger.error(f"Invalid prompt template: missing key {e}")
            return None

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
            error_msg = f"Error calling Ollama: {e}"
            logger.error(error_msg)
            return None

    def generate_title_from_image(self, image_bytes: bytes, original_title: str) -> Optional[str]:
        """Generate a title from an image using a vision model."""
        import base64
        
        # Convert image bytes to base64
        image_b64 = base64.b64encode(image_bytes).decode('utf-8')
        
        # 3. Call Ollama with vision model
        try:
            logger.info(f"Using vision model: {settings.VISION_MODEL} for image title generation")
            language_instruction = f"Generate the title in {settings.LANGUAGE} language. "
            payload = {
                "model": settings.VISION_MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": f"{language_instruction}Describe what you see in this image in 5-7 words suitable as a document title. Output ONLY the title, nothing else.",
                        "images": [image_b64]
                    }
                ],
                "stream": False
            }
            response = requests.post(f"{settings.OLLAMA_BASE_URL}/api/chat", json=payload)
            response.raise_for_status()
            result = response.json()
            
            # Extract the message content
            message = result.get("message", {})
            raw_response = message.get("content", "").strip()
            
            # Take only the first non-empty line to avoid multiple titles
            new_title = raw_response.split('\n')[0].strip()
            
            logger.info(f"Generated title from image: {new_title}")
            return new_title
        except requests.RequestException as e:
            error_msg = f"Error calling Ollama vision model: {e}"
            logger.error(error_msg)
            return None
