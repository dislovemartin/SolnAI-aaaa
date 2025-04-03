from typing import Dict, List, Optional, Any, Union
import asyncio
from loguru import logger
from neo4j import GraphDatabase, basic_auth
from neo4j.exceptions import ServiceUnavailable, DatabaseError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

class Neo4jClient:
    """Client for interacting with Neo4j graph database."""

    def __init__(self, uri: str, user: str, password: str):
        """Initialize the Neo4j client.
        
        Args:
            uri: URI of the Neo4j server (e.g., 'neo4j://localhost:7687')
            user: Username for authentication
            password: Password for authentication
        """
        self.uri = uri
        self.user = user
        self.password = password
        self.driver = None
        self._connected = False
        self._schema_initialized = False

    async def connect(self) -> None:
        """Connect to the Neo4j database."""
        try:
            # Neo4j driver is synchronous, run in executor
            self.driver = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: GraphDatabase.driver(
                    self.uri,
                    auth=basic_auth(self.user, self.password)
                )
            )
            
            # Verify connection
            await self._verify_connectivity()
            self._connected = True
            logger.info(f"Connected to Neo4j at {self.uri}")
            
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            self.driver = None
            self._connected = False
            raise

    async def close(self) -> None:
        """Close the connection to Neo4j."""
        if self.driver:
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.driver.close()
            )
            self.driver = None
            self._connected = False
            logger.info("Neo4j connection closed")

    async def is_healthy(self) -> bool:
        """Check if the Neo4j connection is healthy."""
        if not self.driver:
            return False
            
        try:
            await self._verify_connectivity()
            return True
        except Exception:
            return False

    async def _verify_connectivity(self) -> None:
        """Verify that the connection to Neo4j is working."""
        if not self.driver:
            raise RuntimeError("Neo4j driver not initialized")
            
        try:
            await self.execute_query("RETURN 1 AS num")
        except Exception as e:
            logger.error(f"Neo4j connectivity check failed: {e}")
            raise

    async def initialize_schema(self) -> None:
        """Initialize the Neo4j schema with constraints and indices."""
        if not self.driver or not self._connected:
            raise RuntimeError("Neo4j client not connected")
            
        if self._schema_initialized:
            logger.info("Schema already initialized")
            return
            
        try:
            # Create constraints for uniqueness and faster lookups
            constraints = [
                "CREATE CONSTRAINT unique_paper IF NOT EXISTS FOR (p:Paper) REQUIRE p.id IS UNIQUE",
                "CREATE CONSTRAINT unique_entity IF NOT EXISTS FOR (e:Entity) REQUIRE (e.name, e.type) IS NODE KEY",
                "CREATE CONSTRAINT unique_repo IF NOT EXISTS FOR (r:Repository) REQUIRE r.id IS UNIQUE",
                "CREATE CONSTRAINT unique_company IF NOT EXISTS FOR (c:Company) REQUIRE c.name IS UNIQUE",
                "CREATE CONSTRAINT unique_person IF NOT EXISTS FOR (p:Person) REQUIRE p.name IS UNIQUE"
            ]
            
            # Create indices for common query properties
            indices = [
                "CREATE INDEX paper_title IF NOT EXISTS FOR (p:Paper) ON (p.title)",
                "CREATE INDEX entity_type IF NOT EXISTS FOR (e:Entity) ON (e.type)",
                "CREATE INDEX document_type IF NOT EXISTS FOR (d:Document) ON (d.type)",
                "CREATE INDEX source_type IF NOT EXISTS FOR (s:NewsArticle) ON (s.source)"
            ]
            
            # Execute all schema commands
            for query in constraints + indices:
                await self.execute_query(query)
                
            self._schema_initialized = True
            logger.info("Neo4j schema initialized with constraints and indices")
            
        except Exception as e:
            logger.error(f"Failed to initialize Neo4j schema: {e}")
            raise

    @retry(
        retry=retry_if_exception_type((ServiceUnavailable, DatabaseError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10)
    )
    async def execute_query(self, query: str, params: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """Execute a Cypher query against the Neo4j database.
        
        Args:
            query: Cypher query string
            params: Optional parameters for the query
            
        Returns:
            List of records as dictionaries
        """
        if not self.driver or not self._connected:
            raise RuntimeError("Neo4j client not connected")
            
        params = params or {}
        
        try:
            # Neo4j transaction functions are synchronous, run in executor
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._execute_query_sync(query, params)
            )
            
            return result
            
        except (ServiceUnavailable, DatabaseError) as e:
            logger.error(f"Neo4j query error (retrying): {e}")
            # These errors might be retried by the decorator
            raise
            
        except Exception as e:
            logger.error(f"Neo4j query error: {e}")
            raise RuntimeError(f"Query execution failed: {str(e)}")

    def _execute_query_sync(self, query: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Synchronous execution of a Cypher query (run in executor).
        
        Args:
            query: Cypher query string
            params: Parameters for the query
            
        Returns:
            List of records as dictionaries
        """
        with self.driver.session() as session:
            result = session.run(query, params)
            return [dict(record) for record in result]

    async def create_node(self, labels: List[str], properties: Dict[str, Any]) -> str:
        """Create a new node in the graph.
        
        Args:
            labels: List of node labels
            properties: Node properties
            
        Returns:
            Internal ID of the created node
        """
        labels_str = ':'.join(labels)
        query = f"""
        CREATE (n:{labels_str} $properties)
        RETURN id(n) AS id
        """
        
        result = await self.execute_query(query, {"properties": properties})
        
        if not result:
            raise RuntimeError("Failed to create node")
            
        return result[0]["id"]

    async def merge_node(
        self, 
        labels: List[str], 
        match_properties: Dict[str, Any],
        additional_properties: Dict[str, Any] = None
    ) -> str:
        """Create a node if it doesn't exist, or update an existing node.
        
        Args:
            labels: List of node labels
            match_properties: Properties to match existing nodes
            additional_properties: Additional properties to set if creating a new node
            
        Returns:
            Internal ID of the node
        """
        labels_str = ':'.join(labels)
        
        # Prepare properties: match_properties are used for both matching and setting,
        # additional_properties are only used when creating a new node
        all_properties = {**match_properties}
        if additional_properties:
            all_properties.update(additional_properties)
        
        query = f"""
        MERGE (n:{labels_str} {self._dict_to_properties_string(match_properties)})
        ON CREATE SET n = $all_properties
        RETURN id(n) AS id
        """
        
        result = await self.execute_query(
            query, 
            {
                "all_properties": all_properties
            }
        )
        
        if not result:
            raise RuntimeError("Failed to merge node")
            
        return result[0]["id"]

    def _dict_to_properties_string(self, properties: Dict[str, Any]) -> str:
        """Convert a dictionary to a Cypher properties string.
        
        Args:
            properties: Dictionary of property names and values
            
        Returns:
            Cypher properties string (e.g., "{name: $match_properties.name}")
        """
        props = []
        for key in properties:
            props.append(f"{key}: $match_properties.{key}")
            
        return "{" + ", ".join(props) + "}"

    async def find_node_by_properties(
        self, 
        labels: List[str], 
        properties: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Find a node by its labels and properties.
        
        Args:
            labels: List of node labels
            properties: Properties to match
            
        Returns:
            Node data or None if not found
        """
        labels_str = ':'.join(labels)
        
        # Build a match clause that checks each property
        where_clauses = []
        for key in properties:
            where_clauses.append(f"n.{key} = ${key}")
            
        where_str = " AND ".join(where_clauses)
        
        query = f"""
        MATCH (n:{labels_str})
        WHERE {where_str}
        RETURN id(n) AS id, properties(n) AS properties, labels(n) AS labels
        LIMIT 1
        """
        
        result = await self.execute_query(query, properties)
        
        if not result:
            return None
            
        return result[0]

    async def find_nodes_by_properties(
        self, 
        labels: List[str], 
        properties: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Find all nodes matching labels and properties.
        
        Args:
            labels: List of node labels
            properties: Properties to match
            
        Returns:
            List of matching nodes
        """
        labels_str = ':'.join(labels)
        
        # Build a match clause that checks each property
        where_clauses = []
        for key in properties:
            # Skip None values
            if properties[key] is not None:
                where_clauses.append(f"n.{key} = ${key}")
            
        where_str = " AND ".join(where_clauses) if where_clauses else "1=1"
        
        query = f"""
        MATCH (n:{labels_str})
        WHERE {where_str}
        RETURN id(n) AS id, properties(n) AS properties, labels(n) AS labels
        """
        
        result = await self.execute_query(query, properties)
        return result

    async def update_node(self, node_id: str, properties: Dict[str, Any]) -> None:
        """Update node properties.
        
        Args:
            node_id: Internal ID of the node
            properties: New properties to set
        """
        query = """
        MATCH (n)
        WHERE id(n) = $node_id
        SET n += $properties
        """
        
        await self.execute_query(query, {"node_id": node_id, "properties": properties})

    async def delete_node(self, node_id: str) -> None:
        """Delete a node by its internal ID.
        
        Args:
            node_id: Internal ID of the node
        """
        query = """
        MATCH (n)
        WHERE id(n) = $node_id
        DETACH DELETE n
        """
        
        await self.execute_query(query, {"node_id": node_id})

    async def create_relationship(
        self, 
        start_node_id: str, 
        end_node_id: str, 
        rel_type: str,
        properties: Dict[str, Any] = None
    ) -> str:
        """Create a relationship between two nodes.
        
        Args:
            start_node_id: Internal ID of the start node
            end_node_id: Internal ID of the end node
            rel_type: Type of relationship
            properties: Relationship properties
            
        Returns:
            Internal ID of the created relationship
        """
        properties = properties or {}
        
        query = """
        MATCH (a), (b)
        WHERE id(a) = $start_id AND id(b) = $end_id
        CREATE (a)-[r:`{}`]->(b)
        SET r = $properties
        RETURN id(r) AS id
        """.format(rel_type)
        
        result = await self.execute_query(
            query, 
            {
                "start_id": start_node_id,
                "end_id": end_node_id,
                "properties": properties
            }
        )
        
        if not result:
            raise RuntimeError("Failed to create relationship")
            
        return result[0]["id"]
