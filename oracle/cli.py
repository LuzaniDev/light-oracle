import typer
import json
import sys
import os
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.markdown import Markdown

from .utils.config import OracleConfig
from .engine import OracleEngine
from .pipeline.live import LivePipeline
from .pipeline.persistent import PersistentPipeline

app = typer.Typer(
    name="oracle",
    help="Light Oracle RAG — Oráculo RAG leve para CPU",
)
console = Console()


def get_pipelines():
    config = OracleConfig()
    engine = OracleEngine(config)
    live = LivePipeline(engine)
    persistent = PersistentPipeline(engine)
    return live, persistent, engine


@app.command()
def ask(
    query: str = typer.Argument(..., help="Pergunta a ser respondida"),
    file: Optional[str] = typer.Option(None, "--file", "-f", help="Arquivo para modo ao vivo"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Saída em JSON"),
):
    live, persistent, engine = get_pipelines()

    if file:
        if not os.path.exists(file):
            console.print(f"[red]Erro:[/red] Arquivo não encontrado: {file}")
            raise typer.Exit(1)
        console.print(f"[yellow]Processando[/yellow] {os.path.basename(file)}...")
        result = live.ask(file, query)
    else:
        stats = persistent.stats()
        if stats["documentos_indexados"] == 0:
            console.print("[yellow]Nenhum documento indexado. Use 'oracle index' primeiro ou --file para modo ao vivo.[/yellow]")
            raise typer.Exit(1)
        result = persistent.ask(query)

    if json_output:
        console.print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _print_result(result)


@app.command()
def index(
    path: str = typer.Argument(..., help="Arquivo ou diretório para indexar"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Saída em JSON"),
):
    live, persistent, engine = get_pipelines()
    result = persistent.index(path)

    if json_output:
        console.print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if isinstance(result, list):
            total = sum(r.get("chunks", 0) for r in result if "chunks" in r)
            errors = [r for r in result if "error" in r]
            console.print(f"[green]Indexados:[/green] {len(result) - len(errors)} arquivos, {total} chunks")
            if errors:
                for err in errors:
                    console.print(f"[red]Erro:[/red] {err.get('file', '?')} - {err['error']}")
        elif isinstance(result, dict):
            if "error" in result:
                console.print(f"[red]Erro:[/red] {result['error']}")
            else:
                console.print(f"[green]Indexado:[/green] {result.get('file', '?')} — {result.get('chunks', 0)} chunks")


@app.command()
def stats(
    json_output: bool = typer.Option(False, "--json", "-j", help="Saída em JSON"),
):
    live, persistent, engine = get_pipelines()
    s = persistent.stats()

    if json_output:
        console.print(json.dumps(s, ensure_ascii=False, indent=2))
    else:
        table = Table(title="📊 Estatísticas do Oráculo")
        table.add_column("Métrica", style="cyan")
        table.add_column("Valor", style="green")
        table.add_row("Documentos indexados", str(s["documentos_indexados"]))
        table.add_row("Índice denso carregado", "✅ Sim" if s["indice_denso_carregado"] else "❌ Não")
        console.print(table)


@app.command()
def interactive():
    live, persistent, engine = get_pipelines()
    console.print("[bold cyan]Oráculo RAG — Modo Interativo[/bold cyan]")
    console.print("Comandos: /file <caminho> | /index <caminho> | /stats | /clear | /exit")
    current_file = None

    while True:
        query = typer.prompt("\n❓ Pergunta")
        if query.startswith("/"):
            cmd = query[1:].strip().split()
            if not cmd:
                continue
            if cmd[0] == "exit":
                break
            elif cmd[0] == "file":
                if len(cmd) < 2:
                    console.print("[yellow]Uso: /file <caminho>[/yellow]")
                else:
                    fpath = " ".join(cmd[1:])
                    if os.path.exists(fpath):
                        current_file = fpath
                        console.print(f"[green]Arquivo carregado:[/green] {os.path.basename(fpath)}")
                    else:
                        console.print(f"[red]Arquivo não encontrado:[/red] {fpath}")
            elif cmd[0] == "index":
                if len(cmd) < 2:
                    console.print("[yellow]Uso: /index <caminho>[/yellow]")
                else:
                    result = persistent.index(" ".join(cmd[1:]))
                    if isinstance(result, list):
                        console.print(f"[green]Indexados {len(result)} arquivos[/green]")
                    else:
                        console.print(result.get("status", "Indexado"))
            elif cmd[0] == "stats":
                s = persistent.stats()
                console.print(f"Documentos: {s['documentos_indexados']}, Denso: {s['indice_denso_carregado']}")
            elif cmd[0] == "clear":
                os.system("cls" if os.name == "nt" else "clear")
            continue

        if current_file:
            result = live.ask(current_file, query)
        else:
            result = persistent.ask(query)

        _print_result(result)


def _print_result(result: dict):
    if "error" in result:
        console.print(f"[red]Erro:[/red] {result['error']}")
        return

    decision = result.get("decision", "")
    confidence = result.get("confidence", 0)

    color = "green" if confidence >= 0.85 else ("yellow" if confidence >= 0.60 else "red")
    label = {
        "[Supported]": "✅ Suportado",
        "[Partially]": "⚠️ Parcial",
        "[No Support]": "❌ Não encontrado",
        "[No Retrieve]": "ℹ️ Sem consulta",
    }.get(decision, decision)

    panel = Panel(
        f"[bold]{result.get('answer', '')}[/bold]",
        title=f"{label} | Confiança: {confidence:.1%}",
        border_style=color,
    )
    console.print(panel)

    if result.get("chunks"):
        console.print("\n[dim]Fontes consultadas:[/dim]")
        for c in result["chunks"]:
            console.print(f"  [dim]• {c['source']}[/dim] (score: {c['score']:.3f})")


def main():
    app()


if __name__ == "__main__":
    main()
