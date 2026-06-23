import json
import random
import os
from typing import List, Dict, Optional
from dataclasses import dataclass


SELF_RAG_TOKENS = [
    "[Retrieve]", "[No Retrieve]",
    "[Relevant]", "[Irrelevant]",
    "[Supported]", "[Partially]", "[No Support]", "[Continue]",
]


@dataclass
class RAGExample:
    query: str
    chunks: List[str]
    decisions: List[str]
    answer: str


class SelfRAGDataGenerator:
    def __init__(self, output_dir: str = "./training_data"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def generate_from_documents(self, documents: List[Dict[str, str]], num_examples: int = 100) -> List[RAGExample]:
        examples = []
        for i, doc in enumerate(documents):
            if len(examples) >= num_examples:
                break
            text = doc.get("text", "")
            title = doc.get("title", f"doc_{i}")
            queries = self._generate_queries(text)
            for q in queries:
                if len(examples) >= num_examples:
                    break
                example = self._create_example(q, text, title)
                examples.append(example)
        return examples

    def _generate_queries(self, text: str) -> List[str]:
        sentences = [s.strip() for s in text.replace("\n", ". ").split(".") if len(s.strip()) > 20]
        queries = []
        for s in sentences[:10]:
            words = s.split()[:8]
            if len(words) >= 4:
                q = " ".join(words)
                q = q.replace(",", "").replace(";", "")
                queries.append(f"O que diz sobre {q.lower()}?")
                queries.append(f"Explique {q.lower()}")
                queries.append(f"Informacoes sobre {q.lower()}")
        return queries[:6]

    def _create_example(self, query: str, text: str, title: str) -> RAGExample:
        chunks = self._chunk_text(text)
        if random.random() < 0.7:
            decisions = ["[Retrieve]", "[Relevant]"]
            answer = self._extract_relevant(query, chunks)
            if answer:
                decisions.append("[Supported]")
            else:
                decisions.append("[Partially]")
        else:
            decisions = ["[No Retrieve]"]
            answer = ""
        return RAGExample(query=query, chunks=chunks, decisions=decisions, answer=answer)

    def _chunk_text(self, text: str, chunk_size: int = 200) -> List[str]:
        words = text.split()
        chunks = []
        for i in range(0, len(words), chunk_size):
            chunk = " ".join(words[i:i + chunk_size])
            if chunk.strip():
                chunks.append(chunk)
        return chunks

    def _extract_relevant(self, query: str, chunks: List[str]) -> str:
        query_words = set(query.lower().split())
        best_chunk = ""
        best_score = 0
        for chunk in chunks:
            chunk_lower = chunk.lower()
            score = sum(1 for w in query_words if w in chunk_lower and len(w) > 2)
            if score > best_score:
                best_score = score
                best_chunk = chunk
        words = best_chunk.split()
        return " ".join(words[:60]) if words else ""

    def save_examples(self, examples: List[RAGExample], filename: str = "self_rag_data.jsonl"):
        path = os.path.join(self.output_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            for ex in examples:
                f.write(json.dumps({
                    "query": ex.query,
                    "chunks": ex.chunks,
                    "decisions": ex.decisions,
                    "answer": ex.answer,
                }, ensure_ascii=False) + "\n")
        return path

    def load_examples(self, filename: str = "self_rag_data.jsonl") -> List[RAGExample]:
        path = os.path.join(self.output_dir, filename)
        examples = []
        if not os.path.exists(path):
            return examples
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                data = json.loads(line)
                examples.append(RAGExample(
                    query=data["query"],
                    chunks=data["chunks"],
                    decisions=data["decisions"],
                    answer=data.get("answer", ""),
                ))
        return examples


class SelfRAGTrainer:
    def __init__(self, model_save_dir: str = "./models"):
        self.save_dir = model_save_dir
        os.makedirs(model_save_dir, exist_ok=True)

    def prepare_dataset(self, examples: List[RAGExample]) -> List[Dict]:
        dataset = []
        for ex in examples:
            decisions_str = " ".join(ex.decisions)
            prefix = f"{decisions_str} Pergunta: {ex.query}"
            target = ex.answer if ex.answer else "Nao encontrado."
            dataset.append({"prefix": prefix, "target": target})
        return dataset

    def train_dpo(self, dataset: List[Dict], model_path: str = "oracle_self_rag.pt"):
        import torch
        from ..models.gau import GAUForClassification

        token_map = {tok: i for i, tok in enumerate(SELF_RAG_TOKENS)}
        model = GAUForClassification(num_classes=len(SELF_RAG_TOKENS))
        optimizer = torch.optim.AdamW(model.parameters(), lr=2e-5)

        losses = []
        for epoch in range(3):
            epoch_loss = 0
            for item in dataset:
                tokens_text = item["prefix"] + " " + item["target"]
                input_ids = torch.randint(1, 1000, (1, 128))
                labels = torch.zeros(1, dtype=torch.long)
                for tok in SELF_RAG_TOKENS:
                    if tok in item["prefix"]:
                        labels[0] = token_map[tok]
                        break
                logits = model(input_ids)
                loss = torch.nn.functional.cross_entropy(logits, labels)
                loss.backward()
                optimizer.step()
                optimizer.zero_grad()
                epoch_loss += loss.item()
            losses.append(epoch_loss)

        save_path = os.path.join(self.save_dir, model_path)
        torch.save(model.state_dict(), save_path)
        return save_path
