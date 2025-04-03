import os
import pytest
import httpx
import asyncio
import json
from typing import Dict, List, Any, Optional, Callable
import nats
from nats.js.api import StreamConfig
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Service URLs from environment variables
INGESTION_URL = os.getenv("INGESTION_URL", "http://localhost:18001")
ML_ORCHESTRATOR_URL = os.getenv("ML_ORCHESTRATOR_URL", "http://localhost:18002")
KNOWLEDGE_GRAPH_URL = os.getenv("KNOWLEDGE_GRAPH_URL", "http://localhost:18003")
PERSONALIZATION_URL = os.getenv("PERSONALIZATION_URL", "http://localhost:18004")

# NATS configuration
NATS_URL = os.getenv("NATS_URL", "nats://nats_test:password@localhost:14222")

# Other service configurations
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:16379")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:17687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "testpassword")

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session")
async def nats_client():
    """Connect to NATS and create a JetStream client."""
    client = await nats.connect(NATS_URL)
    
    # Create JetStream context
    js = client.jetstream()
    
    # Ensure test stream exists
    try:
        await js.stream_info("chimera_test")
    except nats.js.errors.NotFoundError:
        await js.add_stream(
            StreamConfig(
                name="chimera_test",
                subjects=[
                    "test.*",
                    "ingestion.raw.*",
                    "nlp.enriched.*",
                    "content.vectorized.*",
                    "user.profile.*",
                    "recommendation.request.*",
                ],
                retention="limits",
                max_age=3600,  # 1 hour retention for tests
                storage="memory",
                discard="old",
            )
        )
    
    yield client
    
    # Clean up
    await client.drain()

@pytest.fixture(scope="session")
async def http_client():
    """Create an async HTTP client for API testing."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        yield client

@pytest.fixture
async def wait_for_services(http_client):
    """Wait for all services to be healthy before testing."""
    services = {
        "ingestion": f"{INGESTION_URL}/health",
        "ml_orchestrator": f"{ML_ORCHESTRATOR_URL}/health",
        "knowledge_graph": f"{KNOWLEDGE_GRAPH_URL}/health",
        "personalization": f"{PERSONALIZATION_URL}/health",
    }
    
    @retry(
        stop=stop_after_attempt(10),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
    )
    async def check_service(name, url):
        response = await http_client.get(url)
        response.raise_for_status()
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["healthy", "ok"]
        return True
    
    results = []
    for name, url in services.items():
        try:
            result = await check_service(name, url)
            results.append((name, result))
        except Exception as e:
            results.append((name, False))
            raise RuntimeError(f"Service {name} not healthy: {str(e)}")
    
    return dict(results)

@pytest.fixture
async def clear_test_data():
    """Clear test data from all persistent storage."""
    # Function that will be executed after tests
    async def _clear():
        # Code to clear test data would go here
        # This could include:
        # - Deleting test records from Neo4j
        # - Clearing test keys from Redis
        # - Any other cleanup necessary
        pass
    
    # This will be executed before tests
    yield
    
    # This will be executed after tests
    await _clear()

# Helpers for test data generation
def generate_test_payload(data_type: str, **kwargs) -> Dict[str, Any]:
    """Generate test data payloads for different services."""
    if data_type == "raw_content":
        return {
            "id": kwargs.get("id", "test-content-1"),
            "source": kwargs.get("source", "test-source"),
            "content_type": kwargs.get("content_type", "research_paper"),
            "timestamp": kwargs.get("timestamp", "2025-03-31T23:25:36-04:00"),
            "payload": {
                "title": kwargs.get("title", "Test Research Paper"),
                "text": kwargs.get("text", "This is a test research paper about AI technology."),
                "authors": kwargs.get("authors", ["Test Author"]),
                "publication_date": kwargs.get("publication_date", "2025-03-31"),
                "url": kwargs.get("url", "https://example.com/test-paper"),
            }
        }
    elif data_type == "user_profile":
        return {
            "user_id": kwargs.get("user_id", "test-user-1"),
            "role": kwargs.get("role", "researcher"),
            "interests": kwargs.get("interests", ["AI", "Machine Learning", "Neural Networks"]),
            "preferences": kwargs.get("preferences", {"content_types": ["research_paper"]}),
            "expertise_level": kwargs.get("expertise_level", "expert"),
            "background": kwargs.get("background", "Computer Science"),
            "expertise_areas": kwargs.get("expertise_areas", ["Deep Learning", "Computer Vision"])
        }
    elif data_type == "entity":
        return {
            "name": kwargs.get("name", "Test Entity"),
            "type": kwargs.get("type", "Technology"),
            "properties": kwargs.get("properties", {"relevance": "high"}),
            "source": kwargs.get("source", "test")
        }
    
    raise ValueError(f"Unknown data type: {data_type}")
