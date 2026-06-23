import re
from typing import List, Dict, Optional

SECTION_RULES = [
    (re.compile(r'produtos?', re.IGNORECASE), "produtos"),
    (re.compile(r'servicos?', re.IGNORECASE), "servicos"),
    (re.compile(r'itens?', re.IGNORECASE), "itens"),
    (re.compile(r'materiais?', re.IGNORECASE), "materiais"),
    (re.compile(r'destinatario', re.IGNORECASE), "destinatario"),
    (re.compile(r'emitente', re.IGNORECASE), "emitente"),
    (re.compile(r'remetente', re.IGNORECASE), "remetente"),
    (re.compile(r'transportador(?:a|es)?', re.IGNORECASE), "transportadora"),
    (re.compile(r'nota\s*fiscal', re.IGNORECASE), "cabecalho"),
    (re.compile(r'nf(?:e)?$', re.IGNORECASE), "cabecalho"),
    (re.compile(r'danfe', re.IGNORECASE), "cabecalho"),
    (re.compile(r'dados\s*do\s*cliente', re.IGNORECASE), "cabecalho"),
    (re.compile(r'identificacao', re.IGNORECASE), "cabecalho"),
    (re.compile(r'fatura', re.IGNORECASE), "fatura"),
    (re.compile(r'boleto', re.IGNORECASE), "boleto"),
    (re.compile(r'observacoes?', re.IGNORECASE), "observacoes"),
    (re.compile(r'informacoes?\s*complementares?', re.IGNORECASE), "complementos"),
    (re.compile(r'imposto', re.IGNORECASE), "imposto"),
    (re.compile(r'icms', re.IGNORECASE), "icms"),
    (re.compile(r'pis', re.IGNORECASE), "pis"),
    (re.compile(r'cofins', re.IGNORECASE), "cofins"),
    (re.compile(r'ipi', re.IGNORECASE), "ipi"),
    (re.compile(r'total\s*da\s*nota', re.IGNORECASE), "total_nf"),
    (re.compile(r'resumo', re.IGNORECASE), "resumo"),
    (re.compile(r'cst', re.IGNORECASE), "cst"),
    (re.compile(r'ncm', re.IGNORECASE), "ncm"),
    (re.compile(r'cfop', re.IGNORECASE), "cfop"),
    (re.compile(r'endereco', re.IGNORECASE), "endereco"),
    (re.compile(r'entrega', re.IGNORECASE), "entrega"),
    (re.compile(r'pedido', re.IGNORECASE), "pedido"),
    (re.compile(r'orcamento', re.IGNORECASE), "orcamento"),
    (re.compile(r'contrato', re.IGNORECASE), "contrato"),
    (re.compile(r'pagamento', re.IGNORECASE), "pagamento"),
    (re.compile(r'condicoes?\s*de\s*pagamento', re.IGNORECASE), "condicoes_pagamento"),
    (re.compile(r'garantia', re.IGNORECASE), "garantia"),
    (re.compile(r'validade', re.IGNORECASE), "validade"),
    (re.compile(r'lote', re.IGNORECASE), "lote"),
    (re.compile(r'data\s*(?:de\s*)?(?:fabricacao|validade|producao)', re.IGNORECASE), "data"),
    (re.compile(r'estoque', re.IGNORECASE), "estoque"),
    (re.compile(r'almoxarifado', re.IGNORECASE), "almoxarifado"),
    (re.compile(r'tabela', re.IGNORECASE), "tabela"),
    (re.compile(r'lista', re.IGNORECASE), "lista"),
    (re.compile(r'endereco', re.IGNORECASE), "endereco"),
]


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

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            matched_name = None
            for pattern, name in SECTION_RULES:
                if pattern.search(stripped):
                    matched_name = name
                    break
            if matched_name:
                if current_lines:
                    sections.append((current_name, "\n".join(current_lines)))
                current_name = matched_name
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
