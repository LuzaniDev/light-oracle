import numpy as np
from typing import List, Tuple, Dict, Optional
from .models.embedder import Embedder
from .models.reranker import Reranker
from .retrieval.bm25 import BM25Index
from .retrieval.dense import DenseIndex
from .retrieval.hyde import HyDEGenerator
from .retrieval.multi_query import MultiQueryGenerator
from .retrieval.hybrid import HybridFusion, MMR
from .pipeline.chunker import Chunker
from .utils.config import OracleConfig


class OracleEngine:
    def __init__(self, config: Optional[OracleConfig] = None):
        self.config = config or OracleConfig()
        self.embedder = Embedder(
            model_name=self.config.embed_model_name,
            use_dim=self.config.embed_use_dim,
            batch_size=self.config.embed_batch_size,
        )
        self.reranker = Reranker(
            model_name=self.config.reranker_model_name,
            batch_size=self.config.reranker_batch_size,
        )
        self.bm25 = BM25Index(self.config.sqlite_db_path)
        self.dense = DenseIndex(self.embedder, self.config.indexes_dir)
        self.hyde = HyDEGenerator()
        self.multi_query = MultiQueryGenerator(self.config.num_queries)
        self.fusion = HybridFusion(top_k=self.config.rrf_top_k)
        self.mmr = MMR(lambda_param=self.config.mmr_lambda, top_k=self.config.mmr_top_k)
        self.chunker = Chunker(
            chunk_size=self.config.chunk_size,
            chunk_overlap=self.config.chunk_overlap,
        )
        self._load_existing()

    def _load_existing(self):
        self.dense.load()
        if self.dense.chunks:
            texts = [c["text"] for c in self.dense.chunks]
            for i in range(0, len(texts), 50):
                batch = texts[i:i+50]
                batch_chunks = self.dense.chunks[i:i+50]
                self.bm25.add_documents(batch_chunks)

    def index_document(self, text: str, source: str = "unknown"):
        chunks = self.chunker.chunk_text(text, source)
        if not chunks:
            return 0
        self.bm25.add_documents(chunks)
        self.dense.add_chunks(chunks)
        self.dense.save()
        return len(chunks)

    def ask(self, query: str) -> Dict:
        analysis = self._analyze_query(query)
        self_rag_token = self._decide_retrieve(analysis)

        if self_rag_token == "[No Retrieve]":
            return self._build_response(query, [], [], "", "unknown", 0, "[No Retrieve]")

        hyde_query = self.hyde.generate(query)
        bm25_results = self.bm25.search(query, self.config.bm25_top_k)
        bm25_hyde = self.bm25.search(hyde_query, self.config.bm25_top_k // 2)
        seen_bm25 = {r[0] for r in bm25_results}
        for r in bm25_hyde:
            if r[0] not in seen_bm25:
                bm25_results.append(r)
                seen_bm25.add(r[0])

        hyde_results = self.dense.search(hyde_query, self.config.dense_top_k)
        multi_queries = self.multi_query.generate(query)
        all_dense = list(hyde_results)
        for mq in multi_queries[1:]:
            mq_results = self.dense.search(mq, self.config.dense_top_k // 2)
            seen_ids = {r[0] for r in all_dense}
            for r in mq_results:
                if r[0] not in seen_ids:
                    all_dense.append(r)
                    seen_ids.add(r[0])

        fused = self.fusion.fuse(bm25_results, all_dense)
        if not fused:
            return self._build_response(query, [], [], "", "unknown", 0, "[No Support]")

        doc_texts = [r[2] for r in fused]
        reranked = self.reranker.rerank(query, doc_texts, top_k=len(fused))
        reranked_results = [(fused[idx][0], score, fused[idx][2], fused[idx][3]) for idx, score in reranked]

        query_vec = self.embedder.encode_query(query)
        doc_embs = np.array([self.embedder.encode_query(r[2]) for r in reranked_results])
        diversified = self.mmr.diversify(reranked_results, query_vec, doc_embs)

        relevant_chunks, confidence = self._evaluate_chunks(query, diversified)

        if confidence >= self.config.confidence_high:
            decision = "[Supported]"
            answer = self._extract_answer(query, relevant_chunks)
        elif confidence >= self.config.confidence_medium:
            decision = "[Partially]"
            answer = self._extract_answer(query, relevant_chunks)
        elif confidence >= 0.40:
            decision = "[Partially]"
            answer = self._extract_answer(query, relevant_chunks)
            if len(answer) < 30:
                rewritten = self._rewrite_query(query)
                if rewritten != query:
                    return self.ask(rewritten)
        else:
            decision = "[No Support]"
            answer = "Não encontrei informação suficiente nos documentos disponíveis."

        return self._build_response(
            query, relevant_chunks, diversified, answer,
            self._get_main_source(diversified), confidence, decision
        )

    def _analyze_query(self, query: str) -> Dict:
        query_lower = query.lower()
        entities = []
        intent = "fact"
        if any(w in query_lower for w in ["qual", "quais", "quanto", "valor", "número", "código"]):
            intent = "value"
        elif any(w in query_lower for w in ["como", "procedimento", "passo", "etapa"]):
            intent = "procedure"
        elif any(w in query_lower for w in ["lista", "quais são", "liste", "enumere"]):
            intent = "list"
        elif any(w in query_lower for w in ["diferença", "comparar", "vs", "versus"]):
            intent = "comparison"
        return {"intent": intent, "entities": entities, "original": query}

    def _decide_retrieve(self, analysis: Dict) -> str:
        return "[Retrieve]"

    def _evaluate_chunks(self, query: str, chunks: List[Tuple]) -> Tuple[List[Tuple], float]:
        if not chunks:
            return [], 0.0

        rerank_scores = np.array([s[1] for s in chunks])
        min_s, max_s = rerank_scores.min(), rerank_scores.max()
        if max_s > min_s:
            rerank_norm = (rerank_scores - min_s) / (max_s - min_s)
        else:
            rerank_norm = np.full_like(rerank_scores, 0.5)

        query_vec = self.embedder.encode_query(query)
        relevant = []
        scores = []
        for i, (doc_id, _, text, source) in enumerate(chunks):
            doc_vec = self.embedder.encode_query(text[:512])
            sim = float(np.dot(query_vec, doc_vec))
            sim_norm = max(0.0, (sim + 1.0) / 2.0)
            combined = 0.6 * rerank_norm[i] + 0.4 * sim_norm
            if combined > 0.1:
                relevant.append((doc_id, combined, text, source))
                scores.append(combined)
        confidence = float(np.mean(scores)) if scores else 0.0
        relevant.sort(key=lambda x: x[1], reverse=True)
        return relevant[:5], confidence

    def _extract_answer(self, query: str, chunks: List[Tuple]) -> str:
        if not chunks:
            return ""
        import re
        query_words = set(re.findall(r'[A-Za-z0-9À-ÿ]+', query.lower()))
        query_numbers = set(re.findall(r'\d+', query))

        def score_sentence(sent: str) -> float:
            sent_lower = sent.lower()
            word_matches = sum(1 for w in query_words if len(w) > 2 and w in sent_lower)
            num_matches = sum(1 for n in query_numbers if n in sent)
            word_score = word_matches / max(len(query_words), 1)
            num_score = min(num_matches / max(len(query_numbers), 1), 1.0)
            return 0.5 * word_score + 0.5 * num_score

        all_sentences = []
        for c in chunks:
            text = c[2]
            raw_sents = re.split(r'(?<=[.!?\n])\s*', text)
            for s in raw_sents:
                s = s.strip()
                if s and len(s) > 15:
                    all_sentences.append((s, score_sentence(s)))

        all_sentences.sort(key=lambda x: x[1], reverse=True)
        best = [s[0] for s in all_sentences[:4] if s[1] > 0]

        if best:
            seen = set()
            unique = []
            for s in best:
                key = s[:50].lower()
                if key not in seen:
                    seen.add(key)
                    unique.append(s)
            return "\n".join(unique[:2])
        return chunks[0][2][:300]

    def _rewrite_query(self, query: str) -> str:
        return query

    def _get_main_source(self, results: List[Tuple]) -> str:
        if results:
            return results[0][3]
        return "unknown"

    def _build_response(self, query: str, relevant_chunks: List[Tuple],
                        all_chunks: List[Tuple], answer: str,
                        source: str, confidence: float, decision: str) -> Dict:
        return {
            "query": query,
            "answer": answer,
            "confidence": round(confidence, 3),
            "decision": decision,
            "source": source,
            "num_chunks": len(relevant_chunks),
            "chunks": [
                {"text": c[2][:300], "score": round(c[1], 3), "source": c[3]}
                for c in relevant_chunks[:3]
            ],
        }
