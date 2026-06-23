"""Demonstração completa do Oráculo RAG"""
import sys, os, shutil, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from oracle.utils.config import OracleConfig
from oracle.engine import OracleEngine
from oracle.pipeline.live import LivePipeline
from oracle.pipeline.persistent import PersistentPipeline

print("=" * 60)
print("  ORACULO RAG - Demonstracao")
print("  Modelo leve para CPU | Self-RAG | PT-BR")
print("=" * 60)

config = OracleConfig()
if os.path.exists(config.indexes_dir):
    shutil.rmtree(config.indexes_dir)
os.makedirs(config.indexes_dir, exist_ok=True)

engine = OracleEngine(config)
live = LivePipeline(engine)
persistent = PersistentPipeline(engine)

# --- MODO PERSISTENTE ---
print("\n[1] MODO PERSISTENTE - Indexando documentos...\n")

docs = [
    ("vendas.txt", """
RELATORIO DE VENDAS - MULTILIMPEZA COMERCIO DE PRODUTOS LTDA
Periodo: Janeiro a Junho 2026
A empresa Multilimpeza apresentou crescimento de 23% nas vendas no primeiro semestre de 2026.
Faturamento total: R$ 1.234.567,00.
Produtos vendidos:
- Detergente Liquido 500ml - R$ 4,50/unidade - 45.000 unidades
- Desinfetante 1L - R$ 6,80/unidade - 32.000 unidades
- Sabao em Po 1kg - R$ 12,90/unidade - 18.500 unidades
Pedidos:
- Pedido #456 - Empresa ABC Ltda - R$ 15.780,00 - Status: APROVADO
- Pedido #789 - Comercio XYZ S/A - R$ 23.450,00 - Status: PENDENTE
O pedido #789 esta pendente pois aguarda analise de credito do cliente.
"""),
    ("regras.txt", """
REGRAS TRIBUTARIAS NCM 3402 (PRODUTOS DE LIMPEZA)
NCM 3402.20 - Detergentes e Desinfetantes
Aliquota PIS: 1,65% | Aliquota COFINS: 7,60%
Aliquota ICMS: 18% (SP) / 12% (interestadual)
NCM 3402.20.10 - Detergentes Liquidos - Aliquota IPI: 5%
NCM 3402.20.90 - Outros produtos de limpeza - Aliquota IPI: 10%
"""),
    ("estoque.txt", """
ESTOQUE ATUAL - MULTILIMPEZA (Atualizado em 20/06/2026)
Produto: Detergente Liquido 500ml - Quantidade: 2.500 unidades
Produto: Desinfetante 1L - Quantidade: 1.800 unidades
Produto: Sabao em Po 1kg - Quantidade: 950 unidades
Observacao: O sabao em po esta com estoque baixo (abaixo do minimo de 1.000).
Responsavel: Carlos Silva | Galpao: Rua das Industrias, 1500 - Bloco B
"""),
]
for source, text in docs:
    n = engine.index_document(text, source)
    print(f"  Indexado: {source} -> {n} chunks")

print(f"\n  Total no indice: {persistent.stats()['documentos_indexados']} chunks\n")

# --- PERGUNTAS ---
perguntas = [
    "Qual o faturamento total da Multilimpeza?",
    "Qual o valor do pedido #456?",
    "Por que o pedido #789 esta pendente?",
    "Qual a aliquota de ICMS para detergentes?",
    "Qual o estoque atual de sabao em po?",
    "Quanto custa o detergente liquido?",
]

print("[2] CONSULTAS MODO PERSISTENTE\n")
for q in perguntas:
    r = engine.ask(q)
    tag = {"[Supported]": "OK", "[Partially]": "~~", "[No Support]": "XX"}.get(r["decision"], "??")
    print(f"  [{tag}] {q}")
    print(f"       -> {r['answer'][:120]}")
    print(f"       (confianca: {r['confidence']:.1%} | fonte: {r['source']})")
    print()

# --- MODO AO VIVO ---
print("[3] MODO AO VIVO\n")

with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
    f.write("MEMORANDO INTERNO\nDesconto especial aprovado de 5% sobre o pedido #456.\nValor final: R$ 14.991,00.\n")
    tmp = f.name

r = live.ask(tmp, "Qual o valor com desconto do pedido #456?")
print(f"  Arquivo: {r.get('file','?')}")
print(f"  Pergunta: Qual o valor com desconto do pedido #456?")
print(f"  Resposta: {r['answer'][:150]}")
print(f"  Decisao: {r['decision']} (confianca: {r['confidence']:.1%})")
os.unlink(tmp)

# --- PDF REAL (opcional) ---
pdf_path = os.environ.get("ORACLE_PDF_PATH")
if pdf_path and os.path.exists(pdf_path):
    print(f"\n[4] TESTE COM PDF REAL\n")
    r = live.ask(pdf_path, "Quais produtos e NCMs sao mencionados?")
    print(f"  PDF: {os.path.basename(pdf_path)}")
    print(f"  Resposta: {r['answer'][:200]}")
    print(f"  Decisao: {r['decision']} (confianca: {r['confidence']:.1%})")

print("\n" + "=" * 60)
print("  DEMONSTRACAO CONCLUIDA")
print("=" * 60)
