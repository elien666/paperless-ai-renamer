from pydantic_settings import BaseSettings
from functools import lru_cache
import os

class Settings(BaseSettings):
    PAPERLESS_API_URL: str = "http://paperless-webserver:8000"
    PAPERLESS_API_TOKEN: str = ""  # Optional for local dev, but required for actual functionality
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    CRON_SCHEDULE: str = "*/30 * * * *"
    
    # Scheduler settings
    ENABLE_SCHEDULER: bool = False
    BAD_TITLE_REGEX: str = "^Scan.*"
    DRY_RUN: bool = False
    
    # Embedding model settings
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    CHROMA_DB_PATH: str = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "chroma")
    
    # LLM settings
    LLM_MODEL: str = "llama3"
    VISION_MODEL: str = "moondream"
    LANGUAGE: str = "German"
    PROMPT_TEMPLATE: str = """You are a document title generator. Your task is to create ONE concise title for the document below.

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

    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    settings = Settings()
    if not settings.PAPERLESS_API_TOKEN:
        import warnings
        warnings.warn(
            "PAPERLESS_API_TOKEN is not set. The application will not be able to connect to Paperless. "
            "Set it in your environment or create a .env file with PAPERLESS_API_TOKEN=your_token",
            UserWarning
        )
    return settings
