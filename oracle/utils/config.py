import os
import tempfile
import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict


def _expand_env(val: str) -> str:
    return os.path.expandvars(os.path.expanduser(val))


def _parse_cfg(path: str) -> Dict[str, str]:
    result = {}
    if not os.path.exists(path):
        return result
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("=") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip()
            if key and val:
                result[key] = _expand_env(val)
    return result


def load_config(path: Optional[str] = None) -> Dict[str, str]:
    if path is None:
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        path = os.path.join(base, "config.cfg")
    cfg = _parse_cfg(path)
    cfg.update(_parse_cfg(os.path.join(os.path.dirname(path), "config.local.cfg")))
    return cfg


CONFIG = load_config()


def cfg(key: str, default: str = "") -> str:
    return CONFIG.get(key, os.environ.get(key.replace("_", "ORACLE_"), default))


def cfg_int(key: str, default: int) -> int:
    try:
        return int(cfg(key, str(default)))
    except (ValueError, TypeError):
        return default


def cfg_float(key: str, default: float) -> float:
    try:
        return float(cfg(key, str(default)))
    except (ValueError, TypeError):
        return default


def cfg_bool(key: str, default: bool) -> bool:
    val = cfg(key, "").lower()
    if val in ("1", "true", "yes", "y", "sim", "s"):
        return True
    if val in ("0", "false", "no", "n", "nao", "nao"):
        return False
    return default


@dataclass
class OracleConfig:
    # Paths
    base_dir: str = field(default="")
    models_dir: str = field(default="")
    indexes_dir: str = field(default="")
    data_dir: str = field(default="")

    # Embedding
    embed_model_name: str = ""
    embed_dim: int = 384
    embed_use_dim: int = 256
    embed_batch_size: int = 0
    embed_device: str = "cpu"

    # Reranker
    reranker_model_name: str = ""
    reranker_batch_size: int = 0

    # Chunking
    chunk_size: int = 0
    chunk_overlap: int = 0

    # Retrieval
    bm25_top_k: int = 0
    dense_top_k: int = 0
    rrf_top_k: int = 0
    reranker_top_k: int = 0
    mmr_top_k: int = 0
    mmr_lambda: float = 0.0

    # Multi-Query
    num_queries: int = 0

    # Self-RAG thresholds
    confidence_high: float = 0.0
    confidence_medium: float = 0.0

    # FAISS
    faiss_nlist: int = 0
    faiss_nprobe: int = 0
    faiss_pq_m: int = 0
    faiss_pq_bits: int = 0

    # Web Fallback
    web_max_results: int = 0
    web_fallback_enabled: bool = False

    # Cache
    cache_size: int = 0

    # SQLite
    sqlite_db_path: str = field(default="")

    _DEFAULTS = {
        "embed_model_name": "BAAI/bge-small-en-v1.5",
        "reranker_model_name": "cross-encoder/ms-marco-MiniLM-L-2-v2",
        "embed_batch_size": 32,
        "reranker_batch_size": 16,
        "chunk_size": 512,
        "chunk_overlap": 64,
        "bm25_top_k": 50,
        "dense_top_k": 50,
        "rrf_top_k": 30,
        "reranker_top_k": 10,
        "mmr_top_k": 5,
        "mmr_lambda": 0.7,
        "num_queries": 3,
        "confidence_high": 0.60,
        "confidence_medium": 0.40,
        "faiss_nlist": 100,
        "faiss_nprobe": 10,
        "faiss_pq_m": 8,
        "faiss_pq_bits": 8,
        "web_max_results": 5,
        "web_fallback_enabled": True,
        "cache_size": 100,
    }

    _CFG_MAP = {
        "embed_model_name": ("EMBED_MODEL", str),
        "embed_use_dim": ("EMBED_DIM", int),
        "embed_batch_size": ("EMBED_BATCH", int),
        "reranker_model_name": ("RERANKER_MODEL", str),
        "reranker_batch_size": ("RERANKER_BATCH", int),
        "chunk_size": ("CHUNK_SIZE", int),
        "chunk_overlap": ("CHUNK_OVERLAP", int),
        "bm25_top_k": ("BM25_TOP_K", int),
        "dense_top_k": ("DENSE_TOP_K", int),
        "rrf_top_k": ("RRF_TOP_K", int),
        "num_queries": ("NUM_QUERIES", int),
        "confidence_high": ("CONFIDENCE_HIGH", float),
        "confidence_medium": ("CONFIDENCE_MEDIUM", float),
        "web_max_results": ("WEB_MAX_RESULTS", int),
        "web_fallback_enabled": ("WEB_FALLBACK", bool),
        "cache_size": ("CACHE_SIZE", int),
    }

    def __post_init__(self):
        if not self.base_dir:
            self.base_dir = cfg("BASE_DIR", os.path.join(tempfile.gettempdir(), "oracle-rag"))

        for field_name, (cfg_key, cast) in self._CFG_MAP.items():
            raw = cfg(cfg_key)
            if raw:
                try:
                    setattr(self, field_name, cast(raw))
                except (ValueError, TypeError):
                    pass

        for field_name, default_val in self._DEFAULTS.items():
            current = getattr(self, field_name)
            if isinstance(current, (int, float)) and current == 0:
                setattr(self, field_name, default_val)
            elif isinstance(current, str) and not current:
                setattr(self, field_name, default_val)
            elif isinstance(current, bool) and current is False and default_val is True:
                setattr(self, field_name, default_val)

        self.models_dir = os.path.join(self.base_dir, "models")
        self.indexes_dir = os.path.join(self.base_dir, "indexes")
        self.data_dir = os.path.join(self.base_dir, "data")
        self.sqlite_db_path = os.path.join(self.indexes_dir, "oracle.db")
        os.makedirs(self.models_dir, exist_ok=True)
        os.makedirs(self.indexes_dir, exist_ok=True)
        os.makedirs(self.data_dir, exist_ok=True)
