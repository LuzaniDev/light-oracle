# Oracle RAG

Sistema de oraculo RAG leve para CPU com Self-RAG, consulta a documentos (PDF, TXT, CSV, HTML) e bancos de dados (SQLite, Firebird).

> **Status: EM DESENVOLVIMENTO** — Este projeto esta em fase ativa de desenvolvimento. Nao esta pronto para uso em producao. Funcionalidades podem mudar, quebrar ou serem removidas sem aviso previo.

## Funcionalidades

- Upload de documentos (PDF, TXT, CSV, HTML) e consulta em linguagem natural
- Indexacao persistente para consultas futuras
- Busca hibrida (BM25 + embeddings densos + reranker)
- Self-RAG: ora��o decide quando buscar, avaliar confian�a e reformular perguntas
- SQL Generator automatico para bancos conectados (SQLite, Firebird .ECO)
- Web fallback (busca na web se nao encontrar nos documentos)
- Interface web (Vue 3 + Tailwind + FastAPI)
- CLI para terminal

## Requisitos

- Python 3.10+
- Node.js 18+ (para build do frontend)
- 4-8GB RAM (CPU)

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

## Uso

```bash
# Interface web
.\venv\Scripts\python run_web.py
# -> http://localhost:8081

# CLI
.\venv\Scripts\python -m oracle.cli ask "pergunta" --file documento.pdf
.\venv\Scripts\python -m oracle.cli index ./documentos/
.\venv\Scripts\python -m oracle.cli interactive
```

## Estrutura

```
light-oracle/
├── oracle/           # Engine RAG (modelos, retrieval, pipeline)
├── web/              # Interface web (FastAPI + Vue 3)
├── run_web.py        # Inicializador do servidor web
├── demo.py           # Script de demonstracao
└── requirements.txt  # Dependencias Python
```

## Licenca

MIT
