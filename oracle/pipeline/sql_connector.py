from typing import List, Dict, Optional
import sqlite3
import re


class SQLConnector:
    def __init__(self):
        self.connections: Dict[str, object] = {}
        self.schemas: Dict[str, List[Dict]] = {}

    def connect_sqlite(self, db_path: str, alias: str = "") -> str:
        name = alias or f"sqlite:{db_path}"
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        self.connections[name] = conn
        self._extract_schema_sqlite(conn, name)
        return name

    def connect_mysql(self, host: str, port: int, user: str, password: str, database: str, alias: str = "") -> str:
        try:
            import pymysql
        except ImportError:
            raise ImportError("pymysql necessario para MySQL. Instale com: pip install pymysql")
        name = alias or f"mysql:{database}@{host}"
        conn = pymysql.connect(host=host, port=port, user=user, password=password, database=database, charset="utf8mb4")
        self.connections[name] = conn
        self._extract_schema_generic(conn, name)
        return name

    def connect_postgres(self, host: str, port: int, user: str, password: str, database: str, alias: str = "") -> str:
        try:
            import psycopg2
        except ImportError:
            raise ImportError("psycopg2 necessario para PostgreSQL. Instale com: pip install psycopg2-binary")
        name = alias or f"pgsql:{database}@{host}"
        conn = psycopg2.connect(host=host, port=port, user=user, password=password, dbname=database)
        self.connections[name] = conn
        self._extract_schema_generic(conn, name)
        return name

    def _extract_schema_sqlite(self, conn, name: str):
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r["name"] for r in cursor.fetchall()]
        schema = []
        for table in tables:
            cursor.execute(f"PRAGMA table_info('{table}')")
            cols = [r["name"] for r in cursor.fetchall()]
            schema.append({"table": table, "columns": cols})
        self.schemas[name] = schema

    def _extract_schema_generic(self, conn, name: str):
        cursor = conn.cursor()
        cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
        tables = [r[0] for r in cursor.fetchall()]
        schema = []
        for table in tables:
            cursor.execute(f"SELECT column_name FROM information_schema.columns WHERE table_name='{table}'")
            cols = [r[0] for r in cursor.fetchall()]
            schema.append({"table": table, "columns": cols})
        self.schemas[name] = schema

    def execute_query(self, conn_name: str, sql: str) -> List[Dict]:
        conn = self.connections.get(conn_name)
        if not conn:
            raise ValueError(f"Conexao '{conn_name}' nao encontrada")
        cursor = conn.cursor()
        cursor.execute(sql)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = cursor.fetchall()
        result = []
        for row in rows:
            if isinstance(row, dict):
                result.append(dict(row))
            elif isinstance(row, (sqlite3.Row,)):
                result.append(dict(row))
            else:
                result.append(dict(zip(columns, row)))
        return result

    def query_to_text(self, conn_name: str, sql: str) -> str:
        rows = self.execute_query(conn_name, sql)
        if not rows:
            return "Nenhum resultado encontrado."
        keys = rows[0].keys()
        lines = [f"Resultados da consulta SQL ({len(rows)} linhas):"]
        lines.append(" | ".join(str(k) for k in keys))
        lines.append("-" * len(lines[-1]))
        for row in rows[:50]:
            lines.append(" | ".join(str(row[k]) for k in keys))
        if len(rows) > 50:
            lines.append(f"... e mais {len(rows) - 50} linhas")
        return "\n".join(lines)

    def get_schema_text(self, conn_name: str) -> str:
        schema = self.schemas.get(conn_name, [])
        if not schema:
            return "Nenhuma tabela encontrada."
        lines = [f"Esquema do banco '{conn_name}':"]
        for table in schema:
            lines.append(f"  {table['table']}: {', '.join(table['columns'])}")
        return "\n".join(lines)

    def list_tables(self, conn_name: str) -> List[str]:
        schema = self.schemas.get(conn_name, [])
        return [t["table"] for t in schema]

    def disconnect(self, conn_name: str):
        conn = self.connections.pop(conn_name, None)
        if conn:
            conn.close()

    def disconnect_all(self):
        for name in list(self.connections.keys()):
            self.disconnect(name)
