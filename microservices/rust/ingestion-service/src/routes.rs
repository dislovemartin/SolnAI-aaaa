use axum::{
    extract::{Json, Extension},
    http::StatusCode,
};
use chrono::Utc;
use tracing::{info, warn, error, instrument};
use std::sync::Arc;

use crate::models::{RawData, BatchRawData, IngestResponse, BatchIngestResponse, HealthResponse};
use crate::nats::NatsClient;
use crate::error::{Result, AppError};

/// Health check endpoint
#[instrument(skip_all)]
pub async fn health_check() -> Json<HealthResponse> {
    let response = HealthResponse {
        service: "ingestion-service".to_string(),
        status: "operational".to_string(),
        version: env!("CARGO_PKG_VERSION").to_string(),
        timestamp: Utc::now(),
    };
    
    Json(response)
}

/// Ingest a single data item
#[instrument(skip(nats_client, payload), fields(source = %payload.source, content_type = %payload.content_type))]
pub async fn ingest_data(
    Extension(nats_client): Extension<Arc<NatsClient>>,
    Json(payload): Json<RawData>,
) -> Result<(StatusCode, Json<IngestResponse>)> {
    info!("Processing ingestion request: id={}", payload.id);
    
    // Validate input
    if payload.source.is_empty() {
        warn!("Empty source field in ingestion request");
        return Err(AppError::ValidationError("Source field cannot be empty".to_string()));
    }
    
    if payload.content_type.is_empty() {
        warn!("Empty content_type field in ingestion request");
        return Err(AppError::ValidationError("Content type field cannot be empty".to_string()));
    }
    
    if payload.payload.is_null() {
        warn!("Empty payload in ingestion request");
        return Err(AppError::ValidationError("Payload cannot be null".to_string()));
    }
    
    // Determine the appropriate NATS subject based on content type
    let subject = format!("ingest.raw.{}", payload.content_type);
    
    // Publish to NATS
    nats_client.publish(&subject, &payload).await?;
    
    // Create response
    let response = IngestResponse {
        status: "success".to_string(),
        id: payload.id,
        timestamp: Utc::now(),
    };
    
    info!("Successfully ingested data with id: {}", payload.id);
    
    Ok((StatusCode::CREATED, Json(response)))
}

/// Batch ingest multiple data items
#[instrument(skip(nats_client, payload), fields(item_count = %payload.items.len()))]
pub async fn ingest_batch(
    Extension(nats_client): Extension<Arc<NatsClient>>,
    Json(payload): Json<BatchRawData>,
) -> Result<(StatusCode, Json<BatchIngestResponse>)> {
    info!("Processing batch ingestion request with {} items", payload.items.len());
    
    if payload.items.is_empty() {
        warn!("Empty batch in ingestion request");
        return Err(AppError::ValidationError("Batch contains no items".to_string()));
    }
    
    let mut successful_ids = Vec::with_capacity(payload.items.len());
    
    // Process each item
    for item in payload.items.iter() {
        // Validate item
        if item.source.is_empty() || item.content_type.is_empty() || item.payload.is_null() {
            error!("Invalid item in batch, id: {}", item.id);
            continue;
        }
        
        // Determine subject
        let subject = format!("ingest.raw.{}", item.content_type);
        
        // Publish to NATS
        match nats_client.publish(&subject, item).await {
            Ok(_) => {
                successful_ids.push(item.id);
                info!("Successfully published item {}", item.id);
            },
            Err(e) => {
                error!("Failed to publish item {}: {}", item.id, e);
                // Continue processing other items even if one fails
            }
        }
    }
    
    // Create response
    let response = BatchIngestResponse {
        status: "success".to_string(),
        count: successful_ids.len(),
        ids: successful_ids,
        timestamp: Utc::now(),
    };
    
    info!("Batch ingestion completed: {}/{} items successful", 
          response.count, payload.items.len());
    
    Ok((StatusCode::CREATED, Json(response)))
}
