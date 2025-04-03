from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, Field
from uuid import uuid4
from datetime import datetime

class ContentItem(BaseModel):
    """Content item for recommendations and search results."""
    content_id: str = Field(..., description="Unique identifier for the content")
    content_type: str = Field(..., description="Type of content (e.g., research_paper, news_article)")
    title: str = Field(..., description="Title of the content")
    source: str = Field(..., description="Source of the content")
    relevance_score: float = Field(..., description="Relevance score for the content (0.0-1.0)")
    timestamp: Optional[str] = Field(None, description="Timestamp when the content was created/published")
    entities: Optional[List[str]] = Field(None, description="Entities mentioned in the content")

class PersonalizedRecommendation(ContentItem):
    """Personalized content recommendation for a user."""
    entity_matches: Optional[List[str]] = Field(default_factory=list, description="Entities that match user interests")

class UserProfileUpdate(BaseModel):
    """Request model for updating a user profile."""
    user_id: Optional[str] = Field(None, description="Unique identifier for the user (generated if not provided)")
    role: Optional[str] = Field(None, description="User's role (e.g., engineer, executive, investor, learner)")
    interests: List[str] = Field(default_factory=list, description="User's interests and topics of interest")
    preferences: Dict[str, Any] = Field(default_factory=dict, description="User's content preferences")
    expertise_level: Optional[str] = Field(None, description="User's expertise level (beginner, intermediate, expert)")
    background: Optional[str] = Field(None, description="User's background or industry")
    expertise_areas: List[str] = Field(default_factory=list, description="User's areas of expertise")

class UserProfile(UserProfileUpdate):
    """Complete user profile with generated fields."""
    user_id: str = Field(..., description="Unique identifier for the user")
    created_at: str = Field(..., description="Timestamp when the profile was created")
    updated_at: str = Field(..., description="Timestamp when the profile was last updated")

class RecommendationRequest(BaseModel):
    """Request model for getting personalized recommendations."""
    user_id: str = Field(..., description="User ID to get recommendations for")
    content_types: Optional[List[str]] = Field(None, description="Types of content to recommend")
    limit: Optional[int] = Field(None, description="Maximum number of recommendations to return")

class SearchQuery(BaseModel):
    """Request model for semantic search."""
    query: str = Field(..., description="Search query text")
    content_types: Optional[List[str]] = Field(None, description="Types of content to search")
    limit: Optional[int] = Field(None, description="Maximum number of results to return")
    user_id: Optional[str] = Field(None, description="User ID for personalized search results")
    personalization_weight: Optional[float] = Field(None, description="Weight of personalization (0.0-1.0)")

class SearchResult(BaseModel):
    """Response model for search results."""
    query: str = Field(..., description="Original search query")
    items: List[ContentItem] = Field(..., description="Search result items")
    total: int = Field(..., description="Total number of results")

class ContentVectorization(BaseModel):
    """Request/response model for content vectorization."""
    content_id: Optional[str] = Field(None, description="Content ID (generated if not provided)")
    content_type: str = Field(..., description="Type of content")
    title: str = Field(..., description="Title of the content")
    text: str = Field(..., description="Text to vectorize")
    source: Optional[str] = Field(None, description="Source of the content")
    entities: Optional[List[str]] = Field(None, description="Entities in the content")
    processed_at: Optional[str] = Field(None, description="Timestamp when the content was processed")

class EntityBatch(BaseModel):
    """Batch of entities."""
    entities: List[str] = Field(..., description="List of entities")

class BatchOperation(BaseModel):
    """Base model for batch operations."""
    ids: List[str] = Field(..., description="List of IDs to operate on")

class HealthResponse(BaseModel):
    """Health check response model."""
    service: str = Field(..., description="Service name")
    status: str = Field(..., description="Service status (healthy, degraded, unhealthy)")
    components: Dict[str, str] = Field(default_factory=dict, description="Status of individual components")
    version: str = Field(..., description="Service version")
