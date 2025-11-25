from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    PAPERLESS_API_URL: str = "http://paperless-webserver:8000"
    PAPERLESS_API_TOKEN: str
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    CRON_SCHEDULE: str = "*/30 * * * *"
    
    # Scheduler settings
    ENABLE_SCHEDULER: bool = False
    BAD_TITLE_REGEX: str = "^Scan.*"
    DRY_RUN: bool = False
    
    # Embedding model settings
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    CHROMA_DB_PATH: str = "/app/data/chroma"
    
    # LLM settings
    LLM_MODEL: str = "llama3"
    PROMPT_TEMPLATE: str = """You are a document title generator. Your task is to create ONE concise title for the document below.

RULES:
- Generate ONLY ONE title
- Output ONLY the title text, nothing else
- Do NOT include explanations, alternatives, or multiple options
- Do NOT include the file extension
- Keep it short and descriptive

{examples}

Document Content:
{content}

Original Filename: {filename}

Generate ONE title (one line only):"""

    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    return Settings()
