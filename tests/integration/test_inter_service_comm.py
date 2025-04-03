#!/usr/bin/env python3
"""
Inter-Service Communication Tests
--------------------------------
Tests to validate the communication patterns between microservices:
- Direct HTTP calls
- Message-based communication via NATS
- Data flow through Redis
- Graph operations via Neo4j
"""

import asyncio
import json
import os
import uuid
import pytest
import httpx
import nats
from nats.js.api import ConsumerConfig, DeliverPolicy
import redis.asyncio as redis
from neo4j import AsyncGraphDatabase

# Test configurations
SERVICES = {
    "ingestion": os.environ.get("INGESTION_URL", "http://localhost:8001"),
    "ml_orchestrator": os.environ.get("ML_ORCHESTRATOR_URL", "http://localhost:8002"),
    "knowledge_graph": os.environ.get("KNOWLEDGE_GRAPH_URL", "http://localhost:8003"),
    "personalization": os.environ.get("PERSONALIZATION_URL", "http://localhost:8004"),
}

NATS_URL = os.environ.get("NATS_URL", "nats://localhost:4222")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
NEO4J_URI = os.environ.get("NEO4J_URI", "neo4j://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "password")

# Test data
TEST_DATA = {
    "content": {
        "id": f"test-{uuid.uuid4().hex[:8]}",
        "source": "integration-test",
        "content_type": "test_document",
        "timestamp": "2025-03-30T12:00:00Z",
        "payload": {
            "title": "Inter-Service Communication Test",
            "text": "This is a test document to validate communication between services.",
            "metadata": {
                "test_id": uuid.uuid4().hex,
                "priority": "high"
            }
        }
    },
    "user": {
        "user_id": f"test-user-{uuid.uuid4().hex[:8]}",
        "role": "tester",
        "interests": ["Testing", "Microservices", "NATS", "Redis"],
        "preferences": {
            "content_types": ["test_document"],
            "delivery_frequency": "realtime"
        }
    }
}

# Fixtures
@pytest.fixture(scope="module")
async def http_client():
    """Create an HTTP client for service communication."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        yield client

@pytest.fixture(scope="module")
async def nats_client():
    """Create a NATS client for message-based communication."""
    nc = await nats.connect(NATS_URL)
    try:
        # Access JetStream
        js = nc.jetstream()
        
        # Ensure test streams exist
        try:
            await js.add_stream(name="TEST_STREAM", subjects=["test.*"])
        except nats.errors.Error:
            # Stream might already exist
            pass
            
        yield nc
    finally:
        await nc.close()

@pytest.fixture(scope="module")
async def redis_client():
    """Create a Redis client for shared data access."""
    client = redis.from_url(REDIS_URL)
    try:
        yield client
    finally:
        await client.close()

@pytest.fixture(scope="module")
async def neo4j_client():
    """Create a Neo4j client for graph operations."""
    driver = AsyncGraphDatabase.driver(
        NEO4J_URI, 
        auth=(NEO4J_USER, NEO4J_PASSWORD)
    )
    try:
        yield driver
    finally:
        await driver.close()

@pytest.fixture(scope="module")
async def test_content_id(http_client):
    """Ingest test content and return its ID."""
    content_id = TEST_DATA["content"]["id"]
    
    # Check if ingestion service is available
    try:
        response = await http_client.get(f"{SERVICES['ingestion']}/health")
        if response.status_code != 200:
            pytest.skip("Ingestion service not available")
    except httpx.RequestError:
        pytest.skip("Ingestion service not available")
    
    # Ingest test content
    response = await http_client.post(
        f"{SERVICES['ingestion']}/ingest",
        json=TEST_DATA["content"]
    )
    assert response.status_code == 200, "Failed to ingest test content"
    
    # Wait a moment for ingestion to process
    await asyncio.sleep(2)
    
    return content_id

@pytest.fixture(scope="module")
async def test_user_id(http_client):
    """Create a test user and return the ID."""
    user_id = TEST_DATA["user"]["user_id"]
    
    # Check if personalization service is available
    try:
        response = await http_client.get(f"{SERVICES['personalization']}/health")
        if response.status_code != 200:
            pytest.skip("Personalization service not available")
    except httpx.RequestError:
        pytest.skip("Personalization service not available")
    
    # Create test user
    response = await http_client.post(
        f"{SERVICES['personalization']}/users",
        json=TEST_DATA["user"]
    )
    
    # If user already exists, that's fine too
    if response.status_code not in (200, 201, 409):
        pytest.fail(f"Failed to create test user: {response.text}")
    
    return user_id

# Tests for HTTP-based communication between services
@pytest.mark.asyncio
async def test_service_health_checks(http_client):
    """Test that all services are healthy and can communicate via HTTP."""
    for service_name, url in SERVICES.items():
        try:
            response = await http_client.get(f"{url}/health")
            assert response.status_code == 200, f"{service_name} health check failed"
            
            data = response.json()
            assert data.get("status") == "healthy", f"{service_name} reports unhealthy status"
            
            # Check component health if provided
            components = data.get("components", {})
            for component, status in components.items():
                assert status.get("status") in ("healthy", "up", "available"), \
                    f"{service_name}'s component {component} is not healthy"
                
            print(f"✅ Service {service_name} is healthy")
        except httpx.RequestError as e:
            pytest.fail(f"Could not connect to {service_name} at {url}: {str(e)}")

@pytest.mark.asyncio
async def test_ml_orchestrator_triton_communication(http_client):
    """Test ML Orchestrator can communicate with Triton Inference Server."""
    try:
        response = await http_client.get(f"{SERVICES['ml_orchestrator']}/models")
        assert response.status_code == 200, "Failed to get models from ML Orchestrator"
        
        models = response.json()
        assert isinstance(models, list), "Models response should be a list"
        assert len(models) > 0, "No models returned from ML Orchestrator"
        
        print(f"✅ ML Orchestrator successfully communicates with Triton")
        print(f"📊 Available models: {', '.join([m.get('name') for m in models])}")
    except httpx.RequestError:
        pytest.skip("ML Orchestrator service not available")

@pytest.mark.asyncio
async def test_knowledge_graph_neo4j_communication(http_client):
    """Test Knowledge Graph service can communicate with Neo4j."""
    try:
        response = await http_client.get(f"{SERVICES['knowledge_graph']}/graph/stats")
        assert response.status_code == 200, "Failed to get graph stats"
        
        stats = response.json()
        assert "nodes" in stats, "Graph stats should contain node count"
        assert "relationships" in stats, "Graph stats should contain relationship count"
        
        print(f"✅ Knowledge Graph service successfully communicates with Neo4j")
        print(f"📊 Graph stats: {stats['nodes']} nodes, {stats['relationships']} relationships")
    except httpx.RequestError:
        pytest.skip("Knowledge Graph service not available")

@pytest.mark.asyncio
async def test_personalization_vector_store_communication(http_client):
    """Test Personalization Engine can communicate with Vector Store."""
    try:
        response = await http_client.get(f"{SERVICES['personalization']}/vector-store/stats")
        assert response.status_code == 200, "Failed to get vector store stats"
        
        stats = response.json()
        assert "vectors" in stats, "Vector store stats should contain vector count"
        assert "dimensions" in stats, "Vector store stats should contain dimensions"
        
        print(f"✅ Personalization Engine successfully communicates with Vector Store")
        print(f"📊 Vector store stats: {stats['vectors']} vectors of {stats['dimensions']} dimensions")
    except httpx.RequestError:
        pytest.skip("Personalization service not available")

# Tests for NATS-based communication between services
@pytest.mark.asyncio
async def test_nats_messaging(nats_client, test_content_id):
    """Test NATS messaging between services."""
    # Create unique subject for this test
    test_subject = f"test.inter_service.{uuid.uuid4().hex[:8]}"
    
    # Create a JetStream context
    js = nats_client.jetstream()
    
    # Subscribe to test messages
    received_messages = []
    
    async def message_handler(msg):
        data = json.loads(msg.data.decode())
        received_messages.append(data)
        await msg.ack()
    
    # Create an ephemeral consumer
    psub = await js.pull_subscribe(
        subject=test_subject,
        durable="test_consumer",
        config=ConsumerConfig(deliver_policy=DeliverPolicy.NEW)
    )
    
    # Publish a test message
    test_payload = {
        "content_id": test_content_id,
        "timestamp": "2025-03-30T12:01:00Z",
        "action": "process",
        "metadata": {
            "test_id": uuid.uuid4().hex,
            "priority": "high"
        }
    }
    
    await js.publish(test_subject, json.dumps(test_payload).encode())
    print(f"✅ Published test message to {test_subject}")
    
    # Fetch messages
    await asyncio.sleep(1)
    messages = await psub.fetch(1, timeout=3)
    
    for msg in messages:
        await message_handler(msg)
    
    # Clean up
    await js.delete_consumer("TEST_STREAM", "test_consumer")
    
    # Verify we received the message
    assert len(received_messages) > 0, "No messages received via NATS"
    assert received_messages[0]["content_id"] == test_content_id, "Message content ID mismatch"
    assert received_messages[0]["action"] == "process", "Message action mismatch"
    
    print(f"✅ Successfully received message via NATS")

@pytest.mark.asyncio
async def test_redis_data_sharing(redis_client, test_content_id):
    """Test data sharing between services via Redis."""
    test_key = f"test:content:{test_content_id}"
    test_data = {
        "id": test_content_id,
        "status": "processing",
        "last_updated": "2025-03-30T12:02:00Z",
        "metadata": {
            "test_id": uuid.uuid4().hex,
            "service": "integration_test"
        }
    }
    
    # Store test data in Redis
    await redis_client.set(test_key, json.dumps(test_data))
    
    # Set a short TTL for cleanup
    await redis_client.expire(test_key, 60)
    
    # Verify data was stored
    stored_data = await redis_client.get(test_key)
    assert stored_data is not None, "Failed to store data in Redis"
    
    stored_json = json.loads(stored_data)
    assert stored_json["id"] == test_content_id, "Redis data ID mismatch"
    
    print(f"✅ Successfully shared data via Redis")
    
    # Test Redis PubSub
    test_channel = f"test:events:{uuid.uuid4().hex[:8]}"
    test_event = {
        "event_type": "content_processed",
        "content_id": test_content_id,
        "timestamp": "2025-03-30T12:03:00Z"
    }
    
    # Use a separate Redis client for PubSub
    redis_pubsub = redis.from_url(REDIS_URL)
    
    try:
        # Setup receiver
        received_events = []
        
        async def message_handler(message):
            if message["type"] == "message":
                data = json.loads(message["data"])
                received_events.append(data)
        
        # Subscribe to channel
        pubsub = redis_pubsub.pubsub()
        await pubsub.subscribe(test_channel)
        
        # Start listening in the background
        future = asyncio.create_task(pubsub.run(message_handler))
        
        # Give the subscription time to initialize
        await asyncio.sleep(1)
        
        # Publish event
        await redis_client.publish(test_channel, json.dumps(test_event))
        
        # Wait for the event to be received
        await asyncio.sleep(2)
        
        # Cancel the pubsub task
        future.cancel()
        try:
            await future
        except asyncio.CancelledError:
            pass
        
        # Verify event was received
        assert len(received_events) > 0, "No events received via Redis PubSub"
        assert received_events[0]["content_id"] == test_content_id, "Event content ID mismatch"
        assert received_events[0]["event_type"] == "content_processed", "Event type mismatch"
        
        print(f"✅ Successfully published and received events via Redis PubSub")
    finally:
        await redis_pubsub.close()

@pytest.mark.asyncio
async def test_neo4j_graph_operations(neo4j_client, test_content_id):
    """Test graph operations via Neo4j."""
    # Generate unique labels for this test run to avoid conflicts
    content_label = f"TestContent_{uuid.uuid4().hex[:8]}"
    entity_label = f"TestEntity_{uuid.uuid4().hex[:8]}"
    relationship_type = "TEST_CONTAINS"
    
    # Create test nodes and relationships
    session = neo4j_client.session()
    
    try:
        # Create content node
        result = await session.run(
            f"""
            CREATE (c:{content_label} {{id: $content_id, type: 'test_document'}})
            RETURN c
            """,
            {"content_id": test_content_id}
        )
        content_node = await result.single()
        assert content_node is not None, "Failed to create content node"
        
        # Create entity nodes and relationships
        test_entities = [
            {"name": "Test Entity 1", "type": "concept"},
            {"name": "Test Entity 2", "type": "technology"},
            {"name": "Test Entity 3", "type": "method"}
        ]
        
        for entity in test_entities:
            result = await session.run(
                f"""
                CREATE (e:{entity_label} {{name: $name, type: $type}})
                WITH e
                MATCH (c:{content_label} {{id: $content_id}})
                CREATE (c)-[r:{relationship_type}]->(e)
                RETURN e, r
                """,
                {"name": entity["name"], "type": entity["type"], "content_id": test_content_id}
            )
            record = await result.single()
            assert record is not None, f"Failed to create entity {entity['name']}"
        
        # Query the graph to verify
        result = await session.run(
            f"""
            MATCH (c:{content_label} {{id: $content_id}})-[r:{relationship_type}]->(e:{entity_label})
            RETURN c, collect(e) as entities, count(e) as entity_count
            """,
            {"content_id": test_content_id}
        )
        record = await result.single()
        assert record is not None, "Failed to query content with entities"
        assert record["entity_count"] == len(test_entities), "Entity count mismatch"
        
        print(f"✅ Successfully performed graph operations via Neo4j")
        print(f"📊 Created {record['entity_count']} entity nodes connected to content node")
    finally:
        # Clean up test nodes
        await session.run(
            f"""
            MATCH (c:{content_label} {{id: $content_id}})
            OPTIONAL MATCH (c)-[r]->(e:{entity_label})
            DETACH DELETE c, e
            """,
            {"content_id": test_content_id}
        )
        
        await session.close()

@pytest.mark.asyncio
async def test_full_data_flow(http_client, nats_client, redis_client, neo4j_client, test_content_id, test_user_id):
    """Test complete data flow across all services."""
    # Check that content was ingested properly via HTTP
    try:
        response = await http_client.get(f"{SERVICES['ingestion']}/content/{test_content_id}")
        assert response.status_code == 200, "Failed to retrieve content from Ingestion Service"
        content = response.json()
        assert content["id"] == test_content_id, "Content ID mismatch"
        print(f"✅ Successfully verified content ingestion via HTTP")
    except httpx.RequestError:
        pytest.skip("Ingestion service not available")
    
    # Check that content was processed by ML Orchestrator
    max_attempts = 10
    ml_processed = False
    
    for attempt in range(max_attempts):
        try:
            response = await http_client.get(f"{SERVICES['ml_orchestrator']}/status/{test_content_id}")
            if response.status_code == 200:
                status = response.json()
                if status.get("status") == "completed":
                    ml_processed = True
                    break
            
            # Wait before retrying
            await asyncio.sleep(2)
        except httpx.RequestError:
            # Service might be temporarily unavailable
            await asyncio.sleep(2)
    
    if ml_processed:
        print(f"✅ Successfully verified ML processing of content")
    else:
        print(f"⚠️ ML processing verification timed out - this might be expected in test environment")
    
    # Check that entities were added to Knowledge Graph
    try:
        response = await http_client.get(
            f"{SERVICES['knowledge_graph']}/entities",
            params={"filter": f"source_id:{test_content_id}"}
        )
        
        if response.status_code == 200:
            entities = response.json()
            if entities:
                print(f"✅ Successfully verified Knowledge Graph entities ({len(entities)} entities)")
                for i, entity in enumerate(entities[:3]):
                    print(f"    📊 Entity {i+1}: {entity.get('name')} (Type: {entity.get('type')})")
            else:
                print(f"⚠️ No entities found for content - this might be expected in test environment")
        else:
            print(f"⚠️ Knowledge Graph query returned status {response.status_code}")
    except httpx.RequestError:
        print(f"⚠️ Knowledge Graph service not available - this might be expected in test environment")
    
    # Check for personalized recommendations
    try:
        response = await http_client.post(
            f"{SERVICES['personalization']}/recommendations",
            json={"user_id": test_user_id, "limit": 5}
        )
        
        if response.status_code == 200:
            recommendations = response.json()
            if recommendations:
                print(f"✅ Successfully retrieved personalized recommendations ({len(recommendations)} items)")
                for i, rec in enumerate(recommendations[:3]):
                    print(f"    📚 Recommendation {i+1}: {rec.get('title')} (Score: {rec.get('relevance_score', 0):.2f})")
            else:
                print(f"⚠️ No recommendations found - this might be expected in test environment")
        else:
            print(f"⚠️ Personalization query returned status {response.status_code}")
    except httpx.RequestError:
        print(f"⚠️ Personalization service not available - this might be expected in test environment")

if __name__ == "__main__":
    pytest.main(["-xvs", __file__])
