import re
from typing import List, Dict


class Chunker:
    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 64):
        self.chunk_size = chunk_size
        self.chunk_overlap = max(1, chunk_overlap)

    def chunk_text(self, text: str, source: str = "") -> List[Dict]:
        text = text.strip()
        if not text:
            return []
        paragraphs = self._split_paragraphs(text)
        chunks = self._recursive_chunk(paragraphs, source)
        return chunks

    def _split_paragraphs(self, text: str) -> List[str]:
        paragraphs = re.split(r"\n\s*\n", text)
        result = []
        for p in paragraphs:
            p = p.strip()
            if not p:
                continue
            lines = p.split("\n")
            for line in lines:
                line = line.strip()
                if line:
                    result.append(line)
        return result

    def _recursive_chunk(self, paragraphs: List[str], source: str) -> List[Dict]:
        chunks = []
        current_chunk = []
        current_size = 0
        chunk_id = 0

        for para in paragraphs:
            para_size = len(para.split())
            if para_size > self.chunk_size:
                sub_chunks = self._split_long_para(para)
                for sc in sub_chunks:
                    sc_size = len(sc.split())
                    if current_size + sc_size > self.chunk_size and current_chunk:
                        chunks.append(self._make_chunk(current_chunk, chunk_id, source))
                        chunk_id += 1
                        current_chunk = [sc]
                        current_size = sc_size
                    else:
                        current_chunk.append(sc)
                        current_size += sc_size
            elif current_size + para_size <= self.chunk_size or not current_chunk:
                current_chunk.append(para)
                current_size += para_size
            else:
                chunks.append(self._make_chunk(current_chunk, chunk_id, source))
                chunk_id += 1
                overlap_tokens = 0
                overlap_lines = []
                for p in reversed(current_chunk):
                    pt = len(p.split())
                    if overlap_tokens + pt > self.chunk_overlap:
                        break
                    overlap_lines.insert(0, p)
                    overlap_tokens += pt
                current_chunk = overlap_lines + [para]
                current_size = sum(len(p.split()) for p in current_chunk)

        if current_chunk:
            chunks.append(self._make_chunk(current_chunk, chunk_id, source))

        return chunks

    def _split_long_para(self, para: str) -> List[str]:
        sentences = re.split(r'(?<=[.!?])\s+', para)
        sub_chunks = []
        current = []
        current_size = 0
        for sent in sentences:
            sent_size = len(sent.split())
            if current_size + sent_size > self.chunk_size and current:
                sub_chunks.append(" ".join(current))
                current = [sent]
                current_size = sent_size
            else:
                current.append(sent)
                current_size += sent_size
        if current:
            sub_chunks.append(" ".join(current))
        return sub_chunks if sub_chunks else [para]

    def _make_chunk(self, lines: List[str], chunk_id: int, source: str) -> Dict:
        text = "\n".join(lines)
        return {
            "id": chunk_id,
            "text": text,
            "source": source,
            "tokens": len(text.split()),
        }
