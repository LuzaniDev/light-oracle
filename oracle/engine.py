import numpy as np
import re
from typing import List, Tuple, Dict, Optional
from .models.embedder import Embedder
from .models.reranker import Reranker
from .retrieval.bm25 import BM25Index
from .retrieval.dense import DenseIndex
from .retrieval.hyde import HyDEGenerator
from .retrieval.multi_query import MultiQueryGenerator
from .retrieval.hybrid import HybridFusion, MMR
from .retrieval.web_fallback import WebFallback
from .pipeline.chunker import Chunker
from .pipeline.sql_connector import SQLConnector
from .utils.config import OracleConfig


class OracleEngine:
    def __init__(self, config: Optional[OracleConfig] = None):
        self.config = config or OracleConfig()
        self._embedder = None
        self._reranker = None
        self._embedder_loading = False
        self._reranker_loading = False
        self.bm25 = BM25Index(self.config.sqlite_db_path)
        self._dense = None
        self._dense_loaded = False
        self.hyde = HyDEGenerator()
        self.multi_query = MultiQueryGenerator(self.config.num_queries)
        self.fusion = HybridFusion(top_k=self.config.rrf_top_k)
        self.mmr = MMR(lambda_param=self.config.mmr_lambda, top_k=self.config.mmr_top_k)
        self.chunker = Chunker(
            chunk_size=self.config.chunk_size,
            chunk_overlap=self.config.chunk_overlap,
        )
        self.web = WebFallback(max_results=self.config.web_max_results)
        self.sql = SQLConnector()
        self._cached_ask = {}
        self._load_existing()

    @property
    def embedder(self):
        if self._embedder is None and not self._embedder_loading:
            self._embedder_loading = True
            self._embedder = Embedder(
                model_name=self.config.embed_model_name,
                use_dim=self.config.embed_use_dim,
                batch_size=self.config.embed_batch_size,
            )
        return self._embedder

    @embedder.setter
    def embedder(self, value):
        self._embedder = value

    @property
    def reranker(self):
        if self._reranker is None and not self._reranker_loading:
            self._reranker_loading = True
            self._reranker = Reranker(
                model_name=self.config.reranker_model_name,
                batch_size=self.config.reranker_batch_size,
            )
        return self._reranker

    @reranker.setter
    def reranker(self, value):
        self._reranker = value

    @property
    def dense(self):
        if self._dense is None:
            self._dense = DenseIndex(self.embedder, self.config.indexes_dir)
        return self._dense

    @dense.setter
    def dense(self, value):
        self._dense = value
        self._load_existing()

    def _load_existing(self):
        if not self._dense_loaded:
            if self._dense is None:
                self._dense = DenseIndex(self.embedder, self.config.indexes_dir)
            self._dense.load()
            self._dense_loaded = True
        if self._dense and self._dense.chunks:
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
        cache_key = query.lower().strip()
        if cache_key in self._cached_ask:
            return self._cached_ask[cache_key]

        sql_result = self._try_sql_query(query)
        if sql_result:
            self._cached_ask[cache_key] = sql_result
            return sql_result

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
        fused = self._filter_schema_chunks(fused)
        if not fused:
            bm25_simple = self.bm25.search(query, self.config.bm25_top_k * 2)
            if bm25_simple:
                fused = bm25_simple[:5]
            else:
                content_count = self.bm25.get_document_count()
                if content_count == 0:
                    return self._build_response(query, [], [], "Nenhum documento foi indexado ainda. Faca upload de um arquivo primeiro.", "", 0, "[No Support]")
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
        else:
            web_result = self._web_fallback(query)
            if web_result["decision"] != "[No Support]" and web_result.get("answer"):
                return web_result
            decision = "[No Support]"
            answer = "Nao encontrei informacao suficiente nos documentos disponiveis."

        result = self._build_response(
            query, relevant_chunks, diversified, answer,
            self._get_main_source(diversified), confidence, decision
        )
        self._cached_ask[cache_key] = result
        return result

    def _filter_schema_chunks(self, chunks: List[Tuple]) -> List[Tuple]:
        filtered = []
        for c in chunks:
            source = c[3] if len(c) > 3 else ""
            text = c[2] if len(c) > 2 else ""
            if source.startswith("sql_schema:"):
                continue
            if source.startswith("sql_query:"):
                continue
            field_like = re.findall(r'^[a-z_]+\d*:\s', text.strip()[:40])
            if field_like and len(field_like) >= 3:
                continue
            colon_count = text.count(":")
            total_lines = text.count("\n") + 1
            if colon_count > 30 and total_lines < colon_count / 2:
                continue
            filtered.append(c)
        if not filtered and chunks:
            filtered = [c for c in chunks if not c[3].startswith("sql_")]
        if not filtered:
            filtered = chunks[:3]
        return filtered

    def _try_sql_query(self, query: str) -> Optional[Dict]:
        db_names = self.sql.list_databases()
        if not db_names:
            return None
        keywords = ["quanto", "quantos", "qual", "quais", "lista", "liste", "mostre",
                     "valor", "total", "dados", "informacao", "cadastro", "tabela",
                     "cliente", "produto", "pedido", "venda", "estoque", "fornecedor",
                     "nf", "nota", "fiscal", "preco", "custo", "saldo", "estoque"]
        query_lower = query.lower()
        if not any(k in query_lower for k in keywords):
            return None
        return self._generate_and_execute_sql(query, db_names[0])

    def _generate_and_execute_sql(self, query: str, db_name: str) -> Optional[Dict]:
        schema = self.sql.schemas.get(db_name, [])
        if not schema:
            return None

        tables = [t for t in schema if not t["table"].startswith("ECO$")]
        query_lower = query.lower()

        table_scores = []
        for t in tables:
            name = t["table"].lower()
            score = 0
            for col in t["columns"]:
                col_lower = col.lower()
                if any(w in col_lower for w in query_lower.split() if len(w) > 3):
                    score += 2
            words_in_name = set(re.findall(r'[a-z0-9]+', name))
            for q_word in re.findall(r'[a-z0-9]+', query_lower):
                if len(q_word) > 3 and q_word in words_in_name:
                    score += 5
            if score > 0:
                table_scores.append((t, score))

        table_scores.sort(key=lambda x: x[1], reverse=True)
        if not table_scores:
            return None

        best_table = table_scores[0][0]
        table_name = best_table["table"]
        columns = best_table["columns"]

        where_clauses = []
        search_terms = [w for w in re.findall(r'[a-z0-9]+', query_lower) if len(w) > 3]

        for term in search_terms:
            relevant_cols = [c for c in columns if any(k in c.lower() for k in
                            ["descricao", "nome", "fantasia", "produto", "titulo",
                             "resumo", "observacao", "marca", "modelo", "codigo"])]
            if relevant_cols:
                col = relevant_cols[0]
                where_clauses.append(f"UPPER({col}) LIKE UPPER('%{term}%')")

        numbers = re.findall(r'\d+', query)
        num_cols = [c for c in columns if any(k in c.lower() for k in
                   ["codigo", "numero", "id", "gid", "pedido", "nota", "documento"])]
        if numbers and num_cols:
            where_clauses.append(f"{num_cols[0]} = {numbers[0]}")

        aggregate = ""
        if any(w in query_lower for w in ["quantos", "quantas", "total de", "numero de", "conta"]):
            if "COUNT" not in aggregate and "quant" in query_lower:
                aggregate = "COUNT(*)"
        else:
            limit_cols = [c for c in [c for c in columns if c.lower() not in
                         ["senha", "password", "hash", "token", "foto", "imagem", "logotipo"]][:8]]
            aggregate = ", ".join(limit_cols) if limit_cols else "*"

        if aggregate == "COUNT(*)":
            sql = f"SELECT COUNT(*) AS total FROM {table_name}"
        else:
            sql = f"SELECT {aggregate} FROM {table_name}"

        if where_clauses:
            sql += " WHERE " + " OR ".join(where_clauses[:3])

        if aggregate != "COUNT(*)":
            sql += " FETCH FIRST 10 ROWS ONLY"

        try:
            rows = self.sql.execute_query(db_name, sql)
        except Exception as e:
            try:
                sql_simple = f"SELECT COUNT(*) AS total FROM {table_name}"
                rows = self.sql.execute_query(db_name, sql_simple)
            except Exception:
                return None

        if not rows:
            return {"query": query, "answer": "Nenhum resultado encontrado no banco.",
                    "confidence": 0.0, "decision": "[Partially]", "source": db_name,
                    "chunks": [{"text": sql, "score": 1.0, "source": db_name}]}

        formatted = self._format_sql_result(rows, sql, table_name, query)
        return {"query": query, "answer": formatted, "confidence": 0.85,
                "decision": "[Supported]", "source": f"sql:{table_name}",
                "chunks": [{"text": f"Query: {sql}", "score": 1.0, "source": db_name}]}

    def _format_sql_result(self, rows: List[Dict], sql: str, table: str, query: str) -> str:
        if not rows:
            return "Nenhum resultado."
        if len(rows) == 1 and "total" in rows[0] and "COUNT" in sql:
            count = rows[0]["total"]
            table_pt = table.replace("trec", "").replace("tspd", "").replace("ger", "")
            return f"Total encontrado: {count} registro(s) na tabela {table_pt}."

        lines = []
        for row in rows[:8]:
            parts = []
            for k, v in row.items():
                k_clean = k.replace("_", " ").capitalize()
                if k.lower() in ("senha", "password", "hash", "token", "foto"):
                    continue
                if v is None:
                    continue
                val_str = str(v)[:60]
                parts.append(f"{k_clean}: {val_str}")
            if parts:
                lines.append(" | ".join(parts))

        if len(rows) > 8:
            lines.append(f"... e mais {len(rows) - 8} registro(s)")

        return "\n".join(lines) if lines else str(rows[0])

    def _analyze_query(self, query: str) -> Dict:
        query_lower = query.lower()
        intent = "fact"
        if any(w in query_lower for w in ["qual", "quais", "quanto", "valor", "numero", "codigo"]):
            intent = "value"
        elif any(w in query_lower for w in ["como", "procedimento", "passo", "etapa"]):
            intent = "procedure"
        elif any(w in query_lower for w in ["lista", "quais sao", "liste", "enumere", "mostre"]):
            intent = "list"
        elif any(w in query_lower for w in ["diferenca", "comparar", "vs", "versus"]):
            intent = "comparison"
        return {"intent": intent, "entities": [], "original": query}

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
            if source.startswith("sql_schema:") or source.startswith("sql_query:"):
                continue
            doc_vec = self.embedder.encode_query(text[:512])
            sim = float(np.dot(query_vec, doc_vec))
            sim_norm = max(0.0, (sim + 1.0) / 2.0)
            combined = 0.6 * rerank_norm[i] + 0.4 * sim_norm
            relevant.append((doc_id, combined, text, source))
            scores.append(combined)

        if not relevant and chunks:
            for i, (doc_id, _, text, source) in enumerate(chunks):
                if not source.startswith("sql_"):
                    relevant.append((doc_id, 0.15, text, source))
                    scores.append(0.15)
                    if len(relevant) >= 3:
                        break

        confidence = float(np.mean(scores)) if scores else 0.0
        relevant.sort(key=lambda x: x[1], reverse=True)
        return relevant[:5], confidence

    def _extract_answer(self, query: str, chunks: List[Tuple]) -> str:
        if not chunks:
            return ""
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
                if s and len(s) > 15 and ":" not in s[:5]:
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

    def connect_sqlite(self, db_path: str) -> str:
        name = self.sql.connect_sqlite(db_path)
        return name

    def connect_firebird(self, db_path: str, host: str = "localhost",
                         user: str = "SYSDBA", password: str = "masterkey") -> str:
        name = self.sql.connect_firebird(db_path, user=user, password=password, host=host)
        return name

    def connect_mysql(self, host: str, port: int, user: str, password: str, database: str) -> str:
        name = self.sql.connect_mysql(host, port, user, password, database)
        return name

    def query_sql(self, conn_name: str, sql: str) -> str:
        return self.sql.query_to_text(conn_name, sql)

    def _web_fallback(self, query: str) -> Dict:
        if not self.config.web_fallback_enabled:
            return {"query": query, "answer": "", "decision": "[No Support]", "confidence": 0.0, "source": "web"}
        results = self.web.search_and_fetch(query)
        if not results:
            return {"query": query, "answer": "", "decision": "[No Support]", "confidence": 0.0, "source": "web"}
        chunks = []
        for i, r in enumerate(results):
            content = r.get("content", "") or r.get("snippet", "")
            if content:
                chunks.append({"id": i, "text": content, "source": r.get("url", f"web_{i}"), "tokens": len(content.split())})
                self.bm25.add_documents([chunks[-1]])
                self.dense.add_chunks([chunks[-1]])
        if not chunks:
            return {"query": query, "answer": "", "decision": "[No Support]", "confidence": 0.0, "source": "web"}
        response = self.ask(query)
        if response["confidence"] < 0.3:
            best = max(chunks, key=lambda c: len(c["text"]))
            return {"query": query, "answer": best["text"][:500], "decision": "[Partially]",
                    "confidence": 0.35, "source": results[0].get("url", "web"), "mode": "web_fallback"}
        return response

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

    def clear_cache(self):
        self._cached_ask.clear()
