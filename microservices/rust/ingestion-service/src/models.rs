use serde::{Deserialize, Serialize};
use chrono::{DateTime, Utc};
use uuid::Uuid;

/// Represents raw data ingested into the system from various sources
#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct RawData {
    /// Unique identifier for the data item
    #[serde(default = "Uuid::new_v4")]
    pub id: Uuid,
    
    /// Source of the data (e.g., "arxiv", "github", "news-api")
    pub source: String,
    
    /// Type of content (e.g., "research_paper", "code_repository", "news_article")
    pub content_type: String,
    
    /// The actual data payload, represented as arbitrary JSON
    pub payload: serde_json::Value,
    
    /// Timestamp when the data was ingested, defaults to current time
    #[serde(default = "Utc::now")]
    pub timestamp: DateTime<Utc>,
    
    /// Optional metadata about the data
    #[serde(default)]
    pub metadata: serde_json::Value,
}

/// Batch of raw data items to be ingested
#[derive(Debug, Serialize, Deserialize)]
pub struct BatchRawData {
    /// Collection of data items to ingest
    pub items: Vec<RawData>,
}

/// Response for successful ingestion
#[derive(Debug, Serialize, Deserialize)]
pub struct IngestResponse {
    /// Status of the operation
    pub status: String,
    
    /// ID of the ingested data item
    pub id: Uuid,
    
    /// Timestamp when the data was ingested
    pub timestamp: DateTime<Utc>,
}

/// Response for batch ingestion
#[derive(Debug, Serialize, Deserialize)]
pub struct BatchIngestResponse {
    /// Status of the operation
    pub status: String,
    
    /// Number of items successfully ingested
    pub count: usize,
    
    /// IDs of the ingested data items
    pub ids: Vec<Uuid>,
    
    /// Timestamp when the batch was processed
    pub timestamp: DateTime<Utc>,
}

/// Health check response
#[derive(Debug, Serialize, Deserialize)]
pub struct HealthResponse {
    /// Service name
    pub service: String,
    
    /// Service status
    pub status: String,
    
    /// Service version
    pub version: String,
    
    /// Timestamp of the health check
    pub timestamp: DateTime<Utc>,
}
