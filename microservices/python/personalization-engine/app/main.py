from contextlib import asynccontextmanager
import asyncio
import json
import os
from typing import Dict, List, Optional, Any, Union
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
import numpy as np

from app.config import Settings, get_settings
from app.models import (
    ContentItem,
    UserProfile,
    PersonalizedRecommendation,
    RecommendationRequest,
    UserProfileUpdate,
    SearchQuery,
    SearchResult,
    HealthResponse,
    ContentVectorization,
    BatchOperation
)
from app.vector_store import VectorStore
from app.nats_client import NatsClient

# Global clients
vector_store: Optional[VectorStore] = None
nats_client: Optional[NatsClient] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    global vector_store, nats_client
    settings = get_settings()
    
    # Initialize Vector Store
    logger.info(f"Initializing Vector Store")
    vector_store = VectorStore(
        model_name=settings.embedding_model,
        dimension=settings.embedding_dimension,
        redis_url=settings.redis_url,
    )
    await vector_store.initialize()
    
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
                    logger.info(f"Processing enriched data for vectorization: {data.get('id', 'unknown')}")
                    
                    # Extract content information for vectorization
                    await process_content_for_vectorization(data)
                    
                    await msg.ack()
                except Exception as e:
                    logger.error(f"Error processing enriched message: {e}")
                    await msg.nak(delay=5)
            
            # Subscribe to NLP enriched data
            await nats_client.subscribe(
                "nlp.enriched.*", 
                queue="personalization-engine-processors",
                callback=process_enriched_data
            )
            
            logger.info("NATS subscriptions configured")
        except Exception as e:
            logger.error(f"Failed to configure NATS streams/subscriptions: {e}")
    
    # Start background processors
    asyncio.create_task(health_check_loop())
    
    logger.info("Personalization Engine service started")
    
    yield
    
    # Cleanup
    if nats_client:
        await nats_client.close()
        logger.info("NATS connection closed")
    
    if vector_store:
        await vector_store.close()
        logger.info("Vector Store closed")
    
    logger.info("Personalization Engine service shutdown")

