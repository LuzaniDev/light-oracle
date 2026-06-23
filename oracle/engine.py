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
        self.full_docs: Dict[str, str] = {}
        self._last_doc_sections: List[str] = []
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

    @property
    def is_ready(self) -> bool:
        return bool(self.full_docs) or bool(self.dense.chunks)

    @property
    def available_sections(self) -> List[str]:
        seen = set()
        sections = []
        for c in self.dense.chunks:
            s = c.get("section", "geral")
            if s not in seen:
                seen.add(s)
                sections.append(s)
        return sections or self._last_doc_sections

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
            for c in self.dense.chunks:
                src = c.get("source", "unknown")
                if src not in self.full_docs:
                    self.full_docs[src] = c["text"]
                else:
                    self.full_docs[src] += "\n" + c["text"]

    def index_document(self, text: str, source: str = "unknown"):
        raw_chunks = self.chunker.chunk_text(text, source)
        if not raw_chunks:
            return 0
        self.full_docs[source] = text
        self._last_doc_sections = list(set(c.get("section", "") for c in raw_chunks if c.get("section")))
        self.bm25.add_documents(raw_chunks)
        self.dense.add_chunks(raw_chunks)
        self.dense.save()
        self._cached_ask.clear()
        return len(raw_chunks)

    def ask(self, query: str) -> Dict:
        cache_key = query.lower().strip()
        if cache_key in self._cached_ask:
            return self._cached_ask[cache_key]

        sql_result = self._try_sql_query(query)
        if sql_result:
            self._cached_ask[cache_key] = sql_result
            return sql_result

        if not self.is_ready:
            return self._build_response(query, [], [], "Nenhum documento foi carregado ainda. Faca upload de um arquivo primeiro.", "", 0, "[No Support]", [])

        analysis = self._analyze_query(query)
        intent = analysis.get("intent", "general")
        entities = analysis.get("entities", [])
        entities_text = " ".join(entities)

        search_query = query
        if intent == "list":
            search_query += " " + " ".join(entities) + " " + " ".join(entities * 2)
        if intent in ("list", "count"):
            table_chunks = self._find_table_chunks()
            if table_chunks:
                table_answer = self._extract_by_intent(intent, query, table_chunks, analysis)
                if table_answer:
                    result = self._build_response(query, table_chunks, table_chunks, table_answer, table_chunks[0].get("source", "unknown"), 0.75, "[Supported]", self.available_sections)
                    self._cached_ask[cache_key] = result
                    return result

        hyde_query = self.hyde.generate(query)
        bm25_results = self.bm25.search(search_query, self.config.bm25_top_k)
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
            return self._fallback_fulltext(query, intent)

        doc_texts = [r[2] for r in fused]
        reranked = self.reranker.rerank(search_query, doc_texts, top_k=len(fused))
        reranked_results = [(fused[idx][0], score, fused[idx][2], fused[idx][3]) for idx, score in reranked]

        query_vec = self.embedder.encode_query(query)
        doc_embs = np.array([self.embedder.encode_query(r[2]) for r in reranked_results])
        diversified = self.mmr.diversify(reranked_results, query_vec, doc_embs)

        relevant_chunks, confidence = self._evaluate_chunks(query, diversified)

        answer = self._extract_by_intent(intent, query, relevant_chunks, analysis)
        if not answer and diversified:
            answer = self._extract_by_intent(intent, query, diversified[:3], analysis)
        if not answer:
            answer = self._fallback_fulltext_answer(query, intent)

        if answer:
            decision = "[Supported]" if confidence >= 0.45 else "[Partially]"
            result = self._build_response(query, relevant_chunks, diversified, answer, self._get_main_source(diversified), confidence, decision, self.available_sections)
            self._cached_ask[cache_key] = result
            return result

        web_result = self._web_fallback(query)
        if web_result["decision"] != "[No Support]" and web_result.get("answer"):
            return web_result

        sections = self.available_sections
        msg = "Nao encontrei informacao suficiente."
        if sections:
            msg += f" Documento possui secoes: {', '.join(sections)}. Tente perguntar de forma mais especifica."
        result = self._build_response(query, [], [], msg, "", 0, "[No Support]", sections)
        self._cached_ask[cache_key] = result
        return result

    def _find_table_chunks(self) -> List[Tuple]:
        results = []
        seen = set()
        for i, c in enumerate(self.dense.chunks):
            if c.get("tag") == "table":
                uid = id(c["text"])
                if uid not in seen:
                    seen.add(uid)
                    chunk_text = c["text"]
                    chunk_source = c.get("source", "unknown")
                    results.append((i, 1.0, chunk_text, chunk_source))
        return results

    def _fallback_fulltext(self, query: str, intent: str) -> Dict:
        answer = self._fallback_fulltext_answer(query, intent)
        if answer:
            return self._build_response(query, [], [], answer, "full_text", 0.40, "[Partially]", self.available_sections)
        sections = self.available_sections
        msg = "Nao encontrei informacao suficiente nos documentos."
        if sections:
            msg += f" Seccoes disponiveis: {', '.join(sections)}"
        return self._build_response(query, [], [], msg, "", 0, "[No Support]", sections)

    def _fallback_fulltext_answer(self, query: str, intent: str) -> str:
        if not self.full_docs:
            return ""
        query_lower = query.lower()
        words = [w for w in re.findall(r'[a-zA-Z0-9\u00C0-\u00FF]+', query_lower) if len(w) > 2]
        if not words:
            return ""

        best_score = 0
        best_para = ""
        best_section = ""

        for source, doc_text in self.full_docs.items():
            paragraphs = re.split(r'\n\s*\n', doc_text)
            for para in paragraphs:
                para_lower = para.lower()
                score = sum(1 for w in words if w in para_lower)
                if score > best_score:
                    best_score = score
                    best_para = para.strip()
                    best_section = source

        if best_para:
            lines = [l.strip() for l in best_para.split("\n") if l.strip()]
            if intent in ("list", "count"):
                data_lines = [l for l in lines if not re.match(r'^[A-Z\s]{3,}$', l) and len(l) > 10]
                if data_lines:
                    return "\n".join(data_lines[:10])
            return best_para[:500]
        return ""

    STOP_WORDS = {"qual", "quanto", "quais", "como", "onde", "quando", "quem", "porque",
                   "valor", "preco", "total", "custa", "custou", "sao", "dos", "das", "do",
                   "da", "para", "com", "tem", "uma", "uma", "numa", "pelo", "pela",
                   "entre", "sobre", "apos", "ate", "sem", "sob", "tipo", "forma",
                   "lista", "liste", "mostre", "diga", "fale", "conte", "informe",
                   "nota", "fiscal", "documento", "arquivo", "tabela", "numero"}

    def _analyze_query(self, query: str) -> Dict:
        query_lower = query.lower()
        intent = "general"
        entities = []
        product_name = ""

        list_words = ["lista", "liste", "listar", "quais", "quais sao", "enumere", "mostre",
                      "itens", "produtos", "relacao", "todos", "relacione"]
        if any(w in query_lower for w in list_words):
            intent = "list"

        count_words = ["quantos", "quantas", "total de", "numero de", "conta", "contagem"]
        if any(w in query_lower for w in count_words):
            intent = "count"

        value_words = ["qual", "quanto", "quanto custa", "valor", "preco", "total",
                       "saldo", "custou", "custa", "custo"]
        if any(w in query_lower for w in value_words):
            if intent == "general":
                intent = "value"

        entity_words = ["destinatario", "emitente", "remetente", "cliente",
                        "fornecedor", "transportadora", "vendedor", "produto"]
        for w in entity_words:
            if w in query_lower:
                entities.append(w)
                if intent == "general":
                    intent = "entity"

        for word in re.findall(r'[a-zA-Z\u00C0-\u00FF]+', query_lower):
            if len(word) > 3:
                entities.append(word)
                if word not in self.STOP_WORDS:
                    if not product_name and word not in ("geral",):
                        product_name = word

        return {"intent": intent, "entities": list(set(entities)), "original": query, "product": product_name}

    def _extract_by_intent(self, intent: str, query: str, chunks: List[Tuple], analysis: Dict) -> str:
        if not chunks:
            return ""
        if intent == "list":
            return self._extract_list(query, chunks)
        elif intent == "count":
            return self._extract_count(query, chunks)
        elif intent == "value":
            return self._extract_value(query, chunks)
        elif intent == "entity":
            return self._extract_entity(query, chunks, analysis.get("entities", []))
        else:
            return self._extract_answer(query, chunks)

    def _format_product_line(self, line: str) -> Optional[str]:
        parts = re.split(r'\s{2,}', line.strip())
        if len(parts) >= 4:
            name = parts[0].strip()
            qty = parts[1].strip()
            price = parts[2].strip()
            total = parts[3].strip()
            if re.search(r'\d', qty) and re.search(r'[Rr]\$', price):
                t = re.sub(r'^.*?(R\$\s*[\d,.]+)', r'\1', total) if 'R$' not in parts[3] else parts[3].strip()
                return f"{name} — {qty} un x {price} = {t}"
        if len(parts) >= 3:
            name = parts[0].strip()
            rest = " — ".join(p.strip() for p in parts[1:] if p.strip())
            return f"{name} — {rest}"
        if "  " in line:
            parts2 = re.split(r'\s{2,}', line)
            return " — ".join(p.strip() for p in parts2 if p.strip())
        return None

    def _extract_list(self, query: str, chunks: List[Tuple]) -> str:
        product_name = self._get_query_product(query.lower())
        seen = set()
        products = []
        for _, _, text, _ in chunks:
            for line in text.split("\n"):
                line = line.strip()
                if not line or len(line) < 5:
                    continue
                if re.match(r'^(?:nota|fiscal|cnpj|inscricao|destinatario|emitente|produtos)', line, re.IGNORECASE):
                    continue
                if not re.search(r'\d+', line):
                    continue
                if product_name and product_name not in line.lower():
                    continue
                key = line[:60].lower()
                if key in seen:
                    continue
                seen.add(key)
                formatted = self._format_product_line(line)
                if formatted:
                    products.append(formatted)

        if products:
            return "\n".join(products[:20])

        all_text = "\n".join(t for _, _, t, _ in chunks)
        raw_lines = [l.strip() for l in all_text.split("\n") if l.strip() and len(l.strip()) > 5]
        seen2 = set()
        items = []
        for line in raw_lines:
            if re.match(r'^[A-Z\s]{5,}$', line):
                continue
            if re.search(r'\d+', line):
                if product_name and product_name not in line.lower():
                    continue
                key2 = line[:50].lower()
                if key2 not in seen2:
                    seen2.add(key2)
                    items.append(line)
        return "\n".join(items[:15]) if items else ""

    def _extract_count(self, query: str, chunks: List[Tuple]) -> str:
        all_text = "\n".join(t for _, _, t, _ in chunks)
        lines = [l.strip() for l in all_text.split("\n") if l.strip()]
        item_lines = [l for l in lines if re.search(r'\d+', l) and not re.match(r'^(?:nota|cnpj|inscricao)', l, re.IGNORECASE)]
        count = len(item_lines)
        if count > 0:
            return f"Total de {count} itens encontrados."
        return ""

    def _extract_value(self, query: str, chunks: List[Tuple]) -> str:
        query_lower = query.lower()
        query_words = set(re.findall(r'[a-zA-Z\u00C0-\u00FF]+', query_lower))
        keywords = [w for w in query_words if len(w) > 2]
        product_name = self._get_query_product(query_lower)

        all_text = "\n".join(t for _, _, t, _ in chunks)
        lines = [l.strip() for l in all_text.split("\n") if l.strip()]

        if product_name:
            product_lines = [l for l in lines if product_name.lower() in l.lower()]
            if not product_lines:
                product_lines = [l for l in lines if any(k.lower() in l.lower() for k in keywords if len(k) > 3)]
        else:
            product_lines = []

        if product_lines:
            formatted_products = []
            for pline in product_lines:
                fp = self._format_product_line(pline)
                if fp:
                    formatted_products.append(fp)
                else:
                    formatted_products.append(pline)
            return "\n".join(formatted_products[:5])

        money_values = re.findall(r'[Rr]\$\s*[\d,.]+', all_text)
        if money_values:
            if len(money_values) <= 3:
                return f"Valores: {', '.join(money_values)}"
            last = money_values[-1]
            return f"Valores: {', '.join(money_values[:4])} ... Total: {last}"

        return "Valor nao encontrado no documento."

    def _extract_entity(self, query: str, chunks: List[Tuple], entities: List[str]) -> str:
        entity = entities[0].lower() if entities else ""
        relevant = []
        field_pattern = re.compile(rf'{{entity}}[\s:]*', re.IGNORECASE) if entity else None
        for _, _, text, _ in chunks:
            for line in text.split("\n"):
                line = line.strip()
                if not line:
                    continue
                if entity and entity in line.lower():
                    relevant.append(line)
                    continue
                if re.match(r'^(?:razao\s*social|cnpj|cpf|endereco|inscricao|nome|fantasia)', line, re.IGNORECASE):
                    relevant.append(line)
        if relevant:
            seen_key = set()
            unique = []
            for line in relevant:
                key = line[:40].lower()
                if key not in seen_key:
                    seen_key.add(key)
                    unique.append(line)
            return "\n".join(unique[:8])
        return ""

    def _extract_answer(self, query: str, chunks: List[Tuple]) -> str:
        if not chunks:
            return ""
        query_words = set(re.findall(r'[A-Za-z0-9\u00C0-\u00FF]+', query.lower()))
        query_numbers = set(re.findall(r'\d+', query))

        def score_line(line: str) -> float:
            lower = line.lower()
            word_matches = sum(1 for w in query_words if len(w) > 2 and w in lower)
            num_matches = sum(1 for n in query_numbers if n in line)
            word_score = word_matches / max(len(query_words), 1)
            num_score = min(num_matches / max(len(query_numbers), 1), 1.0)
            return 0.5 * word_score + 0.5 * num_score

        seen = set()
        scored_lines = []
        for _, _, text, _ in chunks:
            for line in text.replace("\r", "").split("\n"):
                line = line.strip()
                if not line or len(line) < 8:
                    continue
                if re.match(r'^[A-Z\s]{5,}$', line):
                    continue
                key = line[:40].lower()
                if key in seen:
                    continue
                seen.add(key)
                s = score_line(line)
                if s > 0:
                    scored_lines.append((s, line))

        scored_lines.sort(key=lambda x: x[1], reverse=True)
        best_lines = [l for _, l in scored_lines[:3]]
        return "\n".join(best_lines) if best_lines else (chunks[0][2][:300] if chunks else "")

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
        query_lower = query.lower()
        query_content_words = {w for w in re.findall(r'[a-zA-Z\u00C0-\u00FF]+', query_lower) if len(w) > 2}

        relevant = []
        scores = []
        for i, (doc_id, _, text, source) in enumerate(chunks):
            if source.startswith("sql_schema:") or source.startswith("sql_query:"):
                continue
            doc_vec = self.embedder.encode_query(text[:512])
            sim = float(np.dot(query_vec, doc_vec))
            sim_norm = max(0.0, (sim + 1.0) / 2.0)
            combined = 0.6 * rerank_norm[i] + 0.4 * sim_norm
            text_lower = text.lower()
            word_match = sum(1 for w in query_content_words if w in text_lower)
            if word_match >= 2:
                combined = max(combined, 0.50)
            if word_match >= 4:
                combined = max(combined, 0.65)
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

    def connect_sqlite(self, db_path: str) -> str:
        return self.sql.connect_sqlite(db_path)

    def connect_firebird(self, db_path: str, host: str = "localhost",
                         user: str = "SYSDBA", password: str = "masterkey") -> str:
        return self.sql.connect_firebird(db_path, user=user, password=password, host=host)

    def connect_mysql(self, host: str, port: int, user: str, password: str, database: str) -> str:
        return self.sql.connect_mysql(host, port, user, password, database)

    def query_sql(self, conn_name: str, sql: str) -> str:
        return self.sql.query_to_text(conn_name, sql)

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
        if any(w in query_lower for w in ["quantos", "quantas", "total de", "numero de", "conta"]):
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
        except Exception:
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
            return f"Total: {count} registro(s) em {table_pt}."
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
                        source: str, confidence: float, decision: str,
                        sections: Optional[List[str]] = None) -> Dict:
        return {
            "query": query,
            "answer": answer,
            "confidence": round(confidence, 3),
            "decision": decision,
            "source": source,
            "num_chunks": len(relevant_chunks),
            "sections": sections or [],
            "chunks": [
                {"text": c[2][:300], "score": round(c[1], 3), "source": c[3]}
                for c in relevant_chunks[:3]
            ],
        }

    def _get_query_product(self, query_lower: str) -> str:
        for word in re.findall(r'[a-zA-Z\u00C0-\u00FF]+', query_lower):
            if len(word) > 3 and word not in self.STOP_WORDS:
                return word
        return ""

    def clear_cache(self):
        self._cached_ask.clear()
