#!/bin/bash
# Chimera Platform Integration Test Runner
# Usage: ./run_integration_tests.sh [--mode=full|service|interservice|e2e] [--docker] [--env=ENV_FILE]

set -e

# Default values
MODE="full"
USE_DOCKER=0
ENV_FILE=""
PROJECT_ROOT=$(cd "$(dirname "$0")/.." && pwd)
TESTS_DIR="$PROJECT_ROOT/tests/integration"
DOCKER_COMPOSE_FILE="$TESTS_DIR/docker-compose.test.yml"

# Process arguments
for arg in "$@"; do
  case $arg in
    --mode=*)
      MODE="${arg#*=}"
      ;;
    --docker)
      USE_DOCKER=1
      ;;
    --env=*)
      ENV_FILE="${arg#*=}"
      ;;
    --help)
      echo "Chimera Platform Integration Test Runner"
      echo ""
      echo "Usage: ./run_integration_tests.sh [OPTIONS]"
      echo ""
      echo "Options:"
      echo "  --mode=MODE    Test mode to run (full, service, interservice, e2e)"
      echo "                 full: Run all tests"
      echo "                 service: Test individual services"
      echo "                 interservice: Test communication between services"
      echo "                 e2e: End-to-end workflow tests"
      echo "  --docker       Run tests in Docker containers"
      echo "  --env=FILE     Environment file to use"
      echo "  --help         Show this help message"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg"
      echo "Use --help for usage information"
      exit 1
      ;;
  esac
done

# Validation
if [[ "$MODE" != "full" && "$MODE" != "service" && "$MODE" != "interservice" && "$MODE" != "e2e" ]]; then
  echo "Error: Invalid mode '$MODE'"
  echo "Valid modes: full, service, interservice, e2e"
  exit 1
fi

if [[ -n "$ENV_FILE" && ! -f "$ENV_FILE" ]]; then
  echo "Error: Environment file '$ENV_FILE' not found"
  exit 1
fi

# Determine test files to run based on mode
case $MODE in
  full)
    TEST_FILES="$TESTS_DIR"
    ;;
  service)
    TEST_FILES="$TESTS_DIR/test_service_*.py"
    ;;
  interservice)
    TEST_FILES="$TESTS_DIR/test_inter_service_comm.py"
    ;;
  e2e)
    TEST_FILES="$TESTS_DIR/test_e2e_flows.py"
    ;;
esac

# Print test configuration
echo "🚀 Running Chimera Platform Integration Tests"
echo "============================================"
echo "Mode:      $MODE"
echo "Docker:    $([ $USE_DOCKER -eq 1 ] && echo 'Yes' || echo 'No')"
if [[ -n "$ENV_FILE" ]]; then
  echo "Env File:  $ENV_FILE"
fi
echo "Tests:     $TEST_FILES"
echo "============================================"

# Set up environment if needed
if [[ -n "$ENV_FILE" ]]; then
  echo "📝 Loading environment variables from $ENV_FILE"
  export $(grep -v '^#' "$ENV_FILE" | xargs)
fi

# Function to run tests directly
run_local_tests() {
  echo "🧪 Running tests locally..."
  
  # Check if Python virtual environment exists, create if needed
  if [[ ! -d "$PROJECT_ROOT/venv" ]]; then
    echo "📦 Creating Python virtual environment..."
    python3 -m venv "$PROJECT_ROOT/venv"
    "$PROJECT_ROOT/venv/bin/pip" install -r "$TESTS_DIR/requirements.txt"
  fi
  
  # Activate virtual environment and run tests
  source "$PROJECT_ROOT/venv/bin/activate"
  python -m pytest $TEST_FILES -v --no-header
  
  return $?
}

# Function to run tests in Docker
run_docker_tests() {
  echo "🐳 Running tests in Docker..."
  
  # Make sure Docker is running
  if ! docker info &>/dev/null; then
    echo "❌ Error: Docker is not running or not accessible"
    exit 1
  fi
  
  # Build the test Docker image
  echo "🔨 Building test Docker image..."
  docker build -t chimera-integration-test -f "$TESTS_DIR/Dockerfile.test" "$TESTS_DIR"
  
  # Run the tests with Docker Compose
  echo "🚀 Starting test environment..."
  if [[ -n "$ENV_FILE" ]]; then
    docker-compose -f "$DOCKER_COMPOSE_FILE" --env-file "$ENV_FILE" up -d
  else
    docker-compose -f "$DOCKER_COMPOSE_FILE" up -d
  fi
  
  echo "⏳ Waiting for services to be ready..."
  sleep 10
  
  # Run the actual tests
  if [[ "$MODE" == "full" ]]; then
    docker-compose -f "$DOCKER_COMPOSE_FILE" exec test-runner pytest -xvs
  else
    docker-compose -f "$DOCKER_COMPOSE_FILE" exec test-runner pytest -xvs $TEST_FILES
  fi
  
  TEST_EXIT_CODE=$?
  
  # Clean up
  echo "🧹 Cleaning up Docker containers..."
  docker-compose -f "$DOCKER_COMPOSE_FILE" down
  
  return $TEST_EXIT_CODE
}

# Run tests based on configuration
if [[ $USE_DOCKER -eq 1 ]]; then
  run_docker_tests
else
  run_local_tests
fi

# Get exit code from test run
TEST_EXIT_CODE=$?

# Final output
echo "============================================"
if [[ $TEST_EXIT_CODE -eq 0 ]]; then
  echo "✅ All tests passed!"
else
  echo "❌ Tests failed with exit code $TEST_EXIT_CODE"
fi

exit $TEST_EXIT_CODE
