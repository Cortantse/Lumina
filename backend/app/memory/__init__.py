"""
Memory subsystem for Lumina.

This package provides implementations for storing and retrieving memories
as vector embeddings using FAISS.
"""

from .store import get_memory_manager, FAISSMemoryStore
from .embeddings import get_embedding_service, EmbeddingService

__all__ = [
    "get_memory_manager",
    "FAISSMemoryStore",
    "get_embedding_service",
    "EmbeddingService",
] 