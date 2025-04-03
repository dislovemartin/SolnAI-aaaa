from functools import lru_cache
from typing import Dict, Any, Optional
import os
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

class Settings(BaseModel):
    """Application settings loaded from environment variables."""
    
    # Service configuration
    service_name: str = Field(default="ml-orchestrator")
    environment: str = Field(default=os.getenv("ENVIRONMENT", "development"))
    log_level: str = Field(default=os.getenv("LOG_LEVEL", "INFO"))
    
    # API configuration
    host: str = Field(default=os.getenv("HOST", "0.0.0.0"))
    port: int = Field(default=int(os.getenv("PORT", "8000")))
    
    # NATS configuration
    nats_url: str = Field(default=os.getenv("NATS_URL", "nats://localhost:4222"))
    nats_user: Optional[str] = Field(default=os.getenv("NATS_USER"))
    nats_password: Optional[str] = Field(default=os.getenv("NATS_PASSWORD"))
    
    # Triton configuration
    triton_url: str = Field(default=os.getenv("TRITON_URL", "localhost:8000"))
    
    # Model configurations
    summarization_model: str = Field(default=os.getenv("SUMMARIZATION_MODEL", "bart_summarization"))
    entity_extraction_model: str = Field(default=os.getenv("ENTITY_EXTRACTION_MODEL", "ner_model"))
    
    # Processing parameters
    default_max_summary_length: int = Field(default=int(os.getenv("DEFAULT_MAX_SUMMARY_LENGTH", "150")))
    default_min_summary_length: int = Field(default=int(os.getenv("DEFAULT_MIN_SUMMARY_LENGTH", "50")))
    default_entity_confidence: float = Field(default=float(os.getenv("DEFAULT_ENTITY_CONFIDENCE", "0.5")))
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

@lru_cache()
def get_settings() -> Settings:
    """Create cached settings instance."""
    return Settings()
