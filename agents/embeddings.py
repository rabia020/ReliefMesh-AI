"""Sentence-embedding helper for the Verification Agent (Phase 8).

Uses Sentence Transformers, per your spec. The model loads lazily (only the
first time it's actually needed) and only once per process — loading it is
the slow part; encoding a handful of reports after that is fast even on a
laptop CPU. It downloads its weights from Hugging Face the first time you
run it, then caches them locally, so it needs internet once, not every run.
"""

DEFAULT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

_MODEL = None


def get_model_name() -> str:
    from backend import config
    return getattr(config, "EMBEDDING_MODEL", DEFAULT_MODEL_NAME)


def get_embedder():
    """Loads (once) and returns the real sentence-transformers model.
    Tests never call this — they inject a fake embedder instead."""
    global _MODEL
    if _MODEL is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as error:
            raise RuntimeError(
                "sentence-transformers is not installed. Run: pip install sentence-transformers"
            ) from error
        _MODEL = SentenceTransformer(get_model_name())
    return _MODEL


def embed_texts(texts, embedder=None):
    """Returns one normalized (unit-length) embedding vector per text.
    Because vectors are normalized, cosine similarity between two of them
    is just their dot product — see agents/verification_agent.py."""
    model = embedder or get_embedder()
    vectors = model.encode(list(texts), normalize_embeddings=True)
    return [[float(x) for x in vector] for vector in vectors]