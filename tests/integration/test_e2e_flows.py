import pytest
import asyncio
import json
import uuid
import time
from typing import Dict, List, Any
import httpx
import allure

# Import helper functions from conftest
from conftest import (
    INGESTION_URL,
    ML_ORCHESTRATOR_URL,
    KNOWLEDGE_GRAPH_URL,
    PERSONALIZATION_URL,
    generate_test_payload
)

@allure.epic("Chimera Platform")
@allure.feature("End-to-End Data Flow")
class TestE2EDataFlow:
    """Test complete end-to-end data flows across all microservices."""
    
    @pytest.mark.asyncio
    @allure.story("Complete Content Pipeline")
    @allure.severity(allure.severity_level.CRITICAL)
    async def test_complete_data_pipeline(self, http_client, nats_client, wait_for_services, clear_test_data):
        """Test the complete data pipeline from ingestion to personalization."""
        # Validate all services are healthy
        assert wait_for_services
        
        # Step 1: Create a test user profile
        with allure.step("Create user profile"):
            user_id = f"test-user-{uuid.uuid4()}"
            user_payload = generate_test_payload("user_profile", user_id=user_id)
            
            response = await http_client.post(
                f"{PERSONALIZATION_URL}/users",
                json=user_payload
            )
            assert response.status_code == 200
            user_data = response.json()
            assert user_data["user_id"] == user_id
            assert len(user_data["interests"]) > 0
        
        # Step 2: Ingest test content
        with allure.step("Ingest test content"):
            content_id = f"test-content-{uuid.uuid4()}"
            content_payload = generate_test_payload(
                "raw_content", 
                id=content_id,
                title="Neural Networks in Production",
                text="This research paper discusses advanced neural network architectures for production systems. " +
                     "Deep learning models can be optimized for inference in various ways. " +
                     "The paper explores techniques for model compression and quantization."
            )
            
            response = await http_client.post(
                f"{INGESTION_URL}/ingest",
                json=content_payload
            )
            assert response.status_code == 202
            ingest_result = response.json()
            assert ingest_result["id"] == content_id
            assert ingest_result["status"] == "processing"
        
        # Step 3: Wait for the content to be processed through the pipeline
        with allure.step("Monitor NLP enrichment"):
            # Setup subscription to monitor processing
            nlp_result = None
            enrichment_complete = asyncio.Event()
            
            async def nlp_monitor(msg):
                nonlocal nlp_result
                data = json.loads(msg.data.decode())
                if data.get("id") == content_id:
                    nlp_result = data
                    enrichment_complete.set()
                await msg.ack()
            
            # Subscribe to NLP enrichment notifications
            sub = await nats_client.subscribe("nlp.enriched.*", cb=nlp_monitor)
            
            # Wait for enrichment to complete (with timeout)
            try:
                await asyncio.wait_for(enrichment_complete.wait(), timeout=30.0)
            except asyncio.TimeoutError:
                pytest.fail("Timed out waiting for NLP enrichment")
            finally:
                await sub.unsubscribe()
            
            assert nlp_result is not None
            assert nlp_result["id"] == content_id
            assert "nlp_enrichment" in nlp_result
        
        # Step 4: Validate knowledge graph processing
        with allure.step("Verify knowledge graph processing"):
            # Give the knowledge graph service time to process
            await asyncio.sleep(3)
            
            # Query the knowledge graph for the content entity
            response = await http_client.get(
                f"{KNOWLEDGE_GRAPH_URL}/entities",
                params={"filter": f"source_id:{content_id}"}
            )
            assert response.status_code == 200
            entities = response.json()
            assert len(entities) > 0
            
            # Check for expected entities
            entity_names = [e["name"] for e in entities]
            assert any(name.lower() == "neural networks" for name in entity_names)
        
        # Step 5: Wait for vectorization and check for recommendations
        with allure.step("Verify personalization engine processing"):
            # Wait for content to be vectorized
            max_attempts = 10
            for attempt in range(max_attempts):
                # Request recommendations for the user
                response = await http_client.post(
                    f"{PERSONALIZATION_URL}/recommendations",
                    json={"user_id": user_id, "limit": 5}
                )
                
                if response.status_code == 200:
                    recommendations = response.json()
                    if any(r["content_id"] == content_id for r in recommendations):
                        break
                
                # Wait before retrying
                await asyncio.sleep(3)
                
                # Last attempt
                if attempt == max_attempts - 1:
                    pytest.fail("Content not available in recommendations after maximum retries")
            
            # Final validation of recommendations
            response = await http_client.post(
                f"{PERSONALIZATION_URL}/recommendations",
                json={"user_id": user_id, "limit": 5}
            )
            assert response.status_code == 200
            recommendations = response.json()
            assert len(recommendations) > 0
            
            # Verify our test content is in recommendations
            content_recs = [r for r in recommendations if r["content_id"] == content_id]
            assert len(content_recs) > 0
            assert content_recs[0]["relevance_score"] > 0
        
        # Step 6: Test semantic search functionality
        with allure.step("Test semantic search"):
            # Search for content with keywords
            response = await http_client.post(
                f"{PERSONALIZATION_URL}/search",
                json={
                    "query": "neural networks optimization",
                    "user_id": user_id,
                    "personalization_weight": 0.3
                }
            )
            assert response.status_code == 200
            search_results = response.json()
            assert search_results["total"] > 0
            
            # Verify our test content is in search results
            content_results = [r for r in search_results["items"] if r["content_id"] == content_id]
            assert len(content_results) > 0
    
    @pytest.mark.asyncio
    @allure.story("User Profile Personalization")
    @allure.severity(allure.severity_level.HIGH)
    async def test_user_profile_updates(self, http_client, wait_for_services, clear_test_data):
        """Test updates to user profiles and how they affect recommendations."""
        # Create initial user profile
        user_id = f"test-user-{uuid.uuid4()}"
        initial_interests = ["Machine Learning", "Data Science"]
        updated_interests = ["Neural Networks", "Computer Vision", "Deep Learning"]
        
        # Step 1: Create initial profile
        with allure.step("Create initial user profile"):
            user_payload = generate_test_payload(
                "user_profile", 
                user_id=user_id,
                interests=initial_interests,
                expertise_level="beginner"
            )
            
            response = await http_client.post(
                f"{PERSONALIZATION_URL}/users",
                json=user_payload
            )
            assert response.status_code == 200
            user_data = response.json()
            assert user_data["user_id"] == user_id
            assert set(user_data["interests"]) == set(initial_interests)
        
        # Step 2: Add vectorized content through direct API
        with allure.step("Add test vectorized content"):
            # Add multiple content items with different topics
            content_items = [
                {
                    "content_id": f"cv-content-{uuid.uuid4()}",
                    "content_type": "research_paper",
                    "title": "Advanced Computer Vision Techniques",
                    "text": "This paper explores the latest developments in computer vision and image recognition.",
                    "source": "test_academic",
                    "entities": ["Computer Vision", "Image Recognition", "AI"]
                },
                {
                    "content_id": f"ml-content-{uuid.uuid4()}",
                    "content_type": "research_paper",
                    "title": "Machine Learning Fundamentals",
                    "text": "An introduction to machine learning algorithms and techniques for beginners.",
                    "source": "test_academic",
                    "entities": ["Machine Learning", "Algorithms", "Data Science"]
                },
                {
                    "content_id": f"dl-content-{uuid.uuid4()}",
                    "content_type": "research_paper",
                    "title": "Deep Learning Architectures",
                    "text": "A comprehensive review of modern neural network architectures and training methods.",
                    "source": "test_academic",
                    "entities": ["Deep Learning", "Neural Networks", "AI"]
                }
            ]
            
            for item in content_items:
                response = await http_client.post(
                    f"{PERSONALIZATION_URL}/vectorize",
                    json=item
                )
                assert response.status_code == 200
        
        # Step 3: Get initial recommendations
        with allure.step("Get initial recommendations"):
            response = await http_client.post(
                f"{PERSONALIZATION_URL}/recommendations",
                json={"user_id": user_id, "limit": 10}
            )
            assert response.status_code == 200
            initial_recs = response.json()
            
            # Initial profile should prioritize ML content
            ml_first = False
            for rec in initial_recs:
                if "Machine Learning" in rec.get("title", ""):
                    ml_first = True
                    break
            assert ml_first, "Machine Learning content should be prioritized for initial profile"
        
        # Step 4: Update user profile with new interests
        with allure.step("Update user profile with new interests"):
            user_payload = generate_test_payload(
                "user_profile", 
                user_id=user_id,
                interests=updated_interests,
                expertise_level="intermediate"
            )
            
            response = await http_client.put(
                f"{PERSONALIZATION_URL}/users/{user_id}",
                json=user_payload
            )
            assert response.status_code == 200
            user_data = response.json()
            assert set(user_data["interests"]) == set(updated_interests)
        
        # Step 5: Get updated recommendations
        with allure.step("Get updated recommendations"):
            # Wait briefly for embeddings to update
            await asyncio.sleep(2)
            
            response = await http_client.post(
                f"{PERSONALIZATION_URL}/recommendations",
                json={"user_id": user_id, "limit": 10}
            )
            assert response.status_code == 200
            updated_recs = response.json()
            
            # Updated profile should prioritize neural networks/deep learning content
            dl_first = False
            for rec in updated_recs[:3]:  # Check top 3
                if "Deep Learning" in rec.get("title", "") or "Neural Networks" in rec.get("title", ""):
                    dl_first = True
                    break
            assert dl_first, "Neural Networks/Deep Learning content should be prioritized after profile update"

