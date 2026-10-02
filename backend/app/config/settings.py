from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    APP_NAME: str = "AI File Intelligence Platform"
    APP_ENV: str = "development"
    DEBUG: bool = False
    SECRET_KEY: str

    # Database
    DATABASE_URL: str

    # Google Cloud / Drive
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/cloud/google/callback"
    GOOGLE_SERVICE_ACCOUNT_JSON: str = ""  # path to service account JSON file (unused for the OAuth flow)
    GOOGLE_SCOPES: list[str] = [
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        # Read/browse everything in the user's Drive
        "https://www.googleapis.com/auth/drive.readonly",
        # Create files from the app's uploads
        "https://www.googleapis.com/auth/drive.file",
    ]

    # S3-compatible object storage (Backblaze B2 free tier, AWS S3, MinIO, ...)
    S3_ACCESS_KEY_ID: str = ""
    S3_SECRET_ACCESS_KEY: str = ""
    S3_REGION: str = "us-east-1"
    S3_BUCKET_NAME: str = ""
    # Empty → real AWS S3. For Backblaze B2 use e.g. https://s3.us-west-004.backblazeb2.com
    S3_ENDPOINT_URL: str = ""

    # AI / Embeddings — Jina AI hosted embedding API (no OpenAI dependency)
    JINA_API_KEY: str = ""
    JINA_API_URL: str = "https://api.jina.ai/v1/embeddings"
    EMBEDDING_MODEL: str = "jina-embeddings-v3"
    EMBEDDING_DIMENSIONS: int = 1024
    EMBEDDING_BATCH_SIZE: int = 64

    # RAG generation — NVIDIA hosted LLM (OpenAI-compatible chat completions)
    NVIDIA_API_KEY: str = ""
    NVIDIA_MODEL: str = "nvidia/nemotron-3.5-lightning-30b-a3b"
    NVIDIA_TIMEOUT_SECONDS: int = 30

    # Local Ollama fallback LLM (optional — NVIDIA stays primary).
    # Empty OLLAMA_MODEL disables the fallback; nothing is downloaded automatically.
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = ""
    OLLAMA_TIMEOUT_SECONDS: int = 60

    # RAG context construction limits
    RAG_MAX_CONTEXT_CHUNKS: int = 8
    RAG_MAX_CONTEXT_CHARS: int = 24000

    # AI features (Phase 6)
    AI_MAX_DOCUMENTS: int = 10         # max documents per report/analysis request
    AI_CHUNKS_PER_DOCUMENT: int = 6    # chunk selection cap per document

    # Vector DB (Qdrant)
    QDRANT_URL: str = "http://localhost:6333"
    QDRANT_API_KEY: str = ""
    QDRANT_COLLECTION_NAME: str = "document_chunks"

    # Security
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    ALGORITHM: str = "HS256"

    # File upload limits
    MAX_FILE_SIZE_MB: int = 50
    ALLOWED_EXTENSIONS: list[str] = ["pdf", "docx", "txt", "csv", "png", "jpg", "jpeg", "tiff"]

    # Local cache for downloaded files (used by Phase 3 processing)
    LOCAL_STORAGE_PATH: str = "./storage"

    # Document processing (Phase 3)
    CHUNK_SIZE_TOKENS: int = 800
    CHUNK_OVERLAP_TOKENS: int = 120
    OCR_MIN_CHARS_PER_PAGE: int = 30
    OCR_MAX_PAGES: int = 50

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
