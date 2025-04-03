from typing import Dict, List, Optional, Union, Any
from pydantic import BaseModel, Field
from uuid import uuid4
from datetime import datetime

class TextSummarizationRequest(BaseModel):
    """Request model for text summarization."""
    request_id: Optional[str] = Field(default_factory=lambda: str(uuid4()))
    text: str = Field(..., description="The text to summarize")
    max_length: Optional[int] = Field(default=None, description="Maximum length of the summary")
    min_length: Optional[int] = Field(default=None, description="Minimum length of the summary")
    
class EntityExtractionRequest(BaseModel):
    """Request model for entity extraction."""
    request_id: Optional[str] = Field(default_factory=lambda: str(uuid4()))
    text: str = Field(..., description="The text to extract entities from")
    confidence_threshold: Optional[float] = Field(default=None, description="Minimum confidence for entity extraction")
    entity_types: Optional[List[str]] = Field(default=None, description="Types of entities to extract")

class ProcessRequest(BaseModel):
    """Generic request model for processing data."""
    request_id: Optional[str] = Field(default_factory=lambda: str(uuid4()))
    text_content: Optional[str] = Field(default=None, description="Text content to process")
    extract_entities: bool = Field(default=True, description="Whether to extract entities")
    immediate: bool = Field(default=True, description="Process immediately (sync) or queue (async)")
    parameters: Optional[Dict[str, Any]] = Field(default=None, description="Additional parameters for processing")

class Entity(BaseModel):
    """Entity extracted from text."""
    text: str = Field(..., description="The entity text")
    type: str = Field(..., description="The entity type (e.g., PERSON, ORG)")
    start: int = Field(..., description="Start position in the text")
    end: int = Field(..., description="End position in the text")
    confidence: float = Field(..., description="Confidence score for the entity")

class ProcessResponse(BaseModel):
    """Response model for processing requests."""
    request_id: str = Field(..., description="ID of the processed request")
    status: str = Field(..., description="Status of the processing (completed, queued, failed)")
    result: Dict[str, Any] = Field(default_factory=dict, description="Processing results")
    error: Optional[str] = Field(default=None, description="Error message if processing failed")
    processed_at: Optional[str] = Field(default_factory=lambda: datetime.now().isoformat(), description="Timestamp of processing")

class HealthResponse(BaseModel):
    """Health check response model."""
    service: str = Field(..., description="Service name")
    status: str = Field(..., description="Service status (healthy, degraded, unhealthy)")
    components: Dict[str, str] = Field(default_factory=dict, description="Status of individual components")
    version: str = Field(..., description="Service version")
