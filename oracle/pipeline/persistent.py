import os
from typing import Dict, List, Optional
from ..pipeline.parser import DocumentParser
from ..pipeline.chunker import Chunker
from ..engine import OracleEngine
from ..utils.config import OracleConfig


class PersistentPipeline:
    def __init__(self, engine: OracleEngine):
        self.engine = engine
        self.parser = DocumentParser()

    def index(self, path: str) -> Dict:
        if os.path.isfile(path):
            return self._index_file(path)
        elif os.path.isdir(path):
            return self._index_directory(path)
        return {"error": f"Caminho inválido: {path}"}

    def _index_file(self, file_path: str) -> Dict:
        text = self.parser.parse(file_path)
        if text is None:
            return {"error": f"Formato não suportado: {file_path}", "file": file_path}
        num_chunks = self.engine.index_document(text, source=os.path.basename(file_path))
        return {
            "file": os.path.basename(file_path),
            "chunks": num_chunks,
            "status": "indexado",
        }

    def _index_directory(self, dir_path: str) -> List[Dict]:
        results = []
        supported = DocumentParser.SUPPORTED_EXTENSIONS
        for root, _, files in os.walk(dir_path):
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext in supported:
                    fpath = os.path.join(root, fname)
                    result = self._index_file(fpath)
                    results.append(result)
        return results

    def ask(self, query: str) -> Dict:
        response = self.engine.ask(query)
        response["mode"] = "persistent"
        return response

    def stats(self) -> Dict:
        return {
            "documentos_indexados": self.engine.bm25.get_document_count(),
            "indice_denso_carregado": bool(self.engine.dense.chunks),
        }
