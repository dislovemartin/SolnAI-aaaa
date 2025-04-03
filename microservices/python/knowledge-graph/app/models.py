from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, Field
from uuid import uuid4
from datetime import datetime

class EntityProperties(BaseModel):
    """Base model for entity properties."""
    class Config:
        extra = "allow"  # Allow arbitrary additional fields

class NodeReference(BaseModel):
    """Reference to a node in the graph."""
    entity_type: str
    properties: EntityProperties

class EntityCreate(BaseModel):
    """Request model for creating an entity."""
    entity_type: str = Field(..., description="Type of entity (node label)")
    properties: EntityProperties = Field(..., description="Entity properties")

class EntityUpdate(BaseModel):
    """Request model for updating an entity."""
    entity_type: str = Field(..., description="Type of entity (node label)")
    match_properties: EntityProperties = Field(..., description="Properties to match existing entity")
    new_properties: EntityProperties = Field(..., description="New properties to set")

class EntityDelete(BaseModel):
    """Request model for deleting an entity."""
    entity_type: str = Field(..., description="Type of entity (node label)")
    properties: EntityProperties = Field(..., description="Properties to match entity to delete")

class RelationshipProperties(BaseModel):
    """Base model for relationship properties."""
    class Config:
        extra = "allow"  # Allow arbitrary additional fields

class RelationshipCreate(BaseModel):
    """Request model for creating a relationship."""
    start_node: NodeReference = Field(..., description="Start node reference")
    end_node: NodeReference = Field(..., description="End node reference")
    relationship_type: str = Field(..., description="Type of relationship")
    properties: Optional[RelationshipProperties] = Field(None, description="Relationship properties")

class RelationshipUpdate(BaseModel):
    """Request model for updating a relationship."""
    start_node: NodeReference = Field(..., description="Start node reference")
    end_node: NodeReference = Field(..., description="End node reference")
    relationship_type: str = Field(..., description="Type of relationship to match")
    new_properties: RelationshipProperties = Field(..., description="New properties to set")

class RelationshipDelete(BaseModel):
    """Request model for deleting relationships."""
    start_node: Optional[NodeReference] = Field(None, description="Optional start node reference")
    end_node: Optional[NodeReference] = Field(None, description="Optional end node reference")
    relationship_type: Optional[str] = Field(None, description="Optional relationship type to match")

class BatchEntityOperation(BaseModel):
    """Batch operation for entities."""
    create: Optional[List[EntityCreate]] = Field(None, description="Entities to create")
    update: Optional[List[EntityUpdate]] = Field(None, description="Entities to update")
    delete: Optional[List[EntityDelete]] = Field(None, description="Entities to delete")

class BatchRelationshipOperation(BaseModel):
    """Batch operation for relationships."""
    create: Optional[List[RelationshipCreate]] = Field(None, description="Relationships to create")
    update: Optional[List[RelationshipUpdate]] = Field(None, description="Relationships to update")
    delete: Optional[List[RelationshipDelete]] = Field(None, description="Relationships to delete")

class GraphQueryRequest(BaseModel):
    """Request model for querying the graph."""
    cypher: str = Field(..., description="Cypher query string")
    parameters: Optional[Dict[str, Any]] = Field(None, description="Query parameters")

class EntityResponse(BaseModel):
    """Response model for entity operations."""
    id: str = Field(..., description="Internal ID of the entity")
    entity_type: str = Field(..., description="Type of entity")
    properties: Dict[str, Any] = Field(..., description="Entity properties")
    status: str = Field(..., description="Operation status")

class RelationshipResponse(BaseModel):
    """Response model for relationship operations."""
    id: str = Field(..., description="Internal ID of the relationship")
    start_node_id: str = Field(..., description="ID of the start node")
    end_node_id: str = Field(..., description="ID of the end node")
    relationship_type: str = Field(..., description="Type of relationship")
    properties: Dict[str, Any] = Field(..., description="Relationship properties")
    status: str = Field(..., description="Operation status")

class GraphQueryResponse(BaseModel):
    """Response model for graph queries."""
    result: List[Dict[str, Any]] = Field(..., description="Query result")
    status: str = Field(..., description="Query status")

class OperationResponse(BaseModel):
    """Response model for batch operations."""
    successful: int = Field(..., description="Number of successful operations")
    failed: int = Field(..., description="Number of failed operations")
    status: str = Field(..., description="Operation status")

class HealthResponse(BaseModel):
    """Health check response model."""
    service: str = Field(..., description="Service name")
    status: str = Field(..., description="Service status (healthy, degraded, unhealthy)")
    components: Dict[str, str] = Field(default_factory=dict, description="Status of individual components")
    version: str = Field(..., description="Service version")
