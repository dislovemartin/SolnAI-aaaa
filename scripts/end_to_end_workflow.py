#!/usr/bin/env python3
"""
Chimera Platform End-to-End Workflow Demonstration
-------------------------------------------------
This script demonstrates a complete workflow through the Chimera platform:
1. Data ingestion via the Ingestion Service
2. ML processing via ML Orchestrator
3. Knowledge Graph enrichment
4. Personalized recommendations via Personalization Engine

Usage:
    python end_to_end_workflow.py [--config CONFIG_FILE]
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional

import httpx
import coloredlogs

# Configure logging
logger = logging.getLogger("chimera-workflow")
coloredlogs.install(
    level="INFO",
    logger=logger,
    fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# Default configuration
DEFAULT_CONFIG = {
    "ingestion_url": "http://localhost:8001",
    "ml_orchestrator_url": "http://localhost:8002",
    "knowledge_graph_url": "http://localhost:8003",
    "personalization_url": "http://localhost:8002",  # Same port as ML Orchestrator but different service
    "timeout": 60,
    "poll_interval": 2
}

class ChimeraWorkflow:
    """Orchestrates end-to-end workflows through Chimera platform."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the workflow with configuration."""
        self.config = config
        self.http_client = httpx.AsyncClient(timeout=config["timeout"])
        self.request_id = str(uuid.uuid4())
        self.user_id = f"demo-user-{uuid.uuid4().hex[:8]}"
    
    async def close(self):
        """Close resources."""
        await self.http_client.aclose()
    
    async def ingest_sample_content(self) -> List[str]:
        """Ingest sample content through the Ingestion Service.
        
        Returns:
            List of content IDs that were ingested
        """
        logger.info("⚡ Step 1: Ingesting sample content")
        
        # Sample research papers about AI technologies
        sample_content = [
            {
                "id": f"paper-{uuid.uuid4().hex[:8]}",
                "source": "research-database",
                "content_type": "research_paper",
                "timestamp": datetime.utcnow().isoformat(),
                "payload": {
                    "title": "Advanced Techniques in Neural Network Deployment for Production Systems",
                    "text": """
                    This research paper discusses state-of-the-art approaches for deploying neural networks 
                    in production environments. We explore techniques for model optimization, including 
                    quantization, pruning, and knowledge distillation. Additionally, we discuss deployment 
                    strategies across different hardware platforms, with a focus on NVIDIA GPU acceleration 
                    technologies. The paper presents benchmark results comparing inference performance
                    across various model architectures and optimization strategies.
                    """,
                    "authors": ["Dr. Alexandra Smith", "Dr. Michael Chen"],
                    "publication_date": "2025-02-15",
                    "url": "https://example.com/research/neural-networks-production"
                }
            },
            {
                "id": f"paper-{uuid.uuid4().hex[:8]}",
                "source": "research-database",
                "content_type": "research_paper",
                "timestamp": datetime.utcnow().isoformat(),
                "payload": {
                    "title": "Knowledge Graph Applications in Enterprise AI Systems",
                    "text": """
                    This paper explores the application of knowledge graphs in enterprise AI systems.
                    We discuss the integration of semantic networks with machine learning pipelines
                    to enhance reasoning capabilities and provide context-aware intelligence.
                    The research presents a novel architecture that combines Neo4j graph databases
                    with vector embeddings to create a hybrid semantic-neural system capable of
                    advanced inference across diverse data sources.
                    """,
                    "authors": ["Dr. Sarah Johnson", "Dr. David Williams"],
                    "publication_date": "2025-03-01",
                    "url": "https://example.com/research/knowledge-graph-applications"
                }
            },
            {
                "id": f"news-{uuid.uuid4().hex[:8]}",
                "source": "tech-news",
                "content_type": "news_article",
                "timestamp": datetime.utcnow().isoformat(),
                "payload": {
                    "title": "NVIDIA Announces Next-Generation GPU Architecture",
                    "text": """
                    NVIDIA today announced their next-generation GPU architecture, codenamed "Cascade,"
                    which promises significant improvements in AI training and inference performance.
                    The new architecture features enhanced Tensor Cores optimized for transformer models,
                    along with specialized hardware for graph neural networks. Industry analysts suggest
                    this development could accelerate AI model development cycles by up to 40% while
                    reducing energy consumption compared to previous generations.
                    """,
                    "author": "Tech Insider Team",
                    "publication_date": "2025-03-25",
                    "url": "https://example.com/news/nvidia-next-gen-gpu"
                }
            }
        ]
        
        content_ids = []
        for content in sample_content:
            try:
                logger.info(f"  📥 Ingesting: {content['payload']['title']}")
                response = await self.http_client.post(
                    f"{self.config['ingestion_url']}/ingest",
                    json=content
                )
                response.raise_for_status()
                result = response.json()
                content_ids.append(content["id"])
                logger.info(f"  ✅ Successfully ingested content with ID: {content['id']}")
            except httpx.HTTPError as e:
                logger.error(f"  ❌ Failed to ingest content: {str(e)}")
        
        return content_ids
    
    async def monitor_ml_processing(self, content_ids: List[str]) -> bool:
        """Monitor ML processing of ingested content.
        
        Args:
            content_ids: List of content IDs to monitor
            
        Returns:
            True if all content was processed successfully
        """
        logger.info("⚡ Step 2: Monitoring ML processing")
        
        # Wait for all content to be processed
        max_attempts = 30
        all_processed = False
        
        for attempt in range(max_attempts):
            processed_count = 0
            
            for content_id in content_ids:
                try:
                    response = await self.http_client.get(
                        f"{self.config['ml_orchestrator_url']}/status/{content_id}"
                    )
                    
                    if response.status_code == 200:
                        status = response.json()
                        if status.get("status") == "completed":
                            processed_count += 1
                            logger.info(f"  ✅ Content {content_id} processed successfully")
                        elif status.get("status") == "failed":
                            logger.error(f"  ❌ Processing failed for content {content_id}: {status.get('error')}")
                        else:
                            logger.info(f"  ⏳ Content {content_id} is still processing: {status.get('status')}")
                    elif response.status_code == 404:
                        # May be 404 if already processed and cleared from cache
                        processed_count += 1
                        logger.info(f"  ✅ Content {content_id} likely processed (not in processing queue)")
                except httpx.HTTPError as e:
                    logger.error(f"  ❌ Error checking status for {content_id}: {str(e)}")
            
            if processed_count == len(content_ids):
                all_processed = True
                break
            
            logger.info(f"  ⏳ Waiting for processing: {processed_count}/{len(content_ids)} complete")
            await asyncio.sleep(self.config["poll_interval"])
        
        if all_processed:
            logger.info("  ✅ All content processed successfully by ML Orchestrator")
        else:
            logger.warning("  ⚠️ Timed out waiting for all content to be processed")
        
        return all_processed
    
    async def verify_knowledge_graph(self, content_ids: List[str]) -> Dict[str, List[str]]:
        """Verify that content has been added to Knowledge Graph.
        
        Args:
            content_ids: List of content IDs to verify
            
        Returns:
            Dictionary mapping content IDs to lists of entity IDs
        """
        logger.info("⚡ Step 3: Verifying Knowledge Graph enrichment")
        
        content_entities = {}
        
        # Give Knowledge Graph time to process
        await asyncio.sleep(5)
        
        # Query entities for each content
        for content_id in content_ids:
            try:
                response = await self.http_client.get(
                    f"{self.config['knowledge_graph_url']}/entities",
                    params={"filter": f"source_id:{content_id}"}
                )
                response.raise_for_status()
                entities = response.json()
                
                if entities:
                    entity_ids = [entity["id"] for entity in entities]
                    content_entities[content_id] = entity_ids
                    logger.info(f"  ✅ Found {len(entities)} entities for content {content_id}")
                    
                    # Print a few entity examples
                    for i, entity in enumerate(entities[:3]):
                        logger.info(f"    📊 Entity: {entity['name']} (Type: {entity['type']})")
                else:
                    logger.warning(f"  ⚠️ No entities found for content {content_id}")
                    content_entities[content_id] = []
            except httpx.HTTPError as e:
                logger.error(f"  ❌ Error querying entities for {content_id}: {str(e)}")
                content_entities[content_id] = []
        
        # Get relationships between entities
        try:
            entity_ids = [eid for ids in content_entities.values() for eid in ids]
            if entity_ids:
                entity_filter = f"id:{entity_ids[0]}" + "".join([f" OR id:{eid}" for eid in entity_ids[1:]])
                response = await self.http_client.get(
                    f"{self.config['knowledge_graph_url']}/relationships",
                    params={"filter": entity_filter}
                )
                response.raise_for_status()
                relationships = response.json()
                
                if relationships:
                    logger.info(f"  ✅ Found {len(relationships)} relationships between entities")
                    # Print a few relationship examples
                    for i, rel in enumerate(relationships[:3]):
                        logger.info(f"    🔄 Relationship: {rel['start_entity']} --[{rel['type']}]--> {rel['end_entity']}")
                else:
                    logger.warning("  ⚠️ No relationships found between entities")
            else:
                logger.warning("  ⚠️ No entity IDs to query relationships")
        except httpx.HTTPError as e:
            logger.error(f"  ❌ Error querying relationships: {str(e)}")
        
        return content_entities
    
    async def create_user_profile(self) -> str:
        """Create a test user profile for personalization.
        
        Returns:
            User ID of the created profile
        """
        logger.info("⚡ Step 4: Creating user profile for personalization")
        
        user_profile = {
            "user_id": self.user_id,
            "role": "researcher",
            "interests": ["Neural Networks", "GPU Acceleration", "Knowledge Graphs", "Enterprise AI"],
            "preferences": {
                "content_types": ["research_paper", "news_article"],
                "delivery_frequency": "daily"
            },
            "expertise_level": "expert",
            "background": "Computer Science",
            "expertise_areas": ["Deep Learning", "Distributed Systems"]
        }
        
        try:
            response = await self.http_client.post(
                f"{self.config['personalization_url']}/users",
                json=user_profile
            )
            response.raise_for_status()
            profile = response.json()
            logger.info(f"  ✅ Created user profile with ID: {profile['user_id']}")
            logger.info(f"    👤 Role: {profile['role']}")
            logger.info(f"    🧠 Interests: {', '.join(profile['interests'])}")
            return profile["user_id"]
        except httpx.HTTPError as e:
            logger.error(f"  ❌ Failed to create user profile: {str(e)}")
            return self.user_id  # Return the generated ID even if creation failed
    
    async def get_personalized_recommendations(self, user_id: str) -> List[Dict[str, Any]]:
        """Get personalized recommendations for a user.
        
        Args:
            user_id: User ID to get recommendations for
            
        Returns:
            List of recommendation objects
        """
        logger.info("⚡ Step 5: Getting personalized recommendations")
        
        # Wait for content to be vectorized
        await asyncio.sleep(5)
        
        try:
            response = await self.http_client.post(
                f"{self.config['personalization_url']}/recommendations",
                json={
                    "user_id": user_id,
                    "limit": 10
                }
            )
            response.raise_for_status()
            recommendations = response.json()
            
            if recommendations:
                logger.info(f"  ✅ Retrieved {len(recommendations)} personalized recommendations")
                for i, rec in enumerate(recommendations[:5], 1):
                    logger.info(f"    📚 {i}. {rec['title']} ({rec['content_type']})")
                    logger.info(f"       Relevance: {rec['relevance_score']:.2f}")
                    if rec.get("entity_matches"):
                        logger.info(f"       Matching interests: {', '.join(rec['entity_matches'])}")
            else:
                logger.warning("  ⚠️ No recommendations found")
            
            return recommendations
        except httpx.HTTPError as e:
            logger.error(f"  ❌ Failed to get recommendations: {str(e)}")
            return []
    
    async def semantic_search(self, query: str, user_id: str) -> Dict[str, Any]:
        """Perform a semantic search with user context.
        
        Args:
            query: Search query
            user_id: User ID for personalization
            
        Returns:
            Search results
        """
        logger.info(f"⚡ Step 6: Performing semantic search for: '{query}'")
        
        try:
            response = await self.http_client.post(
                f"{self.config['personalization_url']}/search",
                json={
                    "query": query,
                    "user_id": user_id,
                    "personalization_weight": 0.3
                }
            )
            response.raise_for_status()
            results = response.json()
            
            if results["items"]:
                logger.info(f"  ✅ Found {results['total']} search results")
                for i, item in enumerate(results["items"][:5], 1):
                    logger.info(f"    🔍 {i}. {item['title']} ({item['content_type']})")
                    logger.info(f"       Relevance: {item['relevance_score']:.2f}")
            else:
                logger.warning("  ⚠️ No search results found")
            
            return results
        except httpx.HTTPError as e:
            logger.error(f"  ❌ Failed to perform search: {str(e)}")
            return {"items": [], "total": 0, "query": query}
    
    async def run_complete_workflow(self):
        """Run the complete end-to-end workflow."""
        logger.info("🚀 Starting Chimera Platform End-to-End Workflow")
        logger.info("===============================================")
        
        try:
            # 1. Ingest sample content
            content_ids = await self.ingest_sample_content()
            if not content_ids:
                logger.error("❌ Workflow failed: No content was ingested")
                return False
            
            # 2. Monitor ML processing
            ml_success = await self.monitor_ml_processing(content_ids)
            
            # 3. Verify Knowledge Graph enrichment
            content_entities = await self.verify_knowledge_graph(content_ids)
            
            # 4. Create user profile
            user_id = await self.create_user_profile()
            
            # 5. Get personalized recommendations
            recommendations = await self.get_personalized_recommendations(user_id)
            
            # 6. Perform semantic search
            search_results = await self.semantic_search("neural networks GPU optimization", user_id)
            
            # Workflow summary
            logger.info("===============================================")
            logger.info("📊 Workflow Summary:")
            logger.info(f"  📥 Content Ingested: {len(content_ids)}")
            logger.info(f"  🔄 ML Processing: {'Successful' if ml_success else 'Incomplete'}")
            
            entity_count = sum(len(entities) for entities in content_entities.values())
            logger.info(f"  📊 Knowledge Graph Entities: {entity_count}")
            
            logger.info(f"  👤 User Profile: {user_id}")
            logger.info(f"  📚 Recommendations: {len(recommendations)}")
            logger.info(f"  🔍 Search Results: {search_results['total']}")
            
            logger.info("===============================================")
            logger.info("✅ End-to-End Workflow Complete")
            
            return True
        except Exception as e:
            logger.error(f"❌ Unexpected error in workflow: {str(e)}")
            return False
        finally:
            await self.close()

async def main():
    """Main entry point for the workflow script."""
    parser = argparse.ArgumentParser(description="Chimera Platform End-to-End Workflow")
    parser.add_argument("--config", type=str, help="Path to configuration file")
    args = parser.parse_args()
    
    # Load configuration
    config = DEFAULT_CONFIG.copy()
    if args.config:
        try:
            with open(args.config, "r") as f:
                config.update(json.load(f))
        except (IOError, json.JSONDecodeError) as e:
            logger.error(f"Error loading configuration file: {str(e)}")
            sys.exit(1)
    
    # Run workflow
    workflow = ChimeraWorkflow(config)
    success = await workflow.run_complete_workflow()
    
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
