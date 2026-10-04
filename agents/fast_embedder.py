from pathlib import Path

import numpy as np

CACHE_DIR = Path(__file__).resolve().parent.parent / "models_cache"


class FastEmbedder:
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        from fastembed import TextEmbedding

        CACHE_DIR.mkdir(exist_ok=True)
        self._model = TextEmbedding(model_name=model_name, cache_dir=str(CACHE_DIR))

    def encode(self, texts, normalize_embeddings: bool = True):
        if isinstance(texts, str):
            texts = [texts]
        vectors = np.array(list(self._model.embed(list(texts))), dtype="float32")
        if normalize_embeddings:
            norms = np.linalg.norm(vectors, axis=1, keepdims=True)
            vectors = vectors / np.where(norms == 0, 1, norms)
        return vectors