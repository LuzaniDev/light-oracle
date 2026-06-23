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
        raw_scores = self.model.predict(pairs, batch_size=self.batch_size, show_progress_bar=False)
        if raw_scores.ndim == 0:
            raw_scores = np.array([float(raw_scores)])
        scores = np.array(raw_scores).flatten()
        min_s, max_s = scores.min(), scores.max()
        if max_s > min_s:
            normalized = (scores - min_s) / (max_s - min_s)
        elif max_s == 0:
            normalized = np.full_like(scores, 0.5)
        else:
            normalized = np.full_like(scores, 0.5)
        all_scores = list(zip(range(len(documents)), normalized.tolist()))
        all_scores.sort(key=lambda x: x[1], reverse=True)
        return all_scores[:top_k]
