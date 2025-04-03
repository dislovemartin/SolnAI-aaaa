FROM rust:1.76-slim as builder

WORKDIR /app

# Create blank project
RUN USER=root cargo new --bin ingestion-service

# Copy manifest
COPY Cargo.toml ./

# Update the Cargo.toml in the dummy project
RUN sed -i 's/name = "ingestion-service"/name = "app"/' ingestion-service/Cargo.toml
COPY src ./src

# Build for release
RUN cargo build --release

# Runtime stage
FROM debian:bookworm-slim

WORKDIR /app

# Install dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Copy the binary from builder
COPY --from=builder /app/target/release/ingestion-service .

# Expose the service port
EXPOSE 8001

# Set environment variables
ENV PORT=8001
ENV RUST_LOG=info

# Run the binary
CMD ["./ingestion-service"]
