"""Configuration management for the code RAG system."""
from pathlib import Path
from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )
    
    # OpenAI settings
    openai_api_key: str = Field(..., description="OpenAI API key for embeddings")
    embedding_model: str = Field(
        default="text-embedding-3-small",
        description="OpenAI embedding model to use"
    )
    embedding_dimension: int = Field(
        default=1536,
        description="Dimension of embedding vectors"
    )
    
    # Git settings
    git_token: Optional[str] = Field(
        default=None,
        description="GitHub/GitLab personal access token"
    )
    
    # ChromaDB settings
    chroma_persist_directory: Path = Field(
        default=Path("./data/chroma"),
        description="Directory to persist ChromaDB data"
    )
    
    # Repository settings
    repos_config_path: Path = Field(
        default=Path("./config/repos.json"),
        description="Path to repositories configuration file"
    )
    repos_base_path: Path = Field(
        default=Path("./data/repos"),
        description="Base directory for cloned repositories"
    )
    
    # Webhook settings
    webhook_secret: Optional[str] = Field(
        default=None,
        description="Secret for validating webhook requests"
    )
    
    # Chunking settings
    max_chunk_size: int = Field(
        default=1000,
        description="Maximum size of code chunks in characters"
    )
    chunk_overlap: int = Field(
        default=200,
        description="Overlap between chunks in characters"
    )
    
    # API settings
    api_host: str = Field(default="0.0.0.0", description="API host")
    api_port: int = Field(default=8000, description="API port")
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Ensure directories exist
        self.chroma_persist_directory.mkdir(parents=True, exist_ok=True)
        self.repos_base_path.mkdir(parents=True, exist_ok=True)
        self.repos_config_path.parent.mkdir(parents=True, exist_ok=True)


# Global settings instance
settings = Settings()
