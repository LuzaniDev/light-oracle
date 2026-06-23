import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import List


def _short_path(path: str) -> str:
    try:
        result = subprocess.run(
            ["cmd", "/c", f'for %A in ("{path}") do @echo %~sA'],
            capture_output=True, text=True, shell=True
        )
        short = result.stdout.strip()
        if short and os.path.exists(short):
            return short
    except Exception:
        pass
    return path


def _ascii_path(base: str) -> str:
    short = _short_path(base)
    if any(ord(c) > 127 for c in short):
        fallback = os.path.join(tempfile.gettempdir(), "light-oracle")
        return fallback
    return short


@dataclass
class OracleConfig:
    # Paths
    base_dir: str = ""
    models_dir: str = field(default="")
    indexes_dir: str = field(default="")
    data_dir: str = field(default="")

    # Embedding
    embed_model_name: str = "BAAI/bge-small-en-v1.5"
    embed_dim: int = 384
    embed_use_dim: int = 256
    embed_batch_size: int = 32
    embed_device: str = "cpu"

    # Reranker
    reranker_model_name: str = "cross-encoder/ms-marco-MiniLM-L-2-v2"
    reranker_batch_size: int = 16

    # Chunking
    chunk_size: int = 512
    chunk_overlap: int = 64

    # Retrieval
    bm25_top_k: int = 50
    dense_top_k: int = 50
    rrf_top_k: int = 30
    reranker_top_k: int = 10
    mmr_top_k: int = 5
    mmr_lambda: float = 0.7

    # Multi-Query
    num_queries: int = 3

    # Self-RAG thresholds
    confidence_high: float = 0.60
    confidence_medium: float = 0.40

    # FAISS
    faiss_nlist: int = 100
    faiss_nprobe: int = 10
    faiss_pq_m: int = 8
    faiss_pq_bits: int = 8

    # Cache
    cache_size: int = 100

    # SQLite
    sqlite_db_path: str = field(default="")

    def __post_init__(self):
        if not self.base_dir:
            raw = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            self.base_dir = _ascii_path(raw)
        self.models_dir = os.path.join(self.base_dir, "models")
        self.indexes_dir = os.path.join(self.base_dir, "indexes")
        self.data_dir = os.path.join(self.base_dir, "data")
        self.sqlite_db_path = os.path.join(self.indexes_dir, "oracle.db")
        os.makedirs(self.models_dir, exist_ok=True)
        os.makedirs(self.indexes_dir, exist_ok=True)
        os.makedirs(self.data_dir, exist_ok=True)
