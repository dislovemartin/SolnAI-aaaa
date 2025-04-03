import asyncio
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union, cast

import aiofiles
import boto3
import faiss
import numpy as np
import redis.asyncio as redis
from botocore.exceptions import ClientError
from loguru import logger
from prometheus_client import Counter, Gauge, Histogram
from sentence_transformers import SentenceTransformer

# Prometheus metrics
BACKUP_DURATION: Histogram = Histogram(
    'vector_store_backup_duration_seconds',
    'Time spent performing backup operations',
    ['operation']
)
BACKUP_SUCCESS: Counter = Counter(
    'vector_store_backup_success_total',
    'Number of successful backup operations',
    ['type']
)
BACKUP_FAILURE: Counter = Counter(
    'vector_store_backup_failure_total',
    'Number of failed backup operations',
    ['type']
)
BACKUP_SIZE: Gauge = Gauge(
    'vector_store_backup_size_bytes',
    'Size of the latest backup',
    ['component']
)
VECTOR_COUNT: Gauge = Gauge(
    'vector_store_vector_count',
    'Number of vectors in store',
    ['index_type']
)
VECTOR_OPERATION_DURATION: Histogram = Histogram(
    'vector_store_operation_duration_seconds',
    'Time spent on vector operations',
    ['operation']
)
VECTOR_OPERATION_ERRORS: Counter = Counter(
    'vector_store_operation_errors_total',
    'Number of vector operation errors',
    ['operation']
)
LAST_BACKUP_TIMESTAMP: Gauge = Gauge(
    'vector_store_last_backup_timestamp',
    'Timestamp of the last successful backup'
)
BACKUP_AGE: Gauge = Gauge(
    'vector_store_backup_age_seconds',
    'Age of the latest backup in seconds'
)

