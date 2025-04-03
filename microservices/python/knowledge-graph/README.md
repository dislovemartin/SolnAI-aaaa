# Knowledge Graph Service

A microservice that manages a knowledge graph using Neo4j to store entities and relationships extracted from content.

## Features

- Entity and relationship management via REST API
- Graph querying with customizable Cypher queries
- Automatic entity and relationship extraction from NLP-enriched data
- Batch operations for efficient data processing
- Integration with NATS message streaming
- Health monitoring and automatic reconnection

## Components

- **Neo4j Client**: Manages connections and operations with the Neo4j database
- **NATS Client**: Handles messaging for asynchronous processing of enriched data
- **Data Models**: Defines entity and relationship schemas
- **FastAPI Server**: Provides REST API endpoints

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check endpoint |
| `/entities` | POST | Create a new entity |
| `/entities/{id}` | GET | Get entity by ID |
| `/entities/{id}` | DELETE | Delete entity by ID |
| `/relationships` | POST | Create a new relationship |
| `/relationships/{id}` | GET | Get relationship by ID |
| `/relationships/{id}` | DELETE | Delete relationship by ID |
| `/query` | POST | Execute a graph query |
| `/entities/batch` | POST | Batch operation for entities |
| `/relationships/batch` | POST | Batch operation for relationships |

## Message Processing

The service subscribes to the `nlp.enriched.*` NATS subject to automatically process NLP-enriched data:

1. Extracts entities from the enriched data
2. Creates nodes for the source document and identified entities
3. Establishes relationships between entities and documents
4. Updates existing entities with additional metadata when found

## Requirements

- Python 3.8+
- Neo4j 4.4+
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
| `NEO4J_URI` | URI for Neo4j connection | `neo4j://localhost:7687` |
| `NEO4J_USER` | Neo4j username | `neo4j` |
| `NEO4J_PASSWORD` | Neo4j password | `password` |
| `NATS_URL` | URL for NATS connection | `nats://localhost:4222` |
| `NATS_USER` | NATS username | - |
| `NATS_PASSWORD` | NATS password | - |
| `INITIALIZE_SCHEMA` | Whether to initialize schema | `true` |
| `LOG_LEVEL` | Logging level | `info` |

## Usage

### Running Locally

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Using Docker

```bash
docker build -t knowledge-graph-service .
docker run -p 8000:8000 knowledge-graph-service
```

## Schema

The knowledge graph uses the following main node types:

- `Document`: Source documents (papers, articles, etc.)
- `Person`: Individuals mentioned in content
- `Organization`: Companies, institutions, etc.
- `Technology`: Technical concepts, methods, tools
- `Topic`: Subject areas or domains
- `Location`: Geographical locations

Relationships between these entities are typed and can include:

- `MENTIONS`: Document mentions an entity
- `CREATED_BY`: Document created by person/organization
- `BELONGS_TO`: Entity belongs to organization/category
- `RELATED_TO`: General relationship between entities

## Example Queries

### Find connections between technologies

```cypher
MATCH (t1:Technology)-[r*1..3]-(t2:Technology)
WHERE t1.name = 'Machine Learning' AND t2.name = 'Computer Vision'
RETURN t1, r, t2
```

### Find key people in a domain

```cypher
MATCH (p:Person)-[:CREATED_BY|CONTRIBUTED_TO]->(d:Document)-[:CATEGORY]->(t:Topic)
WHERE t.name = 'Artificial Intelligence'
RETURN p.name, count(d) as publications
ORDER BY publications DESC
LIMIT 10
```

## Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Create a pull request 