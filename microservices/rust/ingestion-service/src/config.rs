use std::env;
use tracing::warn;

/// Application configuration loaded from environment variables
#[derive(Debug, Clone)]
pub struct AppConfig {
    /// Port to listen on
    pub port: u16,
    
    /// NATS server URL
    pub nats_url: String,
    
    /// Environment name (development, staging, production)
    pub environment: String,
}

impl AppConfig {
    /// Load configuration from environment variables with defaults
    pub fn from_env() -> Self {
        let port = env::var("PORT")
            .ok()
            .and_then(|s| s.parse::<u16>().ok())
            .unwrap_or_else(|| {
                warn!("PORT environment variable not set or invalid, using default port 3000");
                3000
            });
            
        let nats_url = env::var("NATS_URL")
            .unwrap_or_else(|_| {
                warn!("NATS_URL environment variable not set, using default nats://localhost:4222");
                "nats://localhost:4222".to_string()
            });
            
        let environment = env::var("ENVIRONMENT")
            .unwrap_or_else(|_| {
                warn!("ENVIRONMENT environment variable not set, using default development");
                "development".to_string()
            });
            
        Self {
            port,
            nats_url,
            environment,
        }
    }
}
