# Personalization Engine

A microservice that manages user profiles and content recommendations using vector embeddings for semantic search and personalized content delivery.

## Features

- User profile management with interest tracking
- Vector-based content recommendations
- Semantic search capabilities
- Automatic content vectorization from NLP-enriched data
- Real-time personalization based on user activity
- Integration with NATS for event streaming
- Redis-backed vector database for fast similarity search

## Components

- **Vector Store**: Redis-backed vector database for embeddings
- **NATS Client**: Handles message streaming for content updates
- **User Profile Manager**: Tracks and updates user preferences
- **Recommendation Engine**: Generates personalized content recommendations
- **FastAPI Server**: Provides REST API endpoints

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check endpoint |
| `/users` | POST | Create a new user profile |
| `/users/{user_id}` | GET | Get user profile by ID |
| `/users/{user_id}` | PUT | Update user profile |
| `/users/{user_id}` | DELETE | Delete user profile |
| `/recommendations/{user_id}` | GET | Get personalized recommendations |
| `/search` | POST | Perform semantic search |
| `/vectorize` | POST | Manually vectorize content |
| `/users/{user_id}/activity` | POST | Update user activity |

## Message Processing

The service subscribes to the `nlp.enriched.*` NATS subject to automatically process and vectorize new content:

1. Receives NLP-enriched content from the ML Orchestrator
2. Extracts text, summaries, and metadata
3. Generates vector embeddings for the content
4. Stores embeddings in the vector database with metadata
5. Updates recommendations based on new content

## Vector Store

The vector store component:

- Uses Redis as the backend database
- Supports approximate nearest neighbor (ANN) search
- Enables efficient storage and retrieval of high-dimensional vectors
- Handles metadata storage alongside vectors
- Provides filtering capabilities for recommendation generation

## User Profiles

User profiles include:

- Basic user information
- Interest vectors (derived from content interactions)
- Explicit preferences (topics, sources, etc.)
- Interaction history
- Recommendation history to prevent duplicates

## Requirements

- Python a3.8+
- Redis Stack 6.2+ (with RediSearch and RedisJSON modules)
- NATS Server 2.2+
- Dependencies listed in `requirements.txt`

## Installation

```bash
pip install -r requirements.txt
```

## Configuration

The service is configured using environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `REDIS_URL` | URL for Redis connection | `redis://localhost:6379` |
| `NATS_URL` | URL for NATS connection | `nats://localhost:4222` |
| `NATS_USER` | NATS username | - |
| `NATS_PASSWORD` | NATS password | - |
| `EMBEDDING_MODEL` | Name of embedding model | `text-embedding-3-small` |
| `EMBEDDING_DIMENSION` | Dimension of embeddings | `1536` |
| `LOG_LEVEL` | Logging level | `info` |

## Usage

### Running Locally

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Using Docker

```bash
docker build -t personalization-engine .
docker run -p 8000:8000 personalization-engine
```

## Recommendation Algorithm

The recommendation engine uses a multi-step algorithm:

1. **User Interest Representation**:
   - Computes the user's interest vector from content interactions
   - Weighs recent interactions more heavily
   - Incorporates explicit preferences

2. **Candidate Generation**:
   - Uses vector similarity search to find content similar to user interests
   - Includes diversity mechanisms to avoid recommendation bubbles
   - Filters out previously seen content

3. **Ranking**:
   - Ranks candidates based on similarity, recency, and popularity
   - Applies personalized weighting based on user behavior
   - Supports customizable ranking strategies

## Semantic Search

The semantic search feature:

- Converts natural language queries to vectors
- Finds semantically similar content regardless of exact keyword matches
- Supports filtering by metadata (date, source, type, etc.)
- Returns ranked results with relevance scores

## Example Usage

### Get Recommendations

```bash
curl -X GET "http://localhost:8000/recommendations/user123?limit=10&content_type=research_paper"
```

### Semantic Search

```bash
curl -X POST "http://localhost:8000/search" \
     -H "Content-Type: application/json" \
     -d '{"query": "advances in natural language processing", "limit": 5}'
```

## Performance Considerations

- Vector operations are computationally intensive
- The service is designed for horizontal scaling
- Redis persistence should be configured for production use
- Consider using a dedicated Redis instance for vector storage

## Contributing

Contributions are welcome! Please ensure your code follows the project's style guidelines and includes appropriate tests. 