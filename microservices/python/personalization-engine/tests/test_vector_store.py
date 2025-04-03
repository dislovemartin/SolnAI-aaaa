import json
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import faiss
import numpy as np
import pytest
import redis
from app.vector_store import VectorStore
from sentence_transformers import SentenceTransformer

# Test data
TEST_EMBEDDING_DIM = 384
TEST_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
TEST_REDIS_URL = "redis://localhost:6379"
TEST_INDEX_NAME = "test-vectors"
TEST_USER_INDEX_NAME = "test-users"
TEST_BACKUP_DIR = "/tmp/test_vector_store_backup"

@pytest.fixture
def mock_sentence_transformer():
    """Mock SentenceTransformer to avoid loading the actual model."""
    with patch('sentence_transformers.SentenceTransformer') as mock:
        # Configure mock to return consistent embeddings for testing
        mock_model = Mock()
        mock_model.encode.return_value = np.ones(TEST_EMBEDDING_DIM, dtype=np.float32)
        mock.return_value = mock_model
        yield mock

@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    with patch('redis.from_url') as mock:
        mock_redis = AsyncMock()
        mock_redis.ping.return_value = True
        mock_redis.keys.return_value = []
        mock_redis.get.return_value = None
        mock_redis.pipeline.return_value = AsyncMock()
        mock.return_value = mock_redis
        yield mock_redis

@pytest.fixture
async def vector_store(mock_sentence_transformer, mock_redis):
    """Create a VectorStore instance with mocked dependencies."""
    store = VectorStore(
        model_name=TEST_MODEL_NAME,
        dimension=TEST_EMBEDDING_DIM,
        redis_url=TEST_REDIS_URL,
        index_name=TEST_INDEX_NAME,
        user_index_name=TEST_USER_INDEX_NAME,
        backup_dir=TEST_BACKUP_DIR
    )
    await store.initialize()
    return store

@pytest.mark.asyncio
async def test_initialization(vector_store, mock_redis):
    """Test VectorStore initialization."""
    assert vector_store.initialized
    assert vector_store.model is not None
    assert vector_store.redis is not None
    assert vector_store.content_index is not None
    assert vector_store.user_index is not None
    assert isinstance(vector_store.content_index, faiss.IndexFlatIP)
    assert isinstance(vector_store.user_index, faiss.IndexFlatIP)

@pytest.mark.asyncio
async def test_generate_embedding(vector_store):
    """Test embedding generation."""
    test_text = "This is a test text"
    embedding = await vector_store._generate_embedding(test_text)
    
    assert isinstance(embedding, np.ndarray)
    assert embedding.shape == (TEST_EMBEDDING_DIM,)
    assert embedding.dtype == np.float32

@pytest.mark.asyncio
async def test_add_item(vector_store, mock_redis):
    """Test adding an item to the vector store."""
    item_id = "test_item_1"
    text = "Test item content"
    metadata = {"type": "test", "category": "sample"}
    
    # Configure mock Redis to store the item
    mock_redis.set.return_value = True
    
    await vector_store.add_item(item_id, text, metadata)
    
    # Verify Redis interaction
    mock_redis.set.assert_called_once()
    call_args = mock_redis.set.call_args[0]
    assert call_args[0] == f"{TEST_INDEX_NAME}:{item_id}"
    
    # Verify stored data structure
    stored_data = json.loads(call_args[1])
    assert stored_data["id"] == item_id
    assert stored_data["metadata"] == metadata
    assert "embedding" in stored_data
    assert "timestamp" in stored_data
    
    # Verify FAISS index update
    assert vector_store.content_index.ntotal == 1

@pytest.mark.asyncio
async def test_add_user(vector_store, mock_redis):
    """Test adding a user to the vector store."""
    user_id = "test_user_1"
    interests = "AI, Machine Learning, Python"
    preferences = {"theme": "dark", "language": "en"}
    role = "developer"
    metadata = {"country": "US"}
    
    # Configure mock Redis
    mock_redis.set.return_value = True
    
    await vector_store.add_user(user_id, interests, preferences, role, metadata)
    
    # Verify Redis interaction
    mock_redis.set.assert_called_once()
    call_args = mock_redis.set.call_args[0]
    assert call_args[0] == f"{TEST_USER_INDEX_NAME}:{user_id}"
    
    # Verify stored data structure
    stored_data = json.loads(call_args[1])
    assert stored_data["id"] == user_id
    assert stored_data["interests"] == interests
    assert stored_data["preferences"] == preferences
    assert stored_data["role"] == role
    assert stored_data["metadata"] == metadata
    assert "embedding" in stored_data
    assert "timestamp" in stored_data
    
    # Verify FAISS index update
    assert vector_store.user_index.ntotal == 1

@pytest.mark.asyncio
async def test_backup_restore(vector_store, mock_redis, tmp_path):
    """Test backup and restore functionality."""
    # Setup test data
    backup_dir = str(tmp_path / "backups")
    vector_store.backup_dir = backup_dir
    os.makedirs(backup_dir, exist_ok=True)
    
    # Add test data
    await vector_store.add_item("test_item", "Test content", {"type": "test"})
    await vector_store.add_user("test_user", "Test interests", {"pref": "test"})
    
    # Create backup
    backup_id = await vector_store.backup(upload_to_s3=False)
    assert os.path.exists(os.path.join(backup_dir, backup_id))
    
    # Clear indices
    vector_store.content_index = faiss.IndexFlatIP(TEST_EMBEDDING_DIM)
    vector_store.user_index = faiss.IndexFlatIP(TEST_EMBEDDING_DIM)
    
    # Restore from backup
    await vector_store.restore(backup_id, download_from_s3=False)
    
    # Verify restoration
    assert vector_store.content_index.ntotal == 1
    assert vector_store.user_index.ntotal == 1

@pytest.mark.asyncio
async def test_find_similar_to_user(vector_store, mock_redis):
    """Test finding similar content for a user."""
    # Setup test data
    user_id = "test_user"
    user_data = {
        "id": user_id,
        "embedding": np.ones(TEST_EMBEDDING_DIM).tolist(),
        "interests": "test interests"
    }
    mock_redis.get.return_value = json.dumps(user_data)
    
    # Add some test content
    await vector_store.add_item("item1", "Test content 1", {"type": "article"})
    await vector_store.add_item("item2", "Test content 2", {"type": "video"})
    
    # Find similar content
    results = await vector_store.find_similar_to_user(user_id, content_types=["article"], limit=2)
    
    assert isinstance(results, list)
    assert len(results) <= 2
    for result in results:
        assert "id" in result
        assert "similarity" in result
        assert "metadata" in result

@pytest.mark.asyncio
async def test_health_check(vector_store, mock_redis):
    """Test health check functionality."""
    # Test when healthy
    mock_redis.ping.return_value = True
    assert await vector_store.is_healthy()
    
    # Test when Redis is down
    mock_redis.ping.side_effect = redis.ConnectionError()
    assert not await vector_store.is_healthy()

@pytest.mark.asyncio
async def test_error_handling(vector_store):
    """Test error handling in various scenarios."""
    # Test uninitialized state
    vector_store.initialized = False
    with pytest.raises(RuntimeError):
        await vector_store.add_item("test", "content", {})
    
    # Test model not initialized
    vector_store.initialized = True
    vector_store.model = None
    with pytest.raises(RuntimeError):
        await vector_store._generate_embedding("test")
    
    # Test invalid backup restore
    with pytest.raises(FileNotFoundError):
        await vector_store.restore("nonexistent_backup", download_from_s3=False)

@pytest.mark.asyncio
async def test_cleanup(vector_store, mock_redis):
    """Test cleanup and resource management."""
    # Test close method
    await vector_store.close()
    mock_redis.close.assert_called_once()
    
    # Verify metrics are updated
    assert vector_store.content_index.ntotal == 0
    assert vector_store.user_index.ntotal == 0 