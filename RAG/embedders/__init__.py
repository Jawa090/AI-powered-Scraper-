"""
RAG Embedder Registry
Complies with P10.4:
- EMBEDDERS = {} ("add ONE line per provider")
- get_embedder() returns None when RAG_EMBEDDING_PROVIDER is empty -> state not_configured
- No fallback embedder
"""
from typing import Dict, Optional, Type
from RAG.embedders.base import BaseEmbedder

# Registry of supported embedding providers.
# Add ONE line per provider:
EMBEDDERS: Dict[str, Type[BaseEmbedder]] = {
    # "openai": OpenAIEmbedder,
    # "gemini": GeminiEmbedder,
}


def get_embedder(provider: Optional[str] = None, model: Optional[str] = None) -> Optional[BaseEmbedder]:
    """
    Instantiate embedder for given provider and model.
    Returns None if provider is empty, None, or not registered.
    Never uses a fallback embedder.
    """
    if not provider or not provider.strip():
        return None

    key = provider.strip().lower()
    embedder_cls = EMBEDDERS.get(key)
    if embedder_cls is None:
        return None

    return embedder_cls(model=model or "")
