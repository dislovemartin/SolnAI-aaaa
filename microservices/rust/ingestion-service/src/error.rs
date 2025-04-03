use axum::{
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::json;
use thiserror::Error;

/// Custom error types for the ingestion service
#[derive(Error, Debug)]
pub enum AppError {
    #[error("Failed to connect to NATS: {0}")]
    NatsConnectionError(String),
    
    #[error("Failed to publish message to NATS: {0}")]
    NatsPublishError(String),
    
    #[error("Invalid input data: {0}")]
    ValidationError(String),
    
    #[error("Internal server error: {0}")]
    InternalError(String),
}

/// Convert application errors into appropriate HTTP responses
impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        let (status, error_message) = match self {
            AppError::NatsConnectionError(msg) => (
                StatusCode::SERVICE_UNAVAILABLE,
                msg,
            ),
            AppError::NatsPublishError(msg) => (
                StatusCode::INTERNAL_SERVER_ERROR,
                msg,
            ),
            AppError::ValidationError(msg) => (
                StatusCode::BAD_REQUEST,
                msg,
            ),
            AppError::InternalError(msg) => (
                StatusCode::INTERNAL_SERVER_ERROR,
                msg,
            ),
        };

        let body = Json(json!({
            "error": {
                "message": error_message,
                "code": status.as_u16()
            }
        }));

        (status, body).into_response()
    }
}

/// Helper type for Result with AppError as error type
pub type Result<T> = std::result::Result<T, AppError>;
