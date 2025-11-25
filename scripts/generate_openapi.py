import json
import sys
import os
from unittest.mock import MagicMock

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock dependencies
sys.modules['chromadb'] = MagicMock()
sys.modules['chromadb.config'] = MagicMock()
sys.modules['sentence_transformers'] = MagicMock()
sys.modules['apscheduler'] = MagicMock()
sys.modules['apscheduler.schedulers'] = MagicMock()
sys.modules['apscheduler.schedulers.background'] = MagicMock()
sys.modules['requests'] = MagicMock()

# We need real FastAPI for schema generation
try:
    from fastapi.openapi.utils import get_openapi
    from app.main import app
except ImportError:
    print("FastAPI not installed locally. Skipping OpenAPI generation.")
    sys.exit(0)

def generate_openapi():
    openapi_schema = get_openapi(
        title="Paperless AI Renamer",
        version="1.0.0",
        description="API for Paperless AI Renamer Service",
        routes=app.routes,
    )
    
    with open("openapi.json", "w") as f:
        json.dump(openapi_schema, f, indent=2)
    
    print("Generated openapi.json")

if __name__ == "__main__":
    generate_openapi()
