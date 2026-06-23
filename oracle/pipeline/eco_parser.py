from typing import List, Dict, Optional, Tuple
import struct
import re
import os


class ECOParser:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self._data: Optional[bytes] = None
        self._tables: Dict[str, Dict] = {}

    def _load(self):
        if self._data is None:
            with open(self.file_path, 'rb') as f:
                self._data = f.read()

    def list_tables(self) -> List[str]:
        self._load()
        tables = []
        for name in self._known_tables():
            if self._table_exists(name):
                tables.append(name)
        return sorted(tables)

    def _known_tables(self) -> List[str]:
        return [
            'treccliente', 'trecfornecedor', 'trecproduto', 'trecpedido',
            'trecvenda', 'trecnotafiscal', 'trecestoque', 'trecfiscal',
            'trecusuario', 'trecempresa', 'trecfilial', 'trectransportadora',
            'trecbanco', 'trecconta', 'treccategoria', 'trecmarca',
            'trecgrupo', 'trecsubgrupo', 'trecunidade', 'trecvendedor',
            'trectabelapreco', 'treccondpagamento', 'trecclienteproduto',
            'trecfornecedorproduto', 'trecpedidoitem', 'trecnotafiscalitem',
            'trecclientedependente', 'trecclientereferencia',
            'trecclientesocios', 'trecclientetransportadora',
            'trecclientevendedor', 'trecclienteweb', 'trecclientefidelidade',
            'trecclientepontos', 'trecclientecartao', 'trecclientebloqueio',
            'trecconfig', 'trecparametro', 'trecfuncionario',
            'treccargo', 'trecsetor', 'trecmsgretorno', 'trecemitentenfe',
            'trecdestinatario', 'trecprodutofornecedor', 'trecprodutolocalizacao',
            'trecnotaservico', 'treccontareceber', 'treccontapagar',
            'treccontacorrente', 'treccontabil', 'trecplanoconta',
            'treclancamento', 'trecadicional', 'trecdesconto',
            'trecimposto', 'trectributacao', 'trecclassfiscal',
            'trecst', 'trecmva', 'trecipi', 'trecpis', 'treccofins',
            'treccst', 'treccfop', 'trecncm', 'treccanexo',
            'trecnbs', 'treccest', 'trecnbs', 'trecselo',
        ]

    def _table_exists(self, table_name: str) -> bool:
        pattern = table_name.encode('latin-1')
        return pattern in self._data

    def get_schema(self, table_name: str) -> List[Dict]:
        self._load()
        pattern = table_name.encode('latin-1')
        pos = self._data.find(pattern)
        if pos == -1:
            return []

        context_start = max(0, pos - 1000)
        context = self._data[context_start:pos + len(pattern) + 2000]
        text = context.decode('latin-1', errors='replace')

        lines = text.replace('\r\n', '\n').split('\n')
        fields = []
        header_found = False
        for line in lines:
            if table_name.lower() in line.lower():
                header_found = True
                continue
            if not header_found:
                continue
            if 'CREATE' in line.upper() or 'TABLE' in line.upper():
                continue
            if 'INDEX' in line.upper() or 'KEY' in line.upper() or 'CONSTRAINT' in line.upper():
                continue
            if line.strip().startswith('--') or line.strip().startswith('//'):
                continue
            if ')' in line and not any(c.isalpha() for c in line.split(')')[0]):
                break

            parts = line.strip().split()
            if len(parts) >= 2:
                field_name = parts[0].strip(',; ')
                field_type = parts[1].strip(',; ')
                if field_name and not field_name.startswith('_'):
                    fields.append({
                        'name': field_name,
                        'type': field_type.upper(),
                        'length': self._parse_length(field_type),
                    })

        if not fields:
            return self._guess_fields(table_name, pos, context)

        return fields

    def _parse_length(self, type_str: str) -> int:
        m = re.search(r'\((\d+)\)', type_str)
        return int(m.group(1)) if m else 0

    def _guess_fields(self, table_name: str, pos: int, context: bytes) -> List[Dict]:
        text = context.decode('latin-1', errors='replace')
        sql_like = re.findall(r'\b([A-Z][A-Za-z]{2,20})\b', text)
        seen = set()
        fields = []
        for name in sql_like:
            if name.upper() in ('THE', 'AND', 'INNER', 'JOIN', 'LEFT', 'ON', 'WHERE', 'ORDER', 'BY',
                                'AS', 'IN', 'IS', 'NOT', 'NULL', 'FROM', 'INTO', 'INSERT', 'UPDATE',
                                'DELETE', 'SELECT', 'SET', 'HAVING', 'GROUP', 'INTO'):
                continue
            if name not in seen:
                seen.add(name)
                fields.append({'name': name, 'type': 'VARCHAR', 'length': 0})
        return fields if not all(f['name'].isupper() for f in fields) else []

    def get_schema_text(self, table_name: str) -> str:
        fields = self.get_schema(table_name)
        if not fields:
            return f"Tabela '{table_name}' encontrada, mas nao foi possivel extrair schema."
        lines = [f"Tabela: {table_name}"]
        lines.append(f"Campos ({len(fields)}):")
        for f in fields:
            lines.append(f"  {f['name']:30s} {f['type']}")
        return "\n".join(lines)

    def query(self, table_name: str, where: str = "", limit: int = 30) -> List[Dict]:
        self._load()
        pattern = table_name.encode('latin-1')
        positions = []
        start = 0
        while True:
            pos = self._data.find(pattern, start)
            if pos == -1:
                break
            positions.append(pos)
            start = pos + 1

        if not positions:
            return []

        results = []
        seen = set()
        for pos in positions:
            chunk_start = max(0, pos - 50)
            chunk_end = min(len(self._data), pos + 2000)
            chunk = self._data[chunk_start:chunk_end]
            rows = self._extract_rows(chunk, table_name)
            for row in rows:
                row_key = tuple(sorted(row.items()))
                if row_key not in seen:
                    seen.add(row_key)
                    results.append(row)
                    if len(results) >= limit:
                        return results
        return results[:limit]

    def _extract_rows(self, chunk: bytes, table_name: str) -> List[Dict]:
        text = chunk.decode('latin-1', errors='replace')
        lines = text.split('\n')
        rows = []
        for line in lines:
            if table_name.lower() in line.lower():
                continue
            clean = line.strip()
            if len(clean) < 10:
                continue
            if 'VALUES' in clean.upper() or 'INSERT' in clean.upper():
                m = re.search(r'VALUES\s*\((.*)\)', clean, re.IGNORECASE)
                if m:
                    values = [v.strip().strip("'\"") for v in m.group(1).split(',')]
                    row = {f'campo_{i}': v for i, v in enumerate(values)}
                    rows.append(row)
        return rows

    def extract_all_metadata(self) -> str:
        tables = self.list_tables()
        lines = [f"Database: {os.path.basename(self.file_path)}", f"Tabelas encontradas ({len(tables)}):"]
        for t in tables:
            fields = self.get_schema(t)
            if fields:
                lines.append(f"  {t} ({len(fields)} campos)")
            else:
                lines.append(f"  {t}")
        return "\n".join(lines)
