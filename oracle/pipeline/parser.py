import os
import csv
import io
from typing import List, Optional, Dict


class DocumentParser:
    SUPPORTED_EXTENSIONS = {".txt", ".md", ".csv", ".html", ".htm", ".pdf"}

    def parse(self, file_path: str) -> Optional[str]:
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in self.SUPPORTED_EXTENSIONS:
            return None
        parser_map = {
            ".txt": self._parse_text,
            ".md": self._parse_text,
            ".csv": self._parse_csv,
            ".html": self._parse_html,
            ".htm": self._parse_html,
            ".pdf": self._parse_pdf,
        }
        parser = parser_map.get(ext)
        if parser is None:
            return None
        try:
            return parser(file_path)
        except Exception as e:
            raise RuntimeError(f"Erro ao processar {file_path}: {e}")

    def parse_sql_query(self, query_result: List[Dict]) -> str:
        if not query_result:
            return ""
        keys = query_result[0].keys()
        lines = [" | ".join(str(k) for k in keys)]
        lines.append("-" * len(lines[0]))
        for row in query_result:
            lines.append(" | ".join(str(row[k]) for k in keys))
        return "\n".join(lines)

    def _parse_text(self, file_path: str) -> str:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()

    def _parse_csv(self, file_path: str) -> str:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f)
            lines = []
            for row in reader:
                lines.append(" | ".join(row))
            return "\n".join(lines)

    def _parse_html(self, file_path: str) -> str:
        from bs4 import BeautifulSoup
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            soup = BeautifulSoup(f.read(), "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            return soup.get_text(separator="\n", strip=True)

    def _parse_pdf(self, file_path: str) -> str:
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(file_path)
        texts = []
        for i in range(len(pdf)):
            page = pdf[i]
            textpage = page.get_textpage()
            text = textpage.get_text_bounded()
            textpage.close()
            if text:
                texts.append(text)
        pdf.close()
        return "\n".join(texts) if texts else ""