class VectorStore:
    """Vector store for managing embeddings and similarity search."""

    def __init__(
        self, 
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        dimension: int = 384,
        redis_url: str = "redis://localhost:6379",
        index_name: str = "chimera-vectors",
        user_index_name: str = "chimera-users",
        backup_dir: str = "/tmp/vector_store_backup",
        s3_bucket: Optional[str] = None,
        s3_prefix: str = "vector_store_backups",
    ) -> None:
        """Initialize the vector store.
        
        Args:
            model_name: Name of the sentence transformer model to use
            dimension: Dimension of the embeddings
            redis_url: URL of the Redis server
            index_name: Name of the index for content embeddings
            user_index_name: Name of the index for user embeddings
            backup_dir: Local directory for storing backups
            s3_bucket: Optional S3 bucket for backup storage
            s3_prefix: Prefix for S3 backup storage path
        """
        self.model_name = model_name
        self.dimension = dimension
        self.redis_url = redis_url
        self.index_name = index_name
        self.user_index_name = user_index_name
        self.backup_dir = backup_dir
        self.s3_bucket = s3_bucket
        self.s3_prefix = s3_prefix
        
        self.model: Optional[SentenceTransformer] = None
        self.redis: Optional[redis.Redis] = None
        self.content_index: Optional[faiss.IndexFlatIP] = None
        self.user_index: Optional[faiss.IndexFlatIP] = None
        self.initialized: bool = False

        # Ensure backup directory exists
        os.makedirs(self.backup_dir, exist_ok=True)

        # Update initial vector counts
        VECTOR_COUNT.labels(index_type='content').set(0)
        VECTOR_COUNT.labels(index_type='user').set(0)

    async def initialize(self) -> None:
        """Initialize the vector store components."""
        try:
            # Initialize the embedding model
            self.model = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: SentenceTransformer(self.model_name)
            )
            logger.info(f"Initialized SentenceTransformer model: {self.model_name}")
            
            # Initialize Redis connection
            self.redis = redis.from_url(self.redis_url)
            logger.info(f"Connected to Redis at {self.redis_url}")
            
            # Initialize FAISS indices
            self.content_index = faiss.IndexFlatIP(self.dimension)  # Inner product for cosine similarity
            self.user_index = faiss.IndexFlatIP(self.dimension)
            
            # Load existing vectors from Redis if available
            await self._load_indices()
            
            self.initialized = True
            logger.info("Vector store initialization complete")
            
        except Exception as e:
            logger.error(f"Failed to initialize vector store: {e}")
            raise RuntimeError(f"Vector store initialization failed: {str(e)}")

    async def close(self) -> None:
        """Close the vector store connection."""
        if self.redis:
            await self.redis.close()
            logger.info("Redis connection closed")

    async def is_healthy(self) -> bool:
        """Check if the vector store is healthy."""
        if not self.initialized or not self.redis:
            return False
            
        try:
            await self.redis.ping()
            return True
        except Exception:
            return False

    async def _load_indices(self) -> None:
        """Load existing embeddings from Redis into FAISS indices."""
        try:
            # Load content embeddings
            content_keys = await self.redis.keys(f"{self.index_name}:*")
            if content_keys:
                logger.info(f"Loading {len(content_keys)} content embeddings from Redis")
                
                # Reset the index
                self.content_index = faiss.IndexFlatIP(self.dimension)
                
                # Load embeddings in batches to avoid memory issues
                batch_size = 1000
                for i in range(0, len(content_keys), batch_size):
                    batch = content_keys[i:i+batch_size]
                    
                    # Get embeddings and metadata
                    pipe = self.redis.pipeline()
                    for key in batch:
                        pipe.get(key)
                    
                    results = await pipe.execute()
                    
                    # Parse and add to index
                    embeddings = []
                    for data in results:
                        if data:
                            item = json.loads(data)
                            if "embedding" in item:
                                embeddings.append(np.array(item["embedding"], dtype=np.float32))
                    
                    if embeddings:
                        embeddings_array = np.vstack(embeddings).astype(np.float32)
                        self.content_index.add(embeddings_array)
                
                logger.info(f"Loaded {self.content_index.ntotal} content embeddings into FAISS index")
            
            # Load user embeddings
            user_keys = await self.redis.keys(f"{self.user_index_name}:*")
            if user_keys:
                logger.info(f"Loading {len(user_keys)} user embeddings from Redis")
                
                # Reset the index
                self.user_index = faiss.IndexFlatIP(self.dimension)
                
                # Load embeddings
                pipe = self.redis.pipeline()
                for key in user_keys:
                    pipe.get(key)
                
                results = await pipe.execute()
                
                # Parse and add to index
                embeddings = []
                for data in results:
                    if data:
                        user = json.loads(data)
                        if "embedding" in user:
                            embeddings.append(np.array(user["embedding"], dtype=np.float32))
                
                if embeddings:
                    embeddings_array = np.vstack(embeddings).astype(np.float32)
                    self.user_index.add(embeddings_array)
                
                logger.info(f"Loaded {self.user_index.ntotal} user embeddings into FAISS index")
            
        except Exception as e:
            logger.error(f"Error loading indices from Redis: {e}")
            # Initialize empty indices if loading fails
            self.content_index = faiss.IndexFlatIP(self.dimension)
            self.user_index = faiss.IndexFlatIP(self.dimension)

    async def _generate_embedding(self, text: str) -> np.ndarray:
        """Generate an embedding vector for the given text.
        
        Args:
            text: The text to generate an embedding for
            
        Returns:
            np.ndarray: The embedding vector
            
        Raises:
            RuntimeError: If the model is not initialized
        """
        if not self.model:
            raise RuntimeError("Model not initialized")
            
        embedding = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self.model.encode(text, convert_to_numpy=True)
        )
        return embedding.astype(np.float32)

    async def add_item(
        self, 
        item_id: str, 
        text: str, 
        metadata: Dict[str, Any]
    ) -> None:
        """Add an item to the vector store.
        
        Args:
            item_id: Unique identifier for the item
            text: Text content to generate embedding from
            metadata: Additional metadata to store with the item
            
        Raises:
            RuntimeError: If the store is not initialized
        """
        if not self.initialized or not self.redis or not self.content_index:
            raise RuntimeError("Vector store not initialized")
            
        try:
            with VECTOR_OPERATION_DURATION.labels(operation='add_item').time():
            # Generate embedding
            embedding = await self._generate_embedding(text)
            
            # Store in Redis
            data = {
                "id": item_id,
                "embedding": embedding.tolist(),
                "metadata": metadata,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                await self.redis.set(
                    f"{self.index_name}:{item_id}",
                    json.dumps(data)
                )
            
            # Add to FAISS index
                self.content_index.add(embedding.reshape(1, -1))
            
                # Update metrics
                await self._update_metrics()
            
        except Exception as e:
            VECTOR_OPERATION_ERRORS.labels(operation='add_item').inc()
            logger.error(f"Failed to add item {item_id}: {e}")
            raise

    async def add_user(
        self, 
        user_id: str, 
        interests: str,
        preferences: Dict[str, Any],
        role: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Add a user profile to the vector store.
        
        Args:
            user_id: Unique identifier for the user
            interests: Text describing user interests
            preferences: User preferences dictionary
            role: Optional user role
            metadata: Additional metadata to store
            
        Raises:
            RuntimeError: If the store is not initialized
        """
        if not self.initialized or not self.redis or not self.user_index:
            raise RuntimeError("Vector store not initialized")
            
        try:
            with VECTOR_OPERATION_DURATION.labels(operation='add_user').time():
                # Generate embedding from interests
            embedding = await self._generate_embedding(interests)
            
            # Store in Redis
            data = {
                "id": user_id,
                "embedding": embedding.tolist(),
                    "interests": interests,
                "preferences": preferences,
                "role": role,
                "metadata": metadata or {},
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                await self.redis.set(
                    f"{self.user_index_name}:{user_id}",
                    json.dumps(data)
                )
            
            # Add to FAISS index
                self.user_index.add(embedding.reshape(1, -1))
            
                # Update metrics
                await self._update_metrics()
            
        except Exception as e:
            VECTOR_OPERATION_ERRORS.labels(operation='add_user').inc()
            logger.error(f"Failed to add user {user_id}: {e}")
            raise

    async def update_user(
        self, 
        user_id: str, 
        interests: str,
        preferences: Dict[str, Any],
        role: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Update a user profile in the vector store.
        
        Args:
            user_id: Unique identifier for the user
            interests: Updated text describing user interests
            preferences: Updated user preferences dictionary
            role: Optional updated user role
            metadata: Additional metadata to store
            
        Raises:
            RuntimeError: If the store is not initialized
            KeyError: If the user does not exist
        """
        if not self.initialized or not self.redis or not self.user_index:
            raise RuntimeError("Vector store not initialized")
            
        try:
            with VECTOR_OPERATION_DURATION.labels(operation='update_user').time():
            # Check if user exists
                existing_data = await self.redis.get(f"{self.user_index_name}:{user_id}")
                if not existing_data:
                    raise KeyError(f"User {user_id} not found")
            
            # Generate new embedding
            embedding = await self._generate_embedding(interests)
            
                # Store updated data in Redis
            data = {
                "id": user_id,
                "embedding": embedding.tolist(),
                    "interests": interests,
                "preferences": preferences,
                "role": role,
                "metadata": metadata or {},
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                await self.redis.set(
                    f"{self.user_index_name}:{user_id}",
                    json.dumps(data)
                )
                
                # Update FAISS index (remove old and add new)
                # Note: This is a simplification. In production, we'd need a more
                # sophisticated way to update vectors in FAISS
                self.user_index = faiss.IndexFlatIP(self.dimension)
                await self._load_indices()
                
                # Update metrics
                await self._update_metrics()
                
        except KeyError:
            VECTOR_OPERATION_ERRORS.labels(operation='update_user').inc()
            logger.error(f"User {user_id} not found")
            raise
        except Exception as e:
            VECTOR_OPERATION_ERRORS.labels(operation='update_user').inc()
            logger.error(f"Failed to update user {user_id}: {e}")
            raise

    async def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a user profile from the vector store.
        
        Args:
            user_id: Unique identifier for the user
            
        Returns:
            Optional[Dict[str, Any]]: User profile data if found, None otherwise
            
        Raises:
            RuntimeError: If the store is not initialized
        """
        if not self.initialized or not self.redis:
            raise RuntimeError("Vector store not initialized")
            
        try:
            with VECTOR_OPERATION_DURATION.labels(operation='get_user').time():
                data = await self.redis.get(f"{self.user_index_name}:{user_id}")
            if data:
                    return cast(Dict[str, Any], json.loads(data))
            return None
            
        except Exception as e:
            VECTOR_OPERATION_ERRORS.labels(operation='get_user').inc()
            logger.error(f"Failed to get user {user_id}: {e}")
            raise

    async def find_similar_to_user(
        self, 
        user_id: str,
        content_types: Optional[List[str]] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Find content similar to a user's interests.
        
        Args:
            user_id: Unique identifier for the user
            content_types: Optional list of content types to filter by
            limit: Maximum number of results to return
            
        Returns:
            List[Dict[str, Any]]: List of similar content items
            
        Raises:
            RuntimeError: If the store is not initialized
            KeyError: If the user does not exist
        """
        if not self.initialized or not self.redis or not self.content_index:
            raise RuntimeError("Vector store not initialized")
            
        try:
            with VECTOR_OPERATION_DURATION.labels(operation='find_similar').time():
            # Get user embedding
                user_data = await self.get_user(user_id)
                if not user_data or "embedding" not in user_data:
                    raise KeyError(f"User {user_id} not found or has no embedding")
                    
                user_embedding = np.array(user_data["embedding"], dtype=np.float32)
                
                # Search content index
                D, I = self.content_index.search(
                    user_embedding.reshape(1, -1),
                    limit
                )
                
                # Get content items
                results = []
                async with self.redis.pipeline() as pipe:
                    # Get all content keys
                    content_keys = await self.redis.keys(f"{self.index_name}:*")
                    if not content_keys:
                        return []
                        
                    # Get content data
                    for key in content_keys:
                        pipe.get(key)
                    content_data = await pipe.execute()
                    
                    # Filter and sort by similarity
                    for i, idx in enumerate(I[0]):
                        if idx < len(content_data) and content_data[idx]:
                            item = json.loads(content_data[idx])
                    
                # Apply content type filter if specified
                            if (content_types and 
                                "metadata" in item and 
                                "content_type" in item["metadata"] and
                                item["metadata"]["content_type"] not in content_types):
                        continue
                
                            item["similarity"] = float(D[0][i])
                            results.append(item)
                
                if len(results) >= limit:
                    break
            
            return results
            
        except KeyError:
            VECTOR_OPERATION_ERRORS.labels(operation='find_similar').inc()
            logger.error(f"User {user_id} not found")
            raise
        except Exception as e:
            VECTOR_OPERATION_ERRORS.labels(operation='find_similar').inc()
            logger.error(f"Failed to find similar content for user {user_id}: {e}")
            raise

    async def search(
        self, 
        query: str,
        content_types: Optional[List[str]] = None,
        limit: int = 10,
        user_embedding: Optional[List[float]] = None,
        user_weight: float = 0.3
    ) -> List[Dict[str, Any]]:
        """Search for content using a text query and optional user context.
        
        Args:
            query: Search query text
            content_types: Optional list of content types to filter by
            limit: Maximum number of results to return
            user_embedding: Optional user embedding for personalized results
            user_weight: Weight to apply to user similarity (0-1)
            
        Returns:
            List[Dict[str, Any]]: List of search results
            
        Raises:
            RuntimeError: If the store is not initialized
            ValueError: If user_weight is not between 0 and 1
        """
        if not self.initialized or not self.redis or not self.content_index:
            raise RuntimeError("Vector store not initialized")
            
        if not 0 <= user_weight <= 1:
            raise ValueError("user_weight must be between 0 and 1")
            
        try:
            with VECTOR_OPERATION_DURATION.labels(operation='search').time():
                # Generate query embedding
                query_embedding = await self._generate_embedding(query)
                
                # Combine with user embedding if provided
                if user_embedding is not None:
                    user_embedding_array = np.array(user_embedding, dtype=np.float32)
                    combined_embedding = (
                        (1 - user_weight) * query_embedding +
                        user_weight * user_embedding_array
                    )
                    # Normalize the combined embedding
                    combined_embedding /= np.linalg.norm(combined_embedding)
                else:
                    combined_embedding = query_embedding
                
                # Search content index
                D, I = self.content_index.search(
                    combined_embedding.reshape(1, -1),
                    limit
                )
                
                # Get content items
                results = []
                async with self.redis.pipeline() as pipe:
                    # Get all content keys
                    content_keys = await self.redis.keys(f"{self.index_name}:*")
                    if not content_keys:
                        return []
                        
                    # Get content data
                    for key in content_keys:
                        pipe.get(key)
                    content_data = await pipe.execute()
                    
                    # Filter and sort by similarity
                    for i, idx in enumerate(I[0]):
                        if idx < len(content_data) and content_data[idx]:
                            item = json.loads(content_data[idx])
                            
                            # Apply content type filter if specified
                            if (content_types and 
                                "metadata" in item and 
                                "content_type" in item["metadata"] and
                                item["metadata"]["content_type"] not in content_types):
                                continue
                                
                            item["similarity"] = float(D[0][i])
                            results.append(item)
                            
                            if len(results) >= limit:
                                break
                
                return results
                
        except Exception as e:
            VECTOR_OPERATION_ERRORS.labels(operation='search').inc()
            logger.error(f"Failed to search: {e}")
            raise

    async def _update_metrics(self) -> None:
        """Update Prometheus metrics for the vector store."""
        try:
            # Update vector counts
            if self.content_index:
                VECTOR_COUNT.labels(index_type='content').set(self.content_index.ntotal)
            if self.user_index:
                VECTOR_COUNT.labels(index_type='user').set(self.user_index.ntotal)
        except Exception as e:
            logger.error(f"Failed to update metrics: {e}")

    @VECTOR_OPERATION_DURATION.labels(operation='backup').time()
    async def backup(
        self,
        backup_id: Optional[str] = None,
        upload_to_s3: bool = True
    ) -> str:
        """Create a backup of the vector store.
        
        Args:
            backup_id: Optional identifier for the backup
            upload_to_s3: Whether to upload the backup to S3
            
        Returns:
            str: The backup ID
            
        Raises:
            RuntimeError: If the store is not initialized
            ValueError: If S3 upload is requested but not configured
        """
        if not self.initialized or not self.redis:
            raise RuntimeError("Vector store not initialized")
            
        if upload_to_s3 and not self.s3_bucket:
            raise ValueError("S3 bucket not configured")
            
        try:
            # Generate backup ID if not provided
            backup_id = backup_id or datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
            backup_path = os.path.join(self.backup_dir, backup_id)
            os.makedirs(backup_path, exist_ok=True)
            
            # Save Redis data
            redis_path = os.path.join(backup_path, "redis_data.json")
            async with aiofiles.open(redis_path, 'w') as f:
                # Get all keys and data
                all_keys = []
                all_keys.extend(await self.redis.keys(f"{self.index_name}:*"))
                all_keys.extend(await self.redis.keys(f"{self.user_index_name}:*"))
                
                # Get all values
                pipe = self.redis.pipeline()
                for key in all_keys:
                    pipe.get(key)
                all_values = await pipe.execute()
                
                # Create backup data
                backup_data = {
                    key: value.decode() if isinstance(value, bytes) else value
                    for key, value in zip(all_keys, all_values)
                    if value is not None
                }
                
                await f.write(json.dumps(backup_data, indent=2))
            
            # Save FAISS indices
            if self.content_index:
                content_path = os.path.join(backup_path, "content_index.faiss")
                faiss.write_index(self.content_index, content_path)
                
            if self.user_index:
                user_path = os.path.join(backup_path, "user_index.faiss")
                faiss.write_index(self.user_index, user_path)
            
            # Create metadata
            metadata = {
                "id": backup_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "content_vectors": self.content_index.ntotal if self.content_index else 0,
                "user_vectors": self.user_index.ntotal if self.user_index else 0,
                "redis_keys": len(all_keys),
                "model_name": self.model_name,
                "dimension": self.dimension
            }
            
            metadata_path = os.path.join(backup_path, "metadata.json")
            async with aiofiles.open(metadata_path, 'w') as f:
                await f.write(json.dumps(metadata, indent=2))
            
            # Upload to S3 if requested
            if upload_to_s3:
                s3 = boto3.client('s3')
                for root, _, files in os.walk(backup_path):
                    for file in files:
                        local_path = os.path.join(root, file)
                        s3_key = os.path.join(
                            self.s3_prefix,
                            backup_id,
                            file
                        )
                        s3.upload_file(
                            local_path,
                            self.s3_bucket,
                            s3_key,
                            ExtraArgs={'ServerSideEncryption': 'AES256'}
                        )
            
            # Update metrics
            BACKUP_SUCCESS.labels(type='full').inc()
            LAST_BACKUP_TIMESTAMP.set(time.time())
            
            # Calculate and set backup size
            total_size = 0
            for root, _, files in os.walk(backup_path):
                for file in files:
                    total_size += os.path.getsize(os.path.join(root, file))
            BACKUP_SIZE.labels(component='total').set(total_size)
            
            logger.info(f"Backup completed: {backup_id}")
            return backup_id
            
        except Exception as e:
            BACKUP_FAILURE.labels(type='full').inc()
            logger.error(f"Backup failed: {e}")
            raise

    @VECTOR_OPERATION_DURATION.labels(operation='restore').time()
    async def restore(
        self,
        backup_id: str,
        download_from_s3: bool = True
    ) -> None:
        """Restore the vector store from a backup.
        
        Args:
            backup_id: Identifier of the backup to restore
            download_from_s3: Whether to download the backup from S3
            
        Raises:
            RuntimeError: If the store is not initialized
            ValueError: If S3 download is requested but not configured
            FileNotFoundError: If the backup does not exist
        """
        if not self.initialized or not self.redis:
            raise RuntimeError("Vector store not initialized")
            
        if download_from_s3 and not self.s3_bucket:
            raise ValueError("S3 bucket not configured")
            
        try:
            backup_path = os.path.join(self.backup_dir, backup_id)
            
            # Download from S3 if requested
            if download_from_s3:
                os.makedirs(backup_path, exist_ok=True)
                s3 = boto3.client('s3')
                
                # List and download all backup files
                prefix = os.path.join(self.s3_prefix, backup_id)
                response = s3.list_objects_v2(
                    Bucket=self.s3_bucket,
                    Prefix=prefix
                )
                
                if 'Contents' not in response:
                    raise FileNotFoundError(f"Backup {backup_id} not found in S3")
                    
                for obj in response['Contents']:
                    key = obj['Key']
                    filename = os.path.basename(key)
                    local_path = os.path.join(backup_path, filename)
                    
                    s3.download_file(
                        self.s3_bucket,
                        key,
                        local_path
                    )
            
            # Verify backup exists
            if not os.path.exists(backup_path):
                raise FileNotFoundError(f"Backup {backup_id} not found")
            
            # Load metadata
            metadata_path = os.path.join(backup_path, "metadata.json")
            async with aiofiles.open(metadata_path, 'r') as f:
                metadata = json.loads(await f.read())
            
            # Verify compatibility
            if metadata['dimension'] != self.dimension:
                raise ValueError(
                    f"Backup dimension ({metadata['dimension']}) does not match "
                    f"current dimension ({self.dimension})"
                )
            
            # Restore Redis data
            redis_path = os.path.join(backup_path, "redis_data.json")
            async with aiofiles.open(redis_path, 'r') as f:
                redis_data = json.loads(await f.read())
            
            # Clear existing data
            await self.redis.delete(
                *(await self.redis.keys(f"{self.index_name}:*")),
                *(await self.redis.keys(f"{self.user_index_name}:*"))
            )
            
            # Restore data
            pipe = self.redis.pipeline()
            for key, value in redis_data.items():
                pipe.set(key, value)
            await pipe.execute()
            
            # Restore FAISS indices
            content_path = os.path.join(backup_path, "content_index.faiss")
            if os.path.exists(content_path):
                self.content_index = faiss.read_index(content_path)
            
            user_path = os.path.join(backup_path, "user_index.faiss")
            if os.path.exists(user_path):
                self.user_index = faiss.read_index(user_path)
            
            # Update metrics
            await self._update_metrics()
            
            logger.info(f"Restore completed from backup: {backup_id}")
            
        except Exception as e:
            VECTOR_OPERATION_ERRORS.labels(operation='restore').inc()
            logger.error(f"Restore failed: {e}")
            raise

    async def verify_backup(self, backup_id: str) -> Dict[str, Any]:
        """Verify the integrity of a backup.
        
        Args:
            backup_id: Identifier of the backup to verify
            
        Returns:
            Dict[str, Any]: Verification results including metadata and integrity checks
            
        Raises:
            RuntimeError: If the store is not initialized
            FileNotFoundError: If the backup does not exist
        """
        if not self.initialized:
            raise RuntimeError("Vector store not initialized")
            
        try:
            backup_path = os.path.join(self.backup_dir, backup_id)
            if not os.path.exists(backup_path):
                raise FileNotFoundError(f"Backup {backup_id} not found")
            
            # Load and verify metadata
            metadata_path = os.path.join(backup_path, "metadata.json")
            async with aiofiles.open(metadata_path, 'r') as f:
                metadata = json.loads(await f.read())
            
            # Load and verify indices
            content_path = os.path.join(backup_path, "content_index.faiss")
            user_path = os.path.join(backup_path, "user_index.faiss")
            
            content_index = faiss.read_index(content_path) if os.path.exists(content_path) else None
            user_index = faiss.read_index(user_path) if os.path.exists(user_path) else None
            
            # Load and verify Redis data
            redis_path = os.path.join(backup_path, "redis_data.json")
            async with aiofiles.open(redis_path, 'r') as f:
                redis_data = json.loads(await f.read())
            
            # Compile verification results
            return {
                "backup_id": backup_id,
                "timestamp": metadata["timestamp"],
                "content_index": {
                    "expected_size": metadata["content_vectors"],
                    "actual_size": content_index.ntotal if content_index else 0,
                    "verified": (content_index.ntotal if content_index else 0) == metadata["content_vectors"]
                },
                "user_index": {
                    "expected_size": metadata["user_vectors"],
                    "actual_size": user_index.ntotal if user_index else 0,
                    "verified": (user_index.ntotal if user_index else 0) == metadata["user_vectors"]
                },
                "redis_data": {
                    "expected_keys": metadata["redis_keys"],
                    "actual_keys": len(redis_data),
                    "verified": len(redis_data) == metadata["redis_keys"]
                },
                "model": {
                    "name": metadata["model_name"],
                    "dimension": metadata["dimension"],
                    "compatible": metadata["dimension"] == self.dimension
                }
            }
            
        except Exception as e:
            VECTOR_OPERATION_ERRORS.labels(operation='verify').inc()
            logger.error(f"Failed to verify backup {backup_id}: {e}")
            raise

    async def list_backups(self) -> List[Dict[str, Any]]:
        """List all available backups.
        
        Returns:
            List[Dict[str, Any]]: List of backup metadata, sorted by timestamp descending
            
        Raises:
            RuntimeError: If the store is not initialized
        """
        if not self.initialized:
            raise RuntimeError("Vector store not initialized")
            
        try:
            backups = []
            
            # List local backups
            if os.path.exists(self.backup_dir):
                for backup_id in os.listdir(self.backup_dir):
                    backup_path = os.path.join(self.backup_dir, backup_id)
                    metadata_path = os.path.join(backup_path, "metadata.json")
                    
                    if os.path.isfile(metadata_path):
                        async with aiofiles.open(metadata_path, 'r') as f:
                            metadata = json.loads(await f.read())
                            backups.append(metadata)
            
            # List S3 backups if configured
            if self.s3_bucket:
                s3 = boto3.client('s3')
                paginator = s3.get_paginator('list_objects_v2')
                
                async for page in paginator.paginate(
                    Bucket=self.s3_bucket,
                    Prefix=f"{self.s3_prefix}/"
                ):
                    for obj in page.get('Contents', []):
                        if obj['Key'].endswith('metadata.json'):
                            response = s3.get_object(
                                Bucket=self.s3_bucket,
                                Key=obj['Key']
                            )
                            metadata = json.loads(response['Body'].read())
                            
                            # Add S3-specific metadata
                            metadata['storage'] = 's3'
                            metadata['size'] = obj['Size']
                            metadata['last_modified'] = obj['LastModified'].isoformat()
                            
                            backups.append(metadata)
            
            # Sort by timestamp descending
            backups.sort(
                key=lambda x: datetime.fromisoformat(x['timestamp']),
                reverse=True
            )
            
            return backups
            
        except Exception as e:
            VECTOR_OPERATION_ERRORS.labels(operation='list_backups').inc()
            logger.error(f"Failed to list backups: {e}")
            raise

    async def cleanup_old_backups(
        self,
        retain_days: int = 7,
        retain_weekly: int = 4,
        retain_monthly: int = 6
    ) -> None:
        """Clean up old backups based on retention policy.
        
        Args:
            retain_days: Number of daily backups to retain
            retain_weekly: Number of weekly backups to retain
            retain_monthly: Number of monthly backups to retain
            
        Raises:
            RuntimeError: If the store is not initialized
        """
        if not self.initialized:
            raise RuntimeError("Vector store not initialized")
            
        try:
            backups = await self.list_backups()
            if not backups:
                return
                
            now = datetime.now(timezone.utc)
            to_delete = set()
            to_keep = set()
            
            # Group backups by time period
            daily_backups = []
            weekly_backups = []
            monthly_backups = []
            
            for backup in backups:
                timestamp = datetime.fromisoformat(backup['timestamp'])
                age = now - timestamp
                
                if age.days < retain_days:
                    daily_backups.append(backup)
                elif age.days < retain_days + (retain_weekly * 7):
                    if timestamp.weekday() == 0:  # Monday
                        weekly_backups.append(backup)
                elif age.days < retain_days + (retain_weekly * 7) + (retain_monthly * 30):
                    if timestamp.day == 1:  # First of month
                        monthly_backups.append(backup)
                else:
                    to_delete.add(backup['id'])
            
            # Keep the most recent backups according to retention policy
            to_keep.update(b['id'] for b in daily_backups[:retain_days])
            to_keep.update(b['id'] for b in weekly_backups[:retain_weekly])
            to_keep.update(b['id'] for b in monthly_backups[:retain_monthly])
            
            # Delete old backups
            for backup in backups:
                if backup['id'] not in to_keep:
                    backup_path = os.path.join(self.backup_dir, backup['id'])
                    if os.path.exists(backup_path):
                        shutil.rmtree(backup_path)
                    
                    # Delete from S3 if configured
                    if self.s3_bucket:
                        s3 = boto3.client('s3')
                        prefix = os.path.join(self.s3_prefix, backup['id'])
                        
                        # List and delete all backup files
                        response = s3.list_objects_v2(
                            Bucket=self.s3_bucket,
                            Prefix=prefix
                        )
                        
                        if 'Contents' in response:
                            for obj in response['Contents']:
                                s3.delete_object(
                                    Bucket=self.s3_bucket,
                                    Key=obj['Key']
                                )
            
            logger.info(
                f"Cleaned up old backups: kept {len(to_keep)} backups, "
                f"deleted {len(to_delete)} backups"
            )
            
        except Exception as e:
            VECTOR_OPERATION_ERRORS.labels(operation='cleanup').inc()
            logger.error(f"Failed to clean up old backups: {e}")
            raise
