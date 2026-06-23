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
            self._sanitize_query(query.replace("?", "").replace("!", "").replace(",", "")),
        ]

        key_words = [w for w in query.split() if len(w) > 3]
        if key_words:
            strategies.append(" OR ".join(f'"{w}"' for w in key_words[:5]))

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

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def _sanitize_query(self, query: str) -> str:
        import re
        terms = []
        tokens = re.findall(r'[A-Za-zÀ-ÿ0-9]+', query)
        for word in tokens:
            word = word.strip('"\'(),.;:!?')
            if len(word) >= 2:
                terms.append(f'"{word}"')
        return " OR ".join(terms) if terms else ""

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
