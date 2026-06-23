# Oracle RAG

Sistema de oraculo RAG leve para CPU com Self-RAG, consulta a documentos (PDF, TXT, CSV, HTML) e bancos de dados (SQLite, Firebird).

> **Status: EM DESENVOLVIMENTO** — Este projeto esta em fase ativa de desenvolvimento. Nao esta pronto para uso em producao. Funcionalidades podem mudar, quebrar ou serem removidas sem aviso previo.

## Funcionalidades

- Upload de documentos (PDF, TXT, CSV, HTML) e consulta em linguagem natural
- Indexacao persistente para consultas futuras
- Busca hibrida (BM25 + embeddings densos + reranker)
- Self-RAG: oraculo decide quando buscar, avaliar confianca e reformular perguntas
- SQL Generator automatico para bancos conectados (SQLite, Firebird .ECO)
- Web fallback (busca na web se nao encontrar nos documentos)
- Interface web (Vue 3 + Tailwind + FastAPI)
- CLI para terminal

## Requisitos

- Python 3.10+
- Node.js 18+ (para build do frontend)
- 4-8GB RAM (CPU)
- ~500MB de espaco em disco para indices e cache

## Instalacao

```bash
# Clonar
git clone <url>
cd light-oracle

# Backend
python -m venv venv
.\venv\Scripts\pip install -r requirements.txt

# Frontend
cd web/frontend
npm install
npm run build
cd ../..
```

## Configuracao

Toda a configuracao do sistema e feita pelo arquivo `.env` na raiz do projeto.
Edite-o para ajustar modelos, portas, chuncks, cache e conexoes com banco.

```bash
# O arquivo .env ja existe na raiz. Abra e edite conforme necessario.
notepad .env
```

O `.env` contem todas as opcoes disponiveis com documentacao completa inline.
Exemplo do que voce encontra la:

| Secao | O que configura |
|---|---|
| Diretorios | Onde ficam indices, uploads e cache |
| Modelos de IA | Modelo de embedding e reranker |
| Leitura (Chunking) | Tamanho e sobreposicao dos pedacos |
| Busca (Retrieval) | Quantidade de resultados por etapa |
| Self-RAG | Thresholds de confianca |
| Web Fallback | Busca na web ativada/desativada |
| Servidor Web | Porta e host da interface |
| Banco de Dados | Conexao Firebird (LK.ECO) |
| Cache | Maximo de perguntas em cache |
| Seguranca | Avisos sobre exposicao do servidor |

## Uso

```bash
# Interface web
.\venv\Scripts\python run_web.py
# -> http://localhost:8081

# CLI - Modo ao vivo (arquivo + pergunta)
.\venv\Scripts\python -m oracle.cli ask "qual o valor total" --file nota.pdf

# CLI - Indexar documentos para consulta futura
.\venv\Scripts\python -m oracle.cli index ./documentos/

# CLI - Consultar documentos indexados
.\venv\Scripts\python -m oracle.cli ask "liste os produtos"

# CLI - Modo interativo
.\venv\Scripts\python -m oracle.cli interactive

# CLI - Conectar banco SQL e consultar
.\venv\Scripts\python -m oracle.cli sql "C:\Ecosis\Dados\LK.ECO" "SELECT * FROM treccliente"

# CLI - Busca na web
.\venv\Scripts\python -m oracle.cli web "aliquota icms SP"
```

## Estrutura

```
light-oracle/
├── oracle/               # Engine RAG
│   ├── engine.py         # Orquestrador principal (Self-RAG)
│   ├── models/           # Embedder, Reranker, GAU
│   ├── retrieval/        # BM25, Dense(FAISS), HyDE, Multi-Query, Web fallback
│   ├── pipeline/         # Parser, Chunker, Live, Persistent, SQL connector
│   ├── training/         # Self-RAG training (DPO)
│   └── utils/            # Config, Tokenizer, Cache
├── web/                  # Interface web
│   ├── server.py         # FastAPI
│   └── frontend/         # Vue 3 + Tailwind
├── .env.example          # Exemplo de configuracao
├── run_web.py            # Inicializador do servidor web
├── demo.py               # Script de demonstracao
└── requirements.txt      # Dependencias Python
```

## Licenca

MIT
