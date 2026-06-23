import numpy as np
from typing import List, Tuple, Dict


class HybridFusion:
    def __init__(self, bm25_weight: float = 1.0, dense_weight: float = 1.0, top_k: int = 30):
        self.bm25_weight = bm25_weight
        self.dense_weight = dense_weight
        self.top_k = top_k

    def fuse(self, bm25_results: List[Tuple], dense_results: List[Tuple]) -> List[Tuple[int, float, str, str]]:
        scores: Dict[int, float] = {}
        texts: Dict[int, str] = {}
        sources: Dict[int, str] = {}

        for rank, (doc_id, score, text, source) in enumerate(bm25_results):
            rrf_score = self.bm25_weight / (60 + rank)
            scores[doc_id] = scores.get(doc_id, 0) + rrf_score
            texts[doc_id] = text
            sources[doc_id] = source

        for rank, (doc_id, score, text, source) in enumerate(dense_results):
            rrf_score = self.dense_weight / (60 + rank)
            scores[doc_id] = scores.get(doc_id, 0) + rrf_score
            texts[doc_id] = text
            sources[doc_id] = source

        sorted_docs = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        results = []
        for doc_id, score in sorted_docs[:self.top_k]:
            results.append((doc_id, score, texts.get(doc_id, ""), sources.get(doc_id, "")))
        return results


class MMR:
    def __init__(self, lambda_param: float = 0.7, top_k: int = 5):
        self.lambda_param = lambda_param
        self.top_k = top_k

    def diversify(self, results: List[Tuple[int, float, str, str]], query_emb: np.ndarray,
                  doc_embeddings: np.ndarray) -> List[Tuple[int, float, str, str]]:
        if not results or len(results) <= self.top_k:
            return results

        selected = []
        candidate_indices = list(range(len(results)))
        query_emb_norm = query_emb / (np.linalg.norm(query_emb) + 1e-10)

        for _ in range(min(self.top_k, len(results))):
            mmr_scores = []
            for idx in candidate_indices:
                doc_emb = doc_embeddings[idx]
                doc_norm = doc_emb / (np.linalg.norm(doc_emb) + 1e-10)
                sim_to_query = float(np.dot(query_emb_norm, doc_norm))

                max_sim_to_selected = 0.0
                for sel_idx in selected:
                    sel_emb = doc_embeddings[sel_idx]
                    sel_norm = sel_emb / (np.linalg.norm(sel_emb) + 1e-10)
                    sim = float(np.dot(doc_norm, sel_norm))
                    max_sim_to_selected = max(max_sim_to_selected, sim)

                mmr = self.lambda_param * sim_to_query - (1 - self.lambda_param) * max_sim_to_selected
                mmr_scores.append((idx, mmr))

            if not mmr_scores:
                break
            best_idx = max(mmr_scores, key=lambda x: x[1])[0]
            selected.append(best_idx)
            candidate_indices.remove(best_idx)

        return [results[idx] for idx in selected]
