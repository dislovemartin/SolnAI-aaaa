from contextlib import asynccontextmanager
import asyncio
import json
import os
from typing import Dict, List, Optional, Any, Union

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from app.config import Settings, get_settings
from app.models import (
    EntityCreate,
    RelationshipCreate,
    GraphQueryRequest,
    EntityResponse,
    RelationshipResponse,
    GraphQueryResponse,
    HealthResponse,
    BatchEntityOperation,
    BatchRelationshipOperation,
    OperationResponse,
)
from app.neo4j_client import Neo4jClient
from app.nats_client import NatsClient

# Global clients
neo4j_client: Optional[Neo4jClient] = None
nats_client: Optional[NatsClient] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    global neo4j_client, nats_client
    settings = get_settings()
    
    # Initialize Neo4j client
    logger.info(f"Connecting to Neo4j at {settings.neo4j_uri}")
    neo4j_client = Neo4jClient(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
    )
    await neo4j_client.connect()
    
    # Initialize schema if configured
    if settings.initialize_schema:
        await neo4j_client.initialize_schema()
    
    # Initialize NATS client
    logger.info(f"Connecting to NATS at {settings.nats_url}")
    nats_client = NatsClient(
        nats_url=settings.nats_url,
        user=settings.nats_user,
        password=settings.nats_password,
    )
    await nats_client.connect()
    
    # Initialize NATS streams and subscriptions
    if nats_client.js:
        try:
            # Set up subscriptions for NLP enriched data
            async def process_enriched_data(msg):
                try:
                    data = json.loads(msg.data.decode())
                    logger.info(f"Processing enriched data: {data.get('id', 'unknown')}")
                    
                    # Extract entities and relationships from enriched data
                    if entities := data.get("nlp_enrichment", {}).get("entities", []):
                        await process_entities_from_enriched_data(data, entities)
                    
                    await msg.ack()
                except Exception as e:
                    logger.error(f"Error processing enriched message: {e}")
                    await msg.nak(delay=5)
            
            # Subscribe to NLP enriched data
            await nats_client.subscribe(
                "nlp.enriched.*", 
                queue="knowledge-graph-processors",
                callback=process_enriched_data
            )
            
            logger.info("NATS subscriptions configured")
        except Exception as e:
            logger.error(f"Failed to configure NATS streams/subscriptions: {e}")
    
    # Start background processors
    asyncio.create_task(health_check_loop())
    
    logger.info("Knowledge Graph service started")
    
    yield
    
    # Cleanup
    if nats_client:
        await nats_client.close()
        logger.info("NATS connection closed")
    
    if neo4j_client:
        await neo4j_client.close()
        logger.info("Neo4j connection closed")
    
    logger.info("Knowledge Graph service shutdown")

