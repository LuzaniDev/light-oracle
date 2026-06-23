import sqlite3
import os
from typing import List, Tuple, Optional


class BM25Index:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None

    def connect(self):
        if self.conn is None:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            self.conn = sqlite3.connect(self.db_path)
            self._create_tables()

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None

    def _create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                chunk_id INTEGER NOT NULL,
                text TEXT NOT NULL
            )
        """)
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts USING fts5(
                text, content='documents', content_rowid='id'
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS doc_metadata (
                source TEXT PRIMARY KEY,
                indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.commit()

    def add_documents(self, chunks: List[dict]):
        self.connect()
        cursor = self.conn.cursor()
        source = chunks[0]["source"] if chunks else "unknown"
        cursor.execute(
            "INSERT OR REPLACE INTO doc_metadata (source) VALUES (?)",
            (source,)
        )
        for chunk in chunks:
            cursor.execute(
                "INSERT INTO documents (source, chunk_id, text) VALUES (?, ?, ?)",
                (chunk["source"], chunk["id"], chunk["text"])
            )
            cursor.execute(
                "INSERT INTO docs_fts (rowid, text) VALUES (?, ?)",
                (cursor.lastrowid, chunk["text"])
            )
        self.conn.commit()

    def search(self, query: str, top_k: int = 50) -> List[Tuple[int, float, str, str]]:
        self.connect()
        cursor = self.conn.cursor()
        results = []
        seen_ids = set()

        strategies = [
            self._sanitize_query(query),
            self._sanitize_query(self._strip_punctuation(query)),
        ]

        key_terms = [w for w in self._extract_terms(query) if len(w) > 2]
        if key_terms:
            strategies.append(" OR ".join(f'"{w}"' for w in key_terms[:8]))

        short_terms = [w for w in self._extract_terms(query) if len(w) >= 2]
        if short_terms:
            strategies.append(" OR ".join(f'"{w}"' for w in short_terms[:12]))

        for sanitized in strategies:
            if not sanitized:
                continue
            try:
                sql = """
                    SELECT d.id, rank, d.text, d.source
                    FROM docs_fts f
                    JOIN documents d ON d.id = f.rowid
                    WHERE docs_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                """
                cursor.execute(sql, (sanitized, top_k))
                for rowid, rank, text, source in cursor.fetchall():
                    if rowid not in seen_ids:
                        seen_ids.add(rowid)
                        score = 1.0 / (1.0 + abs(rank))
                        results.append((rowid, score, text, source))
            except sqlite3.OperationalError:
                continue

        if not results:
            latest = self._get_latest_chunks(top_k)
            results.extend(latest)

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def _extract_terms(self, text: str) -> List[str]:
        import re
        terms = []
        for token in re.findall(r'[A-Za-z0-9\u00C0-\u00FF#]+', text):
            token = token.strip('"\'(),.;:!?')
            if token.startswith('#') and len(token) > 1:
                terms.append(token[1:])
                terms.append(token)
            elif re.match(r'[Rr]\$', token):
                pass
            elif re.match(r'^\d+[\d.,]*$', token):
                clean = token.replace('.', '').replace(',', '.')
                terms.append(clean)
                terms.append(token)
            elif len(token) >= 2:
                terms.append(token)
        return terms

    def _strip_punctuation(self, text: str) -> str:
        import re
        return re.sub(r'[^\w\s\u00C0-\u00FF]', ' ', text)

    def _sanitize_query(self, query: str) -> str:
        terms = []
        for word in self._extract_terms(query):
            if len(word) >= 2:
                terms.append(f'"{word}"')
        return " OR ".join(terms) if terms else ""

    def _get_latest_chunks(self, top_k: int) -> List[Tuple[int, float, str, str]]:
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT d.id, d.text, d.source FROM documents d
                ORDER BY d.id DESC LIMIT ?
            """, (top_k,))
            results = []
            for rowid, text, source in cursor.fetchall():
                results.append((rowid, 0.01, text, source))
            return results
        except Exception:
            return []

    def get_document_count(self) -> int:
        self.connect()
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM documents")
        return cursor.fetchone()[0]

    def remove_source(self, source: str):
        self.connect()
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM docs_fts WHERE rowid IN (SELECT id FROM documents WHERE source = ?)", (source,))
        cursor.execute("DELETE FROM documents WHERE source = ?", (source,))
        cursor.execute("DELETE FROM doc_metadata WHERE source = ?", (source,))
        self.conn.commit()