app = FastAPI(
    title="Chimera Personalization Engine",
    description="Manages user profiles and content recommendations using vector embeddings",
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
            vector_store_healthy = vector_store and await vector_store.is_healthy()
            nats_healthy = nats_client and nats_client.is_connected()
            
            if not vector_store_healthy:
                logger.warning("Vector Store unhealthy")
                if vector_store:
                    try:
                        await vector_store.initialize()
                    except Exception as e:
                        logger.error(f"Failed to reinitialize Vector Store: {e}")
            
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

async def process_content_for_vectorization(data: Dict[str, Any]):
    """Process content from enriched data for vectorization.
    
    Args:
        data: The enriched data containing content to vectorize
    """
    if not vector_store:
        logger.error("Vector Store not initialized")
        return
    
    try:
        # Extract content information
        content_id = data.get("id", str(uuid4()))
        content_type = data.get("content_type", "unknown")
        
        # Prepare text for vectorization
        texts = []
        
        # Add title if available
        if title := data.get("payload", {}).get("title"):
            texts.append(title)
        
        # Add summary if available
        if summary := data.get("nlp_enrichment", {}).get("summary"):
            texts.append(summary)
        
        # Add full text if available (limited to reduce embedding size)
        if full_text := data.get("payload", {}).get("text", "")[:2000]:
            texts.append(full_text)
        
        # Combine texts with proper separation
        text_to_vectorize = " ".join(texts)
        
        if not text_to_vectorize:
            logger.warning(f"No text available for vectorization for content {content_id}")
            return
        
        # Extract metadata
        metadata = {
            "id": content_id,
            "content_type": content_type,
            "source": data.get("source", "unknown"),
            "timestamp": data.get("timestamp"),
            "title": data.get("payload", {}).get("title", "Untitled"),
            "entities": [e.get("text") for e in data.get("nlp_enrichment", {}).get("entities", [])]
        }
        
        # Generate embedding and store in vector database
        await vector_store.add_item(
            item_id=content_id,
            text=text_to_vectorize,
            metadata=metadata
        )
        
        logger.info(f"Vectorized content {content_id} ({content_type})")
        
        # Publish to content.vectorized subject
        if nats_client:
            await nats_client.publish(
                f"content.vectorized.{content_type}",
                json.dumps({
                    "id": content_id,
                    "content_type": content_type,
                    "vectorized_at": str(np.datetime64('now')),
                })
            )
        
    except Exception as e:
        logger.error(f"Error vectorizing content: {e}")
        raise

@app.get("/health")
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    vector_store_healthy = vector_store and await vector_store.is_healthy()
    nats_healthy = nats_client and nats_client.is_connected()
    
    return HealthResponse(
        service="personalization-engine",
        status="healthy" if (vector_store_healthy and nats_healthy) else "degraded",
        components={
            "vector_store": "connected" if vector_store_healthy else "disconnected",
            "nats": "connected" if nats_healthy else "disconnected",
        },
        version="0.1.0"
    )

@app.post("/users", response_model=UserProfile)
async def create_user_profile(
    profile: UserProfileUpdate,
    settings: Settings = Depends(get_settings)
) -> UserProfile:
    """Create a new user profile."""
    if not vector_store:
        raise HTTPException(500, "Vector Store not initialized")
    
    try:
        # Generate a new user ID if not provided
        user_id = profile.user_id or str(uuid4())
        
        # Generate embedding for interests and preferences
        interests_text = " ".join([
            *profile.interests,
            *profile.expertise_areas,
            profile.role or "",
            profile.background or "",
        ])
        
        # Store user profile
        await vector_store.add_user(
            user_id=user_id,
            interests=interests_text,
            preferences=profile.preferences,
            role=profile.role,
            metadata={
                "expertise_level": profile.expertise_level,
                "background": profile.background,
                "expertise_areas": profile.expertise_areas,
            }
        )
        
        # Return the created profile
        return UserProfile(
            user_id=user_id,
            interests=profile.interests,
            preferences=profile.preferences,
            role=profile.role,
            expertise_level=profile.expertise_level,
            background=profile.background,
            expertise_areas=profile.expertise_areas,
            created_at=str(np.datetime64('now')),
            updated_at=str(np.datetime64('now')),
        )
    
    except Exception as e:
        logger.error(f"Error creating user profile: {e}")
        raise HTTPException(500, f"Failed to create user profile: {str(e)}")

@app.put("/users/{user_id}", response_model=UserProfile)
async def update_user_profile(
    user_id: str,
    profile: UserProfileUpdate,
    settings: Settings = Depends(get_settings)
) -> UserProfile:
    """Update an existing user profile."""
    if not vector_store:
        raise HTTPException(500, "Vector Store not initialized")
    
    try:
        # Check if user exists
        user = await vector_store.get_user(user_id)
        if not user:
            raise HTTPException(404, f"User {user_id} not found")
        
        # Generate embedding for interests and preferences
        interests_text = " ".join([
            *profile.interests,
            *profile.expertise_areas,
            profile.role or "",
            profile.background or "",
        ])
        
        # Update user profile
        await vector_store.update_user(
            user_id=user_id,
            interests=interests_text,
            preferences=profile.preferences,
            role=profile.role,
            metadata={
                "expertise_level": profile.expertise_level,
                "background": profile.background,
                "expertise_areas": profile.expertise_areas,
            }
        )
        
        # Return the updated profile
        return UserProfile(
            user_id=user_id,
            interests=profile.interests,
            preferences=profile.preferences,
            role=profile.role,
            expertise_level=profile.expertise_level,
            background=profile.background,
            expertise_areas=profile.expertise_areas,
            created_at=user.get("created_at", str(np.datetime64('now'))),
            updated_at=str(np.datetime64('now')),
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user profile: {e}")
        raise HTTPException(500, f"Failed to update user profile: {str(e)}")

@app.get("/users/{user_id}", response_model=UserProfile)
async def get_user_profile(
    user_id: str,
    settings: Settings = Depends(get_settings)
) -> UserProfile:
    """Get a user profile by ID."""
    if not vector_store:
        raise HTTPException(500, "Vector Store not initialized")
    
    try:
        # Get user profile
        user = await vector_store.get_user(user_id)
        if not user:
            raise HTTPException(404, f"User {user_id} not found")
        
        # Extract metadata
        metadata = user.get("metadata", {})
        
        # Return the profile
        return UserProfile(
            user_id=user_id,
            interests=user.get("interests", []),
            preferences=user.get("preferences", {}),
            role=user.get("role"),
            expertise_level=metadata.get("expertise_level"),
            background=metadata.get("background"),
            expertise_areas=metadata.get("expertise_areas", []),
            created_at=user.get("created_at", str(np.datetime64('now'))),
            updated_at=user.get("updated_at", str(np.datetime64('now'))),
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving user profile: {e}")
        raise HTTPException(500, f"Failed to retrieve user profile: {str(e)}")

@app.post("/recommendations", response_model=List[PersonalizedRecommendation])
async def get_recommendations(
    request: RecommendationRequest,
    settings: Settings = Depends(get_settings)
) -> List[PersonalizedRecommendation]:
    """Get personalized content recommendations for a user."""
    if not vector_store:
        raise HTTPException(500, "Vector Store not initialized")
    
    try:
        # Get user profile
        user = await vector_store.get_user(request.user_id)
        if not user:
            raise HTTPException(404, f"User {request.user_id} not found")
        
        # Set query parameters
        content_types = request.content_types or ["research_paper", "news_article", "repository"]
        limit = min(request.limit or 10, 50)  # Cap at 50 items
        
        # Find similar content based on user embedding
        results = await vector_store.find_similar_to_user(
            user_id=request.user_id,
            content_types=content_types,
            limit=limit
        )
        
        # Convert to response model
        recommendations = []
        for item in results:
            metadata = item.get("metadata", {})
            score = item.get("score", 0.0)
            
            recommendations.append(PersonalizedRecommendation(
                content_id=item.get("id"),
                content_type=metadata.get("content_type", "unknown"),
                title=metadata.get("title", "Untitled"),
                source=metadata.get("source", "unknown"),
                relevance_score=float(score),
                timestamp=metadata.get("timestamp"),
                entity_matches=[e for e in metadata.get("entities", []) if e in user.get("interests", [])]
            ))
        
        return recommendations
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating recommendations: {e}")
        raise HTTPException(500, f"Failed to generate recommendations: {str(e)}")

@app.post("/search", response_model=SearchResult)
async def semantic_search(
    query: SearchQuery,
    settings: Settings = Depends(get_settings)
) -> SearchResult:
    """Perform semantic search across content."""
    if not vector_store:
        raise HTTPException(500, "Vector Store not initialized")
    
    try:
        # Set query parameters
        content_types = query.content_types or ["research_paper", "news_article", "repository"]
        limit = min(query.limit or 10, 50)  # Cap at 50 items
        
        # Get user profile if provided
        user_embedding = None
        if query.user_id:
            user = await vector_store.get_user(query.user_id)
            if user:
                user_embedding = user.get("embedding")
        
        # Perform hybrid search (text query + optional user embedding)
        results = await vector_store.search(
            query=query.query,
            content_types=content_types,
            limit=limit,
            user_embedding=user_embedding,
            user_weight=query.personalization_weight or 0.3
        )
        
        # Convert to response items
        items = []
        for item in results:
            metadata = item.get("metadata", {})
            score = item.get("score", 0.0)
            
            items.append(ContentItem(
                content_id=item.get("id"),
                content_type=metadata.get("content_type", "unknown"),
                title=metadata.get("title", "Untitled"),
                source=metadata.get("source", "unknown"),
                relevance_score=float(score),
                timestamp=metadata.get("timestamp"),
                entities=metadata.get("entities", [])
            ))
        
        return SearchResult(
            query=query.query,
            items=items,
            total=len(items)
        )
    
    except Exception as e:
        logger.error(f"Error performing search: {e}")
        raise HTTPException(500, f"Search failed: {str(e)}")

@app.post("/vectorize", response_model=ContentVectorization)
async def vectorize_content(
    content: ContentVectorization,
    settings: Settings = Depends(get_settings)
) -> ContentVectorization:
    """Manually vectorize content for recommendation engine."""
    if not vector_store:
        raise HTTPException(500, "Vector Store not initialized")
    
    try:
        # Generate a content ID if not provided
        content_id = content.content_id or str(uuid4())
        
        # Add to vector store
        await vector_store.add_item(
            item_id=content_id,
            text=content.text,
            metadata={
                "id": content_id,
                "content_type": content.content_type,
                "title": content.title,
                "source": content.source,
                "timestamp": str(np.datetime64('now')),
                "entities": content.entities or []
            }
        )
        
        # Update the response
        content.content_id = content_id
        content.processed_at = str(np.datetime64('now'))
        
        return content
    
    except Exception as e:
        logger.error(f"Error vectorizing content: {e}")
        raise HTTPException(500, f"Vectorization failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", "8002"))
    host = os.getenv("HOST", "0.0.0.0")
    
    uvicorn.run("app.main:app", host=host, port=port, reload=True)
