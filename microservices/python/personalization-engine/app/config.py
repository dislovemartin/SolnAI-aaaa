from functools import lru_cache
from typing import Dict, Any, Optional, List
import os
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

class Settings(BaseModel):
    """Application settings loaded from environment variables."""
    
    # Service configuration
    service_name: str = Field(default="personalization-engine")
    environment: str = Field(default=os.getenv("ENVIRONMENT", "development"))
    log_level: str = Field(default=os.getenv("LOG_LEVEL", "INFO"))
    
    # API configuration
    host: str = Field(default=os.getenv("HOST", "0.0.0.0"))
    port: int = Field(default=int(os.getenv("PORT", "8002")))
    
    # Vector embedding configuration
    embedding_model: str = Field(default=os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"))
    embedding_dimension: int = Field(default=int(os.getenv("EMBEDDING_DIMENSION", "384")))
    
    # Redis Vector DB configuration
    redis_url: str = Field(default=os.getenv("REDIS_URL", "redis://localhost:6379"))
    redis_index_name: str = Field(default=os.getenv("REDIS_INDEX_NAME", "chimera-vectors"))
    redis_user_index_name: str = Field(default=os.getenv("REDIS_USER_INDEX_NAME", "chimera-users"))
    
    # NATS configuration
    nats_url: str = Field(default=os.getenv("NATS_URL", "nats://localhost:4222"))
    nats_user: Optional[str] = Field(default=os.getenv("NATS_USER"))
    nats_password: Optional[str] = Field(default=os.getenv("NATS_PASSWORD"))
    
    # Content personalization settings
    default_content_types: List[str] = Field(
        default=["research_paper", "news_article", "repository", "tutorial"]
    )
    default_recommendation_limit: int = Field(default=10)
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

@lru_cache()
def get_settings() -> Settings:
    """Create cached settings instance."""
    return Settings()