@allure.epic("Chimera Platform")
@allure.feature("Microservice Communication")
class TestInterServiceCommunication:
    """Test specific inter-service communication patterns."""
    
    @pytest.mark.asyncio
    @allure.story("Ingestion to ML Orchestration")
    async def test_ingestion_to_ml_orchestration(self, http_client, nats_client, wait_for_services):
        """Test data flow from Ingestion Service to ML Orchestrator."""
        # Configure message monitoring
        message_received = asyncio.Event()
        test_data = None
        
        async def message_handler(msg):
            nonlocal test_data
            data = json.loads(msg.data.decode())
            test_data = data
            message_received.set()
            await msg.ack()
        
        # Subscribe to the relevant subject
        sub = await nats_client.subscribe("ingestion.raw.*", cb=message_handler)
        
        try:
            # Generate test content
            content_id = f"test-ml-{uuid.uuid4()}"
            content_payload = generate_test_payload("raw_content", id=content_id)
            
            # Send to ingestion service
            response = await http_client.post(
                f"{INGESTION_URL}/ingest",
                json=content_payload
            )
            assert response.status_code == 202
            
            # Wait for message to be processed
            try:
                await asyncio.wait_for(message_received.wait(), timeout=15.0)
            except asyncio.TimeoutError:
                pytest.fail("Message not received within timeout period")
            
            # Verify message content
            assert test_data is not None
            assert test_data["id"] == content_id
            
            # Check ML Orchestrator processed it
            await asyncio.sleep(3)  # Give some time for processing
            
            # Query ML Orchestrator status endpoint
            response = await http_client.get(
                f"{ML_ORCHESTRATOR_URL}/status/{content_id}"
            )
            assert response.status_code in [200, 202, 404]  # May be 404 if processed and cleared
            
        finally:
            await sub.unsubscribe()
    
    @pytest.mark.asyncio
    @allure.story("ML Orchestrator to Knowledge Graph")
    async def test_ml_to_knowledge_graph(self, http_client, nats_client, wait_for_services):
        """Test data flow from ML Orchestrator to Knowledge Graph."""
        # Create a mock NLP-enriched message
        content_id = f"test-kg-{uuid.uuid4()}"
        enriched_data = {
            "id": content_id,
            "source": "test-source",
            "content_type": "research_paper",
            "timestamp": str(time.time()),
            "nlp_enrichment": {
                "entities": [
                    {"text": "AI Platform", "label": "PRODUCT", "score": 0.95},
                    {"text": "NVIDIA", "label": "ORGANIZATION", "score": 0.92},
                    {"text": "GPU Acceleration", "label": "TECHNOLOGY", "score": 0.89}
                ],
                "summary": "Test summary about AI platforms using NVIDIA GPUs.",
                "keywords": ["AI", "NVIDIA", "GPU", "acceleration"],
                "sentiment": {"positive": 0.7, "negative": 0.1, "neutral": 0.2}
            },
            "payload": {
                "title": "GPU-Accelerated AI Platforms",
                "text": "This is test content about NVIDIA's GPU-accelerated AI platforms."
            }
        }
        
        # Publish directly to NLP enriched subject
        await nats_client.publish(
            f"nlp.enriched.{enriched_data['content_type']}",
            json.dumps(enriched_data)
        )
        
        # Wait for Knowledge Graph to process
        await asyncio.sleep(5)
        
        # Verify entities were created in Knowledge Graph
        response = await http_client.get(
            f"{KNOWLEDGE_GRAPH_URL}/entities",
            params={"filter": f"source_id:{content_id}"}
        )
        assert response.status_code == 200
        entities = response.json()
        
        # Verify expected entities exist
        entity_names = [e["name"].upper() for e in entities]
        assert "NVIDIA" in entity_names or "GPU ACCELERATION" in entity_names
        
        # Check relationships were created
        response = await http_client.get(
            f"{KNOWLEDGE_GRAPH_URL}/relationships",
            params={"filter": f"source_id:{content_id}"}
        )
        assert response.status_code == 200
        relationships = response.json()
        assert len(relationships) > 0
    
    @pytest.mark.asyncio
    @allure.story("Knowledge Graph to Personalization Engine")
    async def test_knowledge_graph_to_personalization(self, http_client, nats_client, wait_for_services):
        """Test data flow from Knowledge Graph to Personalization Engine."""
        content_id = f"test-pers-{uuid.uuid4()}"
        
        # Create an entity in the Knowledge Graph
        entity_payload = {
            "name": "Test Entity",
            "type": "TECHNOLOGY",
            "properties": {
                "description": "A test technology entity",
                "source_id": content_id
            }
        }
        
        response = await http_client.post(
            f"{KNOWLEDGE_GRAPH_URL}/entities",
            json=entity_payload
        )
        assert response.status_code in [200, 201]
        
        # Directly publish enriched content that would trigger vectorization
        enriched_data = {
            "id": content_id,
            "source": "test-source",
            "content_type": "research_paper",
            "timestamp": str(time.time()),
            "nlp_enrichment": {
                "entities": [
                    {"text": "Test Entity", "label": "TECHNOLOGY", "score": 0.95}
                ],
                "summary": "Test summary about test entities.",
            },
            "payload": {
                "title": "Test Entity Research",
                "text": "This is a test document about Test Entity technology."
            }
        }
        
        await nats_client.publish(
            f"nlp.enriched.{enriched_data['content_type']}",
            json.dumps(enriched_data)
        )
        
        # Wait for processing
        await asyncio.sleep(5)
        
        # Check if vectorized in Personalization Engine
        # Create a user to test search
        user_id = f"test-user-{uuid.uuid4()}"
        user_payload = generate_test_payload(
            "user_profile", 
            user_id=user_id,
            interests=["Test Entity", "Technology"]
        )
        
        response = await http_client.post(
            f"{PERSONALIZATION_URL}/users",
            json=user_payload
        )
        assert response.status_code == 200
        
        # Search for the entity
        response = await http_client.post(
            f"{PERSONALIZATION_URL}/search",
            json={"query": "Test Entity", "user_id": user_id}
        )
        assert response.status_code == 200
        search_results = response.json()
        
        # Verify found in results
        found = False
        for item in search_results.get("items", []):
            if item.get("content_id") == content_id:
                found = True
                break
        
        assert found, "Content should be found in personalization engine"