app = FastAPI(
    title="Chimera Knowledge Graph Service",
    description="Manages the Knowledge Graph using Neo4j",
    version="0.1.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def health_check_loop():
    """Background task to check system health periodically."""
    while True:
        try:
            neo4j_healthy = neo4j_client and await neo4j_client.is_healthy()
            nats_healthy = nats_client and nats_client.is_connected()
            
            if not neo4j_healthy:
                logger.warning("Neo4j connection unhealthy")
                if neo4j_client:
                    try:
                        await neo4j_client.connect()
                    except Exception as e:
                        logger.error(f"Failed to reconnect to Neo4j: {e}")
            
            if not nats_healthy:
                logger.warning("NATS connection unhealthy")
                if nats_client:
                    try:
                        await nats_client.connect()
                    except Exception as e:
                        logger.error(f"Failed to reconnect to NATS: {e}")
                        
        except Exception as e:
            logger.error(f"Error in health check loop: {e}")
            
        await asyncio.sleep(30)  # Check every 30 seconds

async def process_entities_from_enriched_data(data: Dict[str, Any], entities: List[Dict[str, Any]]):
    """Process entities from enriched data.
    
    Args:
        data: The enriched data
        entities: List of extracted entities
    """
    if not neo4j_client:
        logger.error("Neo4j client not initialized")
        return
    
    try:
        # Extract source information
        source_id = data.get("id", "unknown")
        source_type = data.get("content_type", "unknown")
        source_title = data.get("payload", {}).get("title", "Untitled")
        
        # Create source node (e.g., Paper, NewsArticle)
        source_props = {
            "id": source_id,
            "title": source_title,
            "source": data.get("source", "unknown"),
            "timestamp": data.get("timestamp"),
        }
        
        # Determine label based on content_type
        source_label = "Document"
        if "research_paper" in source_type:
            source_label = "Paper"
        elif "news_article" in source_type:
            source_label = "NewsArticle"
        elif "repository" in source_type:
            source_label = "Repository"
            
        # Create the source node
        source_node_id = await neo4j_client.create_node(
            labels=[source_label],
            properties=source_props
        )
        
        # Process each entity
        for entity in entities:
            entity_type = entity.get("type", "UNKNOWN")
            entity_text = entity.get("text", "").strip()
            
            if not entity_text:
                continue
                
            # Create entity node if it doesn't exist
            entity_props = {
                "name": entity_text,
                "type": entity_type,
                "confidence": entity.get("confidence", 1.0),
            }
            
            entity_node_id = await neo4j_client.merge_node(
                labels=["Entity"],
                match_properties={"name": entity_text, "type": entity_type},
                additional_properties=entity_props
            )
            
            # Create relationship between source and entity
            rel_props = {
                "confidence": entity.get("confidence", 1.0),
            }
            
            await neo4j_client.create_relationship(
                start_node_id=source_node_id,
                end_node_id=entity_node_id,
                rel_type="MENTIONS",
                properties=rel_props
            )
            
        logger.info(f"Processed {len(entities)} entities for {source_id}")
        
    except Exception as e:
        logger.error(f"Error processing entities: {e}")
        raise

@app.get("/health")
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    neo4j_healthy = neo4j_client and await neo4j_client.is_healthy()
    nats_healthy = nats_client and nats_client.is_connected()
    
    return HealthResponse(
        service="knowledge-graph",
        status="healthy" if (neo4j_healthy and nats_healthy) else "degraded",
        components={
            "neo4j": "connected" if neo4j_healthy else "disconnected",
            "nats": "connected" if nats_healthy else "disconnected",
        },
        version="0.1.0"
    )

@app.post("/entities", response_model=EntityResponse)
async def create_entity(entity: EntityCreate) -> EntityResponse:
    """Create a new entity in the knowledge graph."""
    if not neo4j_client:
        raise HTTPException(500, "Neo4j client not initialized")
    
    try:
        # Create entity node
        node_id = await neo4j_client.create_node(
            labels=[entity.entity_type],
            properties=entity.properties.dict()
        )
        
        return EntityResponse(
            id=node_id,
            entity_type=entity.entity_type,
            properties=entity.properties.dict(),
            status="created"
        )
    
    except Exception as e:
        logger.error(f"Error creating entity: {e}")
        raise HTTPException(500, f"Failed to create entity: {str(e)}")

@app.post("/relationships", response_model=RelationshipResponse)
async def create_relationship(relationship: RelationshipCreate) -> RelationshipResponse:
    """Create a new relationship between entities in the knowledge graph."""
    if not neo4j_client:
        raise HTTPException(500, "Neo4j client not initialized")
    
    try:
        # Find start and end nodes
        start_node = await neo4j_client.find_node_by_properties(
            labels=relationship.start_node.entity_type.split("|"),
            properties=relationship.start_node.properties.dict()
        )
        
        end_node = await neo4j_client.find_node_by_properties(
            labels=relationship.end_node.entity_type.split("|"),
            properties=relationship.end_node.properties.dict()
        )
        
        if not start_node:
            raise HTTPException(404, "Start node not found")
            
        if not end_node:
            raise HTTPException(404, "End node not found")
        
        # Create relationship
        rel_id = await neo4j_client.create_relationship(
            start_node_id=start_node["id"],
            end_node_id=end_node["id"],
            rel_type=relationship.relationship_type,
            properties=relationship.properties.dict() if relationship.properties else {}
        )
        
        return RelationshipResponse(
            id=rel_id,
            start_node_id=start_node["id"],
            end_node_id=end_node["id"],
            relationship_type=relationship.relationship_type,
            properties=relationship.properties.dict() if relationship.properties else {},
            status="created"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating relationship: {e}")
        raise HTTPException(500, f"Failed to create relationship: {str(e)}")

@app.post("/query", response_model=GraphQueryResponse)
async def query_graph(query: GraphQueryRequest) -> GraphQueryResponse:
    """Query the knowledge graph."""
    if not neo4j_client:
        raise HTTPException(500, "Neo4j client not initialized")
    
    try:
        # Execute Cypher query
        result = await neo4j_client.execute_query(
            query=query.cypher,
            params=query.parameters if query.parameters else {}
        )
        
        return GraphQueryResponse(
            result=result,
            status="success"
        )
    
    except Exception as e:
        logger.error(f"Error executing query: {e}")
        raise HTTPException(500, f"Query execution failed: {str(e)}")

@app.post("/entities/batch", response_model=OperationResponse)
async def batch_entity_operations(operations: BatchEntityOperation) -> OperationResponse:
    """Perform batch operations on entities."""
    if not neo4j_client:
        raise HTTPException(500, "Neo4j client not initialized")
    
    try:
        successful = 0
        failed = 0
        
        # Process create operations
        for entity in operations.create or []:
            try:
                await neo4j_client.create_node(
                    labels=[entity.entity_type],
                    properties=entity.properties.dict()
                )
                successful += 1
            except Exception as e:
                logger.error(f"Error in batch create: {e}")
                failed += 1
        
        # Process update operations
        for update in operations.update or []:
            try:
                # Find nodes to update
                nodes = await neo4j_client.find_nodes_by_properties(
                    labels=update.entity_type.split("|"),
                    properties=update.match_properties.dict()
                )
                
                # Update each matching node
                for node in nodes:
                    await neo4j_client.update_node(
                        node_id=node["id"],
                        properties=update.new_properties.dict()
                    )
                    successful += 1
            except Exception as e:
                logger.error(f"Error in batch update: {e}")
                failed += 1
        
        # Process delete operations
        for delete in operations.delete or []:
            try:
                # Find nodes to delete
                nodes = await neo4j_client.find_nodes_by_properties(
                    labels=delete.entity_type.split("|"),
                    properties=delete.properties.dict()
                )
                
                # Delete each matching node
                for node in nodes:
                    await neo4j_client.delete_node(node_id=node["id"])
                    successful += 1
            except Exception as e:
                logger.error(f"Error in batch delete: {e}")
                failed += 1
        
        return OperationResponse(
            successful=successful,
            failed=failed,
            status="completed"
        )
    
    except Exception as e:
        logger.error(f"Error in batch operation: {e}")
        raise HTTPException(500, f"Batch operation failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", "8001"))
    host = os.getenv("HOST", "0.0.0.0")
    
    uvicorn.run("app.main:app", host=host, port=port, reload=True)
