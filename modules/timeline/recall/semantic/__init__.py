"""Optional local semantic recall (embeddings + vector index).

This package is intentionally decoupled from the core recorder. It only does
anything when semantic indexing is enabled in config AND the optional
dependencies (sentence-transformers, faiss) are installed. Everything degrades
gracefully otherwise.
"""
from .service import SemanticService, get_semantic_service, semantic_available

__all__ = ["SemanticService", "get_semantic_service", "semantic_available"]
