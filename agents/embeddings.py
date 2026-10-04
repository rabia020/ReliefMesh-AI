"""Sentence-embedding helper.

The model loads lazily (only the first time it is needed) and only once per
process. It downloads its weights the first time it runs, then caches them
locally, so it needs internet once, not every run.

The light fastembed runtime is used when it is installed (for example on the
hosted backend). Otherwise sentence-transformers is used.
"""

DEFAULT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

_MODEL = None


def get_model_name() -> str:
    from backend import config
    return getattr(config, "EMBEDDING_MODEL", DEFAULT_MODEL_NAME)


def get_embedder():
    """Loads (once) and returns the embedding model.
    Tests never call this. They inject a fake embedder instead."""
    global _MODEL
    if _MODEL is None:
        try:
            from agents.fast_embedder import FastEmbedder

            _MODEL = FastEmbedder(get_model_name())
        except ImportError:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as error:
                raise RuntimeError(
                    "No embedding library is installed. Run: pip install fastembed"
                ) from error
            _MODEL = SentenceTransformer(get_model_name())
    return _MODEL


def embed_texts(texts, embedder=None):
    """Returns one normalized (unit-length) embedding vector per text.
    Because vectors are normalized, cosine similarity between two of them
    is just their dot product. See agents/verification_agent.py."""
    model = embedder or get_embedder()
    vectors = model.encode(list(texts), normalize_embeddings=True)
    return [[float(x) for x in vector] for vector in vectors]