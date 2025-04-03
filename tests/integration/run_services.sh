#!/bin/bash
set -e

# Colors for terminal output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting core infrastructure services...${NC}"
docker-compose -f docker-compose.test.yml up -d nats redis neo4j mock-triton

# Wait for services to be ready
echo -e "${YELLOW}Waiting for infrastructure services to be ready...${NC}"
sleep 10

# Set environment variables for local testing
export NATS_URL="nats://nats_test:password@localhost:14222"
export REDIS_URL="redis://localhost:16379"
export NEO4J_URI="bolt://localhost:17687"
export NEO4J_USER="neo4j"
export NEO4J_PASSWORD="testpassword"
export INGESTION_URL="http://localhost:18001"
export ML_ORCHESTRATOR_URL="http://localhost:18002"
export KNOWLEDGE_GRAPH_URL="http://localhost:18003"
export PERSONALIZATION_URL="http://localhost:18004"
export TRITON_URL="http://localhost:18000"

echo -e "${GREEN}Environment variables set:${NC}"
echo "NATS_URL=$NATS_URL"
echo "REDIS_URL=$REDIS_URL"
echo "NEO4J_URI=$NEO4J_URI"
echo "INGESTION_URL=$INGESTION_URL"
echo "ML_ORCHESTRATOR_URL=$ML_ORCHESTRATOR_URL"
echo "KNOWLEDGE_GRAPH_URL=$KNOWLEDGE_GRAPH_URL"
echo "PERSONALIZATION_URL=$PERSONALIZATION_URL"
echo "TRITON_URL=$TRITON_URL"

# Run the tests
echo -e "${GREEN}Running integration tests...${NC}"
pytest -xvs "$@"

# Cleanup
echo -e "${GREEN}Stopping services...${NC}"
docker-compose -f docker-compose.test.yml down
