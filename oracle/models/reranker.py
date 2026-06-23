import numpy as np
from typing import List, Tuple
from sentence_transformers import CrossEncoder


class Reranker:
    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-2-v2", batch_size: int = 16):
        self.model = CrossEncoder(model_name)
        self.batch_size = batch_size

    def rerank(self, query: str, documents: List[str], top_k: int = 10) -> List[Tuple[int, float]]:
        if not documents:
            return []
        pairs = [[query, doc] for doc in documents]
        scores = self.model.predict(pairs, batch_size=self.batch_size, show_progress_bar=False)
        if scores.ndim == 0:
            scores = np.array([float(scores)])
        scores = np.array(scores).flatten()
        top_indices = np.argsort(scores)[::-1][:top_k]
        return [(int(idx), float(scores[idx])) for idx in top_indices]
