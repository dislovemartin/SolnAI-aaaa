from contextlib import asynccontextmanager
from typing import Dict, List, Optional, Any, Union
import asyncio
import json
import os
from uuid import uuid4

import numpy as np
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from loguru import logger
import nats
from nats.js.api import StreamConfig, ConsumerConfig
import tritonclient.http as httpclient
from tritonclient.utils import InferenceServerException

from app.config import Settings, get_settings
from app.models import (
    ProcessRequest, 
    TextSummarizationRequest, 
    EntityExtractionRequest, 
    ProcessResponse,
    HealthResponse
)
from app.triton import TritonClient
from app.nats_client import NatsClient

# Global clients
triton_client: Optional[TritonClient] = None
nats_client: Optional[NatsClient] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    global triton_client, nats_client
    settings = get_settings()
    
    # Initialize Triton client
    logger.info(f"Connecting to Triton at {settings.triton_url}")
    triton_client = TritonClient(settings.triton_url)
    await triton_client.connect()
    
    # Initialize NATS client
    logger.info(f"Connecting to NATS at {settings.nats_url}")
    nats_client = NatsClient(settings.nats_url)
    await nats_client.connect()
    
    # Initialize NATS streams and consumers
    if nats_client.js:
        try:
            # Create streams if they don't exist
            stream_config = StreamConfig(
                name="NLP_PROCESSING",
                subjects=["ingest.validated.*", "nlp.request.*", "nlp.enriched.*"],
                storage="file",
                retention="limits",
                max_msgs=10_000_000,
                max_bytes=10_000_000_000,
                discard="old",
                max_age=86400_000_000_000,  # 1 day in nanoseconds
            )
            await nats_client.js.add_stream(stream_config)
            logger.info("NLP_PROCESSING stream configured")
            
            # Set up consumers
            for subject in ["ingest.validated.*"]:
                consumer_config = ConsumerConfig(
                    durable_name=f"ml-orchestrator-{subject.replace('*', 'all').replace('.', '-')}",
                    ack_policy="explicit",
                    max_deliver=5,
                    ack_wait=60_000_000_000,  # 60 seconds in nanoseconds
                )
                await nats_client.js.add_consumer("NLP_PROCESSING", consumer_config)
            
            logger.info("NATS consumers configured")
        except Exception as e:
            logger.error(f"Failed to configure NATS streams/consumers: {e}")
    
    # Start background processors
    asyncio.create_task(process_validated_messages())
    
    logger.info("ML Orchestrator service started")
    
    yield
    
    # Cleanup
    if nats_client:
        await nats_client.close()
        logger.info("NATS connection closed")
    
    if triton_client:
        await triton_client.close()
        logger.info("Triton connection closed")
    
    logger.info("ML Orchestrator service shutdown")

app = FastAPI(
    title="Chimera ML Orchestrator Service",
    description="Orchestrates NLP processing tasks using Triton Inference Server",
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

async def process_validated_messages():
    """Background task to process validated messages from NATS."""
    if not nats_client or not nats_client.js:
        logger.error("NATS client not initialized")
        return
    
    logger.info("Starting background processor for validated messages")
    
    while True:
        try:
            sub = await nats_client.js.pull_subscribe(
                "ingest.validated.*", 
                "ml-orchestrator-ingest-validated-all"
            )
            
            while True:
                try:
                    msgs = await sub.fetch(10, timeout=1)
                    for msg in msgs:
                        try:
                            data = json.loads(msg.data.decode())
                            logger.info(f"Processing message: {data['id']}")
                            
                            # Check content type to determine processing pipeline
                            content_type = data.get("content_type", "")
                            
                            if "research_paper" in content_type or "news_article" in content_type:
                                # For text content, extract text and run summarization + entity extraction
                                if text_content := data.get("payload", {}).get("text", ""):
                                    # Process with Triton
                                    result = await process_text_content(text_content, data["id"])
                                    
                                    # Publish enriched data
                                    enriched_data = {
                                        **data,
                                        "nlp_enrichment": result,
                                    }
                                    
                                    await nats_client.publish(
                                        f"nlp.enriched.{content_type}", 
                                        json.dumps(enriched_data)
                                    )
                                    logger.info(f"Published enriched data for {data['id']}")
                            
                            await msg.ack()
                        except Exception as e:
                            logger.error(f"Error processing message: {e}")
                            await msg.nak(delay=5)
                
                except Exception as e:
                    if "timeout" not in str(e).lower():
                        logger.error(f"Error fetching messages: {e}")
                    await asyncio.sleep(1)
        
        except Exception as e:
            logger.error(f"Subscription error: {e}")
            await asyncio.sleep(5)  # Wait before reconnecting

async def process_text_content(text: str, request_id: str) -> Dict[str, Any]:
    """Process text content through Triton models."""
    if not triton_client:
        raise RuntimeError("Triton client not initialized")
    
    # Run summarization
    summary = await triton_client.run_summarization(text)
    
    # Run entity extraction
    entities = await triton_client.run_entity_extraction(text)
    
    return {
        "summary": summary,
        "entities": entities,
        "processed_at": str(np.datetime64('now')),
    }

@app.get("/health")
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    triton_healthy = triton_client and await triton_client.is_healthy()
    nats_healthy = nats_client and nats_client.is_connected()
    
    return HealthResponse(
        service="ml-orchestrator",
        status="healthy" if (triton_healthy and nats_healthy) else "degraded",
        components={
            "triton": "connected" if triton_healthy else "disconnected",
            "nats": "connected" if nats_healthy else "disconnected",
        },
        version="0.1.0"
    )

@app.post("/process", response_model=ProcessResponse)
async def process_data(
    request: ProcessRequest,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings)
) -> ProcessResponse:
    """Generic endpoint to process data through various NLP pipelines."""
    if not triton_client:
        raise HTTPException(500, "Triton client not initialized")
    
    request_id = request.request_id or str(uuid4())
    logger.info(f"Processing request {request_id}")
    
    try:
        result = {}
        
        # Process text summarization if requested
        if request.text_content:
            # If immediate is True, process synchronously
            if request.immediate:
                result["summary"] = await triton_client.run_summarization(request.text_content)
                
                if request.extract_entities:
                    result["entities"] = await triton_client.run_entity_extraction(request.text_content)
            else:
                # Queue for asynchronous processing
                await nats_client.publish(
                    "nlp.request.process",
                    json.dumps({
                        "request_id": request_id,
                        "text_content": request.text_content,
                        "extract_entities": request.extract_entities,
                        "timestamp": str(np.datetime64('now')),
                    })
                )
                result["status"] = "queued"
        
        return ProcessResponse(
            request_id=request_id,
            status="completed" if request.immediate else "queued",
            result=result
        )
    
    except Exception as e:
        logger.error(f"Error processing request: {e}")
        raise HTTPException(500, f"Processing error: {str(e)}")

@app.post("/summarize", response_model=ProcessResponse)
async def summarize_text(request: TextSummarizationRequest) -> ProcessResponse:
    """Endpoint to summarize text."""
    if not triton_client:
        raise HTTPException(500, "Triton client not initialized")
    
    request_id = request.request_id or str(uuid4())
    
    try:
        summary = await triton_client.run_summarization(
            request.text,
            max_length=request.max_length or 150,
            min_length=request.min_length or 50,
        )
        
        return ProcessResponse(
            request_id=request_id,
            status="completed",
            result={"summary": summary}
        )
    
    except Exception as e:
        logger.error(f"Summarization error: {e}")
        raise HTTPException(500, f"Summarization error: {str(e)}")

@app.post("/extract_entities", response_model=ProcessResponse)
async def extract_entities(request: EntityExtractionRequest) -> ProcessResponse:
    """Endpoint to extract entities from text."""
    if not triton_client:
        raise HTTPException(500, "Triton client not initialized")
    
    request_id = request.request_id or str(uuid4())
    
    try:
        entities = await triton_client.run_entity_extraction(
            request.text,
            confidence_threshold=request.confidence_threshold or 0.5,
        )
        
        return ProcessResponse(
            request_id=request_id,
            status="completed",
            result={"entities": entities}
        )
    
    except Exception as e:
        logger.error(f"Entity extraction error: {e}")
        raise HTTPException(500, f"Entity extraction error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")
    
    uvicorn.run("app.main:app", host=host, port=port, reload=True)
