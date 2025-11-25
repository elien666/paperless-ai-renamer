import requests
from typing import Optional, List, Dict, Any
import logging
from app.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

class PaperlessClient:
    def __init__(self):
        self.base_url = settings.PAPERLESS_API_URL.rstrip('/')
        self.headers = {
            "Authorization": f"Token {settings.PAPERLESS_API_TOKEN}",
            "Accept": "application/json; version=2"
        }

    def get_document(self, doc_id: int) -> Optional[Dict[str, Any]]:
        """Fetch a single document by ID."""
        try:
            response = requests.get(f"{self.base_url}/api/documents/{doc_id}/", headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Error fetching document {doc_id}: {e}")
            return None

    def update_document(self, doc_id: int, title: str) -> bool:
        """Update a document's title."""
        try:
            payload = {"title": title}
            response = requests.patch(f"{self.base_url}/api/documents/{doc_id}/", json=payload, headers=self.headers)
            response.raise_for_status()
            logger.info(f"Successfully updated document {doc_id} to '{title}'")
            return True
        except requests.RequestException as e:
            logger.error(f"Error updating document {doc_id}: {e}")
            return False

    def search_documents(self, query: str, newer_than: Optional[str] = None) -> List[Dict[str, Any]]:
        """Search for documents, optionally filtering by date (YYYY-MM-DD)."""
        try:
            # Paperless supports advanced query syntax.
            # We can append date filters to the query string if needed, 
            # or use specific API parameters if available.
            # For simplicity, let's append to the query if it's a simple text search.
            # Example: "Scan created:[2023-01-01 TO 2023-12-31]" or similar.
            # Actually, the /api/documents/ endpoint accepts 'created__date__gt' etc.
            
            params = {"query": query}
            if newer_than:
                params["created__date__gt"] = newer_than
                
            response = requests.get(f"{self.base_url}/api/documents/", params=params, headers=self.headers)
            response.raise_for_status()
            return response.json().get("results", [])
        except requests.RequestException as e:
            logger.error(f"Error searching documents: {e}")
            return []

    def get_all_documents(self, page_size: int = 100, older_than: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch all documents, optionally filtering by date (YYYY-MM-DD)."""
        documents = []
        params = {"page_size": page_size}
        if older_than:
            params["created__date__lt"] = older_than
            
        # Construct initial URL with params
        req = requests.Request('GET', f"{self.base_url}/api/documents/", headers=self.headers, params=params)
        prepped = req.prepare()
        next_url = prepped.url
        
        while next_url:
            try:
                response = requests.get(next_url, headers=self.headers)
                response.raise_for_status()
                data = response.json()
                documents.extend(data.get("results", []))
                next_url = data.get("next")
            except requests.RequestException as e:
                logger.error(f"Error fetching all documents: {e}")
                break
        
        return documents

    def get_all_documents_filtered(self, page_size: int = 100, newer_than: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch all documents, optionally filtering by newer_than date (YYYY-MM-DD)."""
        documents = []
        params = {"page_size": page_size}
        if newer_than:
            params["created__date__gt"] = newer_than
            
        # Construct initial URL with params
        req = requests.Request('GET', f"{self.base_url}/api/documents/", headers=self.headers, params=params)
        prepped = req.prepare()
        next_url = prepped.url
        
        while next_url:
            try:
                response = requests.get(next_url, headers=self.headers)
                response.raise_for_status()
                data = response.json()
                documents.extend(data.get("results", []))
                next_url = data.get("next")
            except requests.RequestException as e:
                logger.error(f"Error fetching documents: {e}")
                break
        
        return documents
