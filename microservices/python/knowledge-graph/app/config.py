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
    service_name: str = Field(default="knowledge-graph")
    environment: str = Field(default=os.getenv("ENVIRONMENT", "development"))
    log_level: str = Field(default=os.getenv("LOG_LEVEL", "INFO"))
    
    # API configuration
    host: str = Field(default=os.getenv("HOST", "0.0.0.0"))
    port: int = Field(default=int(os.getenv("PORT", "8001")))
    
    # Neo4j configuration
    neo4j_uri: str = Field(default=os.getenv("NEO4J_URI", "neo4j://localhost:7687"))
    neo4j_user: str = Field(default=os.getenv("NEO4J_USER", "neo4j"))
    neo4j_password: str = Field(default=os.getenv("NEO4J_PASSWORD", "password"))
    initialize_schema: bool = Field(default=os.getenv("INITIALIZE_SCHEMA", "true").lower() == "true")
    
    # NATS configuration
    nats_url: str = Field(default=os.getenv("NATS_URL", "nats://localhost:4222"))
    nats_user: Optional[str] = Field(default=os.getenv("NATS_USER"))
    nats_password: Optional[str] = Field(default=os.getenv("NATS_PASSWORD"))
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

@lru_cache()
def get_settings() -> Settings:
    """Create cached settings instance."""
    return Settings()
