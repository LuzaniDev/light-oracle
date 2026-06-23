import numpy as np
import faiss
import os
import pickle
from typing import List, Tuple, Optional
from ..models.embedder import Embedder


class DenseIndex:
    def __init__(self, embedder: Embedder, index_dir: str):
        self.embedder = embedder
        self.index_dir = index_dir
        self.index: Optional[faiss.Index] = None
        self.chunks: List[dict] = []
        self.is_trained = False
        self.dimension = embedder.use_dim
        self.nlist = 100
        self.nprobe = 10
        self.pq_m = 8
        self.pq_bits = 8
        self._use_ivf = False

    def build_index(self, chunks: List[dict]):
        texts = [c["text"] for c in self.chunks] + [c["text"] for c in chunks]
        self.chunks.extend(chunks)
        return self._build_from_texts(texts)

    def _build_from_texts(self, texts: List[str]):
        if not texts:
            return
        embeddings = self.embedder.encode(texts)
        if self.index is None:
            n = embeddings.shape[0]
            if n >= self.nlist:
                self._use_ivf = True
                quantizer = faiss.IndexFlatIP(self.dimension)
                self.index = faiss.IndexIVFPQ(quantizer, self.dimension, self.nlist, self.pq_m, self.pq_bits)
                self.index.train(embeddings)
            else:
                self._use_ivf = False
                self.index = faiss.IndexFlatIP(self.dimension)
            self.is_trained = True
        self.index.add(embeddings)

    def add_chunks(self, chunks: List[dict]):
        texts = [c["text"] for c in chunks]
        embeddings = self.embedder.encode(texts)
        if self.index is None:
            self._build_from_texts(texts)
        else:
            n = self.index.ntotal
            total = n + embeddings.shape[0]
            if not self._use_ivf and total >= self.nlist:
                old_chunks = self.chunks[:n]
                all_texts = [c["text"] for c in old_chunks] + texts
                all_embs = self.embedder.encode(all_texts)
                self.index = faiss.IndexFlatIP(self.dimension)
                self.index.add(all_embs)
                self._use_ivf = False
            else:
                self.index.add(embeddings)
        self.chunks.extend(chunks)

    def search(self, query: str, top_k: int = 50) -> List[Tuple[int, float, str, str]]:
        if self.index is None or self.index.ntotal == 0:
            return []
        query_vec = self.embedder.encode_query(query).reshape(1, -1)
        if self._use_ivf:
            self.index.nprobe = self.nprobe
        scores, indices = self.index.search(query_vec, min(top_k, self.index.ntotal))
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx >= 0 and idx < len(self.chunks):
                chunk = self.chunks[idx]
                results.append((int(idx), float(score), chunk["text"], chunk["source"]))
        return results

    def save(self, name: str = "dense_index"):
        if self.index is None:
            return
        index_path = os.path.join(self.index_dir, f"{name}.faiss")
        chunks_path = os.path.join(self.index_dir, f"{name}_chunks.pkl")
        faiss.write_index(self.index, index_path)
        with open(chunks_path, "wb") as f:
            pickle.dump(self.chunks, f)

    def load(self, name: str = "dense_index"):
        index_path = os.path.join(self.index_dir, f"{name}.faiss")
        chunks_path = os.path.join(self.index_dir, f"{name}_chunks.pkl")
        if not os.path.exists(index_path):
            return False
        self.index = faiss.read_index(index_path)
        self.is_trained = True
        if os.path.exists(chunks_path):
            with open(chunks_path, "rb") as f:
                self.chunks = pickle.load(f)
        return True

    def clear(self):
        self.index = None
        self.chunks = []
        self.is_trained = False
