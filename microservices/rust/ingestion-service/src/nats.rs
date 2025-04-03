use async_nats::Client;
use serde::Serialize;
use tracing::{info, error, instrument};
use crate::error::{AppError, Result};

/// Client wrapper for NATS interactions
pub struct NatsClient {
    client: Client,
}

impl NatsClient {
    /// Create a new NATS client
    pub async fn new(url: &str) -> Result<Self> {
        info!("Connecting to NATS server at {}", url);
        
        let client = async_nats::connect(url)
            .await
            .map_err(|e| {
                error!("Failed to connect to NATS: {}", e);
                AppError::NatsConnectionError(e.to_string())
            })?;
        
        info!("Successfully connected to NATS");
        
        Ok(Self { client })
    }

    /// Publish a message to a NATS subject
    #[instrument(skip(self, payload), fields(subject = %subject))]
    pub async fn publish<T: Serialize>(&self, subject: &str, payload: &T) -> Result<()> {
        let payload = serde_json::to_vec(payload).map_err(|e| {
            error!("JSON serialization error: {}", e);
            AppError::InternalError(format!("JSON serialization error: {}", e))
        })?;
        
        info!("Publishing message to subject: {}", subject);
        
        self.client.publish(subject, payload.into())
            .await
            .map_err(|e| {
                error!("Failed to publish to NATS: {}", e);
                AppError::NatsPublishError(e.to_string())
            })?;
        
        info!("Successfully published message to {}", subject);
        
        Ok(())
    }
}
