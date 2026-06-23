from typing import List, Optional


class TokenizerWrapper:
    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5"):
        from transformers import AutoTokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.vocab_size = len(self.tokenizer)

    def encode(self, text: str, max_length: int = 512, truncation: bool = True) -> List[int]:
        return self.tokenizer.encode(text, max_length=max_length, truncation=truncation)

    def decode(self, ids: List[int]) -> str:
        return self.tokenizer.decode(ids)

    def tokenize(self, text: str, max_length: int = 512, padding: bool = True, truncation: bool = True):
        return self.tokenizer(
            text,
            max_length=max_length,
            padding=padding,
            truncation=truncation,
            return_tensors="pt",
        )

    def batch_tokenize(self, texts: List[str], max_length: int = 512):
        return self.tokenizer(
            texts,
            max_length=max_length,
            padding=True,
            truncation=True,
            return_tensors="pt",
        )
