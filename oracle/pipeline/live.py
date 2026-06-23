from ..pipeline.parser import DocumentParser
from ..engine import OracleEngine
from typing import Dict, Optional
import os


class LivePipeline:
    def __init__(self, engine: OracleEngine):
        self.engine = engine
        self.parser = DocumentParser()

    def ask(self, file_path: str, query: str) -> Dict:
        if not os.path.exists(file_path):
            return {"error": f"Arquivo não encontrado: {file_path}"}
        text = self.parser.parse(file_path)
        if text is None:
            return {"error": f"Formato não suportado: {file_path}"}
        if not text.strip():
            return {"error": "Arquivo vazio ou sem texto extraível."}
        self.engine.index_document(text, source=os.path.basename(file_path))
        response = self.engine.ask(query)
        response["mode"] = "live"
        response["file"] = os.path.basename(file_path)
        return response
