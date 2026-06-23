import re
from typing import List, Dict, Optional

SECTION_MARKERS = [
    "produtos?", "servicos?", "itens?", "materiais?",
    "destinatario", "emitente", "remetente", "transportador(?:a|es)?",
    "nota\s*fiscal", "nf(?:e)?", "danfe",
    "dados\s*do\s*cliente", "identificacao",
    "fatura", "boleto", "cobranca",
    "observacoes?", "informacoes?\s*complementares?",
    "c\xe1lculo\s*do\s*imposto", "imposto",
    "icms", "pis", "cofins", "ipi",
    "total\s*da\s*nota", "resumo",
    "cst", "ncm", "cfop",
    "endereco", "entrega",
    "pedido", "orcamento", "contrato",
    "pagamento", "condicoes?\s*de\s*pagamento",
    "garantia", "validade",
    "lote", "data\s*(?:de\s*)?(?:fabricacao|validade|producao)",
    "estoque", "almoxarifado",
    "tabela", "lista",
]

SECTION_NAMES = {
    "produtos": "produtos", "servicos": "servicos", "itens": "itens",
    "destinatario": "destinatario", "emitente": "emitente",
    "nota fiscal": "cabecalho", "nfe": "cabecalho",
    "identificacao": "cabecalho",
}


class Chunker:
    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 64):
        self.chunk_size = chunk_size
        self.chunk_overlap = max(1, chunk_overlap)

    def chunk_text(self, text: str, source: str = "") -> List[Dict]:
        text = text.strip()
        if not text:
            return []
        sections = self._split_sections(text)
        chunks = []
        chunk_id = 0
        for section_name, section_text in sections:
            section_chunks = self._chunk_section(section_name, section_text, source, chunk_id)
            chunks.extend(section_chunks)
            chunk_id += len(section_chunks)
        if not chunks:
            chunks = self._chunk_fallback(text, source)
        return chunks

    def _split_sections(self, text: str) -> List[tuple]:
        lines = text.split("\n")
        sections = []
        current_name = "geral"
        current_lines = []
        section_patterns = {m.lower(): re.compile(m, re.IGNORECASE) for m in SECTION_MARKERS}

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            lower = stripped.lower()
            matched = None
            for name, pattern in section_patterns.items():
                if pattern.search(stripped):
                    matched = name
                    break
            if matched:
                if current_lines:
                    sections.append((current_name, "\n".join(current_lines)))
                current_name = SECTION_NAMES.get(matched, matched)
                current_lines = [stripped]
            else:
                current_lines.append(stripped)

        if current_lines:
            sections.append((current_name, "\n".join(current_lines)))
        return sections

    def _chunk_section(self, section_name: str, text: str, source: str, start_id: int) -> List[Dict]:
        if self._is_table_block(text):
            return [self._make_chunk(
                text, start_id, source,
                tag="table", section=section_name
            )]

        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
        if len(paragraphs) <= 3:
            combined = " | ".join(paragraphs)
            if len(combined.split()) <= self.chunk_size:
                return [self._make_chunk(
                    combined, start_id, source,
                    tag="compact", section=section_name
                )]

        chunks = []
        current_lines = []
        current_size = 0
        chunk_id = start_id

        for para in paragraphs:
            para_size = len(para.split())
            if para_size > self.chunk_size:
                sub = self._split_long_para(para)
                for s in sub:
                    sz = len(s.split())
                    if current_size + sz > self.chunk_size and current_lines:
                        chunks.append(self._make_chunk(
                            "\n".join(current_lines), chunk_id, source,
                            tag="body", section=section_name
                        ))
                        chunk_id += 1
                        current_lines = [s]
                        current_size = sz
                    else:
                        current_lines.append(s)
                        current_size += sz
            elif current_size + para_size <= self.chunk_size or not current_lines:
                current_lines.append(para)
                current_size += para_size
            else:
                chunks.append(self._make_chunk(
                    "\n".join(current_lines), chunk_id, source,
                    tag="body", section=section_name
                ))
                chunk_id += 1
                current_lines = [para]
                current_size = para_size

        if current_lines:
            chunks.append(self._make_chunk(
                "\n".join(current_lines), chunk_id, source,
                tag="body", section=section_name
            ))

        return chunks

    def _is_table_block(self, text: str) -> bool:
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        if len(lines) < 3:
            return False
        number_lines = 0
        pipe_lines = 0
        money_lines = 0
        for line in lines:
            has_number = bool(re.search(r'\d+', line))
            has_pipe = "|" in line
            has_money = bool(re.search(r'[Rr]\$\s*[\d,.]+', line))
            dashed_headers = bool(re.match(r'^[-\s]+\|?[-\s]+', line))
            if has_number:
                number_lines += 1
            if has_pipe:
                pipe_lines += 1
            if has_money:
                money_lines += 1

        ratio_numbers = number_lines / len(lines)
        ratio_pipe = pipe_lines / len(lines)

        has_header = bool(re.search(
            r'(?:descricao|produto|item|qtd|quantidade|unitario|total|valor)',
            lines[0], re.IGNORECASE
        )) if lines else False

        multi_word_numbers = 0
        for line in lines:
            words = line.split()
            num_words = sum(1 for w in words if re.match(r'^[\d,.R$\-]+$', w))
            if num_words >= 2:
                multi_word_numbers += 1
        ratio_multi = multi_word_numbers / len(lines)

        return (ratio_numbers >= 0.5 and ratio_multi >= 0.3) or pipe_lines >= 2 or money_lines >= 2

    def _chunk_fallback(self, text: str, source: str) -> List[Dict]:
        paragraphs = text.split("\n")
        paragraphs = [p.strip() for p in paragraphs if p.strip()]
        chunks = []
        current = []
        size = 0
        cid = 0
        for para in paragraphs:
            sz = len(para.split())
            if size + sz <= self.chunk_size or not current:
                current.append(para)
                size += sz
            else:
                chunks.append(self._make_chunk("\n".join(current), cid, source))
                cid += 1
                current = [para]
                size = sz
        if current:
            chunks.append(self._make_chunk("\n".join(current), cid, source))
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

    def _make_chunk(self, text: str, chunk_id: int, source: str,
                    tag: str = "body", section: str = "geral") -> Dict:
        return {
            "id": chunk_id,
            "text": text,
            "source": source,
            "tokens": len(text.split()),
            "tag": tag,
            "section": section,
        }
