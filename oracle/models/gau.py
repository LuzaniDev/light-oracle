import torch
import torch.nn as nn
import torch.nn.functional as F
import math


class GAU(nn.Module):
    def __init__(self, d_model: int = 384, d_ff: int = None, dropout: float = 0.1, activation: str = "swish"):
        super().__init__()
        d_ff = d_ff or d_model * 2
        self.d_model = d_model
        self.d_ff = d_ff

        self.norm = nn.LayerNorm(d_model)
        self.gate_proj = nn.Linear(d_model, d_ff, bias=False)
        self.value_proj = nn.Linear(d_model, d_ff, bias=False)
        self.query_proj = nn.Linear(d_model, d_ff, bias=False)
        self.key_proj = nn.Linear(d_model, d_ff, bias=False)
        self.out_proj = nn.Linear(d_ff, d_model, bias=False)

        self.scale = math.sqrt(d_ff) ** -1
        self.dropout = nn.Dropout(dropout)
        self.activation = activation

    def _act(self, x: torch.Tensor) -> torch.Tensor:
        if self.activation == "swish":
            return x * torch.sigmoid(x)
        elif self.activation == "gelu":
            return F.gelu(x)
        return F.relu(x)

    def forward(self, x: torch.Tensor, mask: torch.Tensor = None) -> torch.Tensor:
        residual = x
        x = self.norm(x)

        gate = self._act(self.gate_proj(x))
        v = self.value_proj(x)
        q = self.query_proj(x)
        k = self.key_proj(x)

        attn = torch.matmul(q, k.transpose(-2, -1)) * self.scale
        if mask is not None:
            attn = attn.masked_fill(mask == 0, float("-inf"))
        attn = F.softmax(attn, dim=-1)
        attn = self.dropout(attn)

        out = torch.matmul(attn, v)
        out = out * gate
        out = self.out_proj(out)
        return residual + out


class GAUEncoder(nn.Module):
    def __init__(self, vocab_size: int = 32000, d_model: int = 384, num_layers: int = 6,
                 d_ff: int = None, dropout: float = 0.1, max_seq_len: int = 512, activation: str = "swish"):
        super().__init__()
        self.d_model = d_model
        self.embed = nn.Embedding(vocab_size, d_model, padding_idx=0)
        self.pos_embed = nn.Embedding(max_seq_len, d_model)
        self.dropout = nn.Dropout(dropout)

        self.layers = nn.ModuleList([
            GAU(d_model, d_ff, dropout, activation) for _ in range(num_layers)
        ])
        self.norm = nn.LayerNorm(d_model)

    def forward(self, input_ids: torch.Tensor, attention_mask: torch.Tensor = None) -> torch.Tensor:
        seq_len = input_ids.size(1)
        positions = torch.arange(seq_len, device=input_ids.device).unsqueeze(0)

        x = self.embed(input_ids) + self.pos_embed(positions)
        x = self.dropout(x)

        if attention_mask is not None:
            mask = attention_mask.unsqueeze(1).unsqueeze(2)
        else:
            mask = None

        for layer in self.layers:
            x = layer(x, mask)

        x = self.norm(x)
        return x


class GAUForEmbedding(nn.Module):
    def __init__(self, vocab_size: int = 32000, d_model: int = 384, num_layers: int = 6,
                 embed_dim: int = 256, dropout: float = 0.1):
        super().__init__()
        self.encoder = GAUEncoder(vocab_size, d_model, num_layers, dropout=dropout)
        self.pooler = nn.Linear(d_model, embed_dim)

    def forward(self, input_ids: torch.Tensor, attention_mask: torch.Tensor = None) -> torch.Tensor:
        x = self.encoder(input_ids, attention_mask)
        if attention_mask is not None:
            x = (x * attention_mask.unsqueeze(-1)).sum(dim=1) / attention_mask.sum(dim=1, keepdim=True)
        else:
            x = x.mean(dim=1)
        x = self.pooler(x)
        x = F.normalize(x, p=2, dim=-1)
        return x


class GAUForClassification(nn.Module):
    def __init__(self, vocab_size: int = 32000, d_model: int = 256, num_layers: int = 4,
                 num_classes: int = 8, dropout: float = 0.1):
        super().__init__()
        self.encoder = GAUEncoder(vocab_size, d_model, num_layers, d_ff=d_model * 2, dropout=dropout)
        self.classifier = nn.Linear(d_model, num_classes)

    def forward(self, input_ids: torch.Tensor, attention_mask: torch.Tensor = None) -> torch.Tensor:
        x = self.encoder(input_ids, attention_mask)
        if attention_mask is not None:
            x = (x * attention_mask.unsqueeze(-1)).sum(dim=1) / attention_mask.sum(dim=1, keepdim=True)
        else:
            x = x.mean(dim=1)
        return self.classifier(x)


def count_params(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters() if p.requires_grad)
