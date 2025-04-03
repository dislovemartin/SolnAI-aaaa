# SolnAI Optimized Configuration

This document outlines the optimized configuration for the SolnAI platform, including best practices and performance enhancements.

## Key Improvements

### 1. Docker Compose Enhancements

- **Specific Image Tagging**: Changed from floating `:latest` tags to specific version tags for reproducible builds
- **Custom Network**: Added a defined bridge network for better service isolation
- **Health Checks**: Implemented health checks for all services to ensure proper startup sequence
- **Environment Variables**: Moved sensitive data to environment variables with sane defaults
- **Dependency Management**: Improved service dependency resolution with condition-based dependencies
- **Observability**: Added Prometheus and Grafana for monitoring
- **Volume Management**: Enhanced volume definitions and added persistent cache for NIM models

### 2. Redis Optimization

- Created a dedicated configuration file (`infrastructure/redis/redis.conf`) with:
  - Memory limits and policies (2GB max, volatile-lru eviction)
  - Persistence configuration (AOF enabled with everysec sync)
  - Performance tuning for connection handling and memory usage
  - Security settings

### 3. Triton Server Performance

- Added a dedicated configuration file (`infrastructure/triton/triton.conf`) with:
  - Optimized HTTP/REST and gRPC settings
  - Cache configuration for faster inference
  - Model repository and polling settings
  - GPU memory allocation settings
  - Logging configuration

### 4. Service Resilience

- **Auto-recovery**: Added automatic service health monitoring and restart capability
- **Graceful Shutdown**: Improved shutdown sequence with proper waiting periods
- **Resource Limits**: Configured appropriate resource limits for Neo4j and other services

### 5. Security Improvements

- **Environment Variable Management**: Added `.env` file for sensitive configuration
- **Redis Password**: Added configurable Redis password
- **Read-Only Mounts**: Changed application code mount to read-only for security
- **Enterprise Neo4j**: Upgraded to Neo4j Enterprise with enhanced security features

## Configuration Files

1. **docker-compose.yml**: Main orchestration configuration
2. **infrastructure/redis/redis.conf**: Redis server optimization
3. **infrastructure/triton/triton.conf**: Triton server performance settings
4. **.env**: Environment variable configuration (rename .env.example to .env)
5. **scripts/start.sh**: Updated startup script with resilience features

## Usage Instructions

1. Configure environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your settings
   nano .env
   ```

2. Start the optimized stack:
   ```bash
   docker-compose up -d
   ```

3. Monitor performance:
   - Access Grafana dashboard at http://localhost:3000 (admin/admin)
   - View Triton metrics at http://localhost:8002/metrics
   - Check NATS monitoring at http://localhost:8222

## Performance Tuning

For further optimization based on your specific hardware:

1. **GPU Settings**: Adjust `GPU_MEMORY_FRACTION` in `.env` based on your specific GPU model
2. **Neo4j Memory**: Modify Neo4j memory settings in `docker-compose.yml` based on available RAM
3. **Triton Cache**: Adjust cache sizes in `infrastructure/triton/triton.conf` based on your workload
4. **Redis Memory**: Configure Redis memory limits in `infrastructure/redis/redis.conf`

## Security Notes

1. Always change default passwords in `.env` before deployment
2. Consider setting up a reverse proxy with TLS for production deployments
3. Restrict access to management ports (8222, 3000, etc.) in production 