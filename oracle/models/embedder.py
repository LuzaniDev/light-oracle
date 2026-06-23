import numpy as np
from typing import List, Optional
from sentence_transformers import SentenceTransformer


class Embedder:
    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5", use_dim: int = 256, batch_size: int = 32):
        self.model = SentenceTransformer(model_name)
        self.full_dim = self.model.get_sentence_embedding_dimension()
        self.use_dim = min(use_dim, self.full_dim)
        self.batch_size = batch_size

    def encode(self, texts: List[str], normalize: bool = True) -> np.ndarray:
        embeddings = self.model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=normalize,
            show_progress_bar=False,
        )
        if self.use_dim < self.full_dim:
            embeddings = embeddings[:, :self.use_dim]
        return embeddings.astype(np.float32)

    def encode_query(self, query: str) -> np.ndarray:
        return self.encode([query], normalize=True)[0]

    def encode_queries(self, queries: List[str]) -> np.ndarray:
        return self.encode(queries, normalize=True)
