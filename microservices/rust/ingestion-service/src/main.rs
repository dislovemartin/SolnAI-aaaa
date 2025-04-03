mod models;
mod error;
mod nats;
mod routes;
mod config;

use std::sync::Arc;
use axum::{
    routing::{post, get},
    Router,
    extract::Extension,
    http::{HeaderValue, Method},
};
use tower_http::{
    trace::TraceLayer,
    cors::{CorsLayer, Any},
};
use tracing::{info, Level};
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};

use crate::config::AppConfig;
use crate::nats::NatsClient;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Initialize tracing
    tracing_subscriber::registry()
        .with(tracing_subscriber::EnvFilter::new(
            std::env::var("RUST_LOG").unwrap_or_else(|_| "info,tower_http=debug".into()),
        ))
        .with(tracing_subscriber::fmt::layer())
        .init();

    info!("Initializing Chimera Ingestion Service");
    
    // Load configuration
    let config = AppConfig::from_env();
    info!("Loaded configuration: {:#?}", config);

    // Initialize NATS connection
    let nats_client = NatsClient::new(&config.nats_url).await?;
    let nats_client = Arc::new(nats_client);

    // Build our application with a route
    let app = Router::new()
        .route("/health", get(routes::health_check))
        .route("/ingest", post(routes::ingest_data))
        .route("/ingest/batch", post(routes::ingest_batch))
        // Add middleware
        .layer(
            CorsLayer::new()
                .allow_origin(Any)
                .allow_methods([Method::GET, Method::POST])
                .allow_headers(Any)
        )
        .layer(TraceLayer::new_for_http())
        .layer(Extension(nats_client));

    // Run our app
    let addr = format!("0.0.0.0:{}", config.port);
    let listener = tokio::net::TcpListener::bind(&addr).await?;
    info!("Ingestion service listening on {}", addr);
    
    axum::serve(listener, app).await?;
    
    Ok(())
}
