from typing import List, Dict, Optional, Any
import sqlite3
import re
import os


class SQLConnector:
    def __init__(self):
        self.connections: Dict[str, Any] = {}
        self.schemas: Dict[str, List[Dict]] = {}
        self._drivers: Dict[str, str] = {}

    def connect_sqlite(self, db_path: str, alias: str = "") -> str:
        name = alias or f"sqlite:{db_path}"
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("SELECT 1")
            self.connections[name] = conn
            self._drivers[name] = "sqlite"
            self._extract_schema_sqlite(conn, name)
            return name
        except sqlite3.DatabaseError:
            return self._try_firebird(db_path, name)

    def _try_firebird(self, db_path: str, name: str) -> str:
        try:
            import fdb
            fdb.load_api()
            try:
                conn = fdb.connect(database=db_path, user='SYSDBA', password='masterkey')
            except Exception:
                conn = fdb.connect(host='localhost', database=db_path, user='SYSDBA', password='masterkey')
            self.connections[name] = conn
            self._drivers[name] = "firebird"
            self._extract_schema_firebird(conn, name)
            return name
        except Exception as fb_err:
            raise sqlite3.DatabaseError(
                f"Arquivo nao e SQLite valido. Tentativa Firebird falhou: {fb_err}"
            )

    def connect_firebird(self, db_path: str, user: str = "SYSDBA",
                         password: str = "masterkey", host: str = "localhost",
                         alias: str = "") -> str:
        import fdb
        fdb.load_api()
        name = alias or f"firebird:{os.path.basename(db_path)}"
        kwargs = {"database": db_path, "user": user, "password": password}
        if host:
            kwargs["host"] = host
        conn = fdb.connect(**kwargs)
        self.connections[name] = conn
        self._drivers[name] = "firebird"
        self._extract_schema_firebird(conn, name)
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

    def _extract_schema_firebird(self, conn, name: str):
        cursor = conn.cursor()
        cursor.execute("SELECT rdb$relation_name FROM rdb$relations WHERE rdb$view_blr IS NULL AND rdb$system_flag = 0")
        tables = []
        for row in cursor.fetchall():
            t = row[0].strip() if hasattr(row[0], 'strip') else row[0]
            tables.append(t)
        schema = []
        for table in tables:
            cursor.execute(
                "SELECT rdb$field_name FROM rdb$relation_fields "
                "WHERE rdb$relation_name = ? ORDER BY rdb$field_position",
                (table,)
            )
            cols = []
            for row in cursor.fetchall():
                col = row[0].strip() if hasattr(row[0], 'strip') else row[0]
                cols.append(col.lower())
            schema.append({"table": table.lower(), "columns": cols})
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
        driver = self._drivers.get(conn_name, "sqlite")
        for row in rows:
            if isinstance(row, dict):
                result.append({k.lower(): v for k, v in row.items()})
            elif hasattr(row, '__getitem__') and not isinstance(row, (str, bytes)):
                d = {}
                for i, col in enumerate(columns):
                    val = row[i] if i < len(row) else None
                    col_clean = col.lower() if isinstance(col, str) else str(col).lower()
                    if hasattr(val, 'strip') and hasattr(val, 'upper'):
                        pass
                    d[col_clean] = val
                result.append(d)
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
