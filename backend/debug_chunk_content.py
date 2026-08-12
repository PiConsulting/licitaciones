"""Script para ver el contenido completo de un chunk específico."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from shared.ports.azure_search import search_hybrid

console = Console()

analysis_id = "162587f0-5c70-48de-ac11-ffbd584a2d69"
category = "requisitos_admisibilidad"

chunks = search_hybrid(
    query="requisitos",
    analysis_id=analysis_id,
    top_k=10,
    keyword_query=None,
    category_filter=category,
)

console.print(f"\n[bold]Total chunks: {len(chunks)}[/bold]\n")

for i, chunk in enumerate(chunks, 1):
    console.print(Panel(
        f"[bold]Document ID:[/bold] {chunk.get('document_id', 'N/A')}\n"
        f"[bold]Page:[/bold] {chunk.get('page_number', 'N/A')}\n"
        f"[bold]Chunk Index:[/bold] {chunk.get('chunk_index', 'N/A')}\n"
        f"[bold]Primary Category:[/bold] {chunk.get('primary_category', 'N/A')}\n"
        f"[bold]Secondary Categories:[/bold] {chunk.get('secondary_categories', [])}\n"
        f"[bold]Section Path:[/bold] {chunk.get('section_path', 'N/A')}\n"
        f"[bold]Title:[/bold] {chunk.get('title', 'N/A')}\n\n"
        f"[bold cyan]CONTENT:[/bold cyan]\n{chunk.get('content', 'N/A')}",
        title=f"Chunk {i}",
        border_style="cyan",
    ))

# Ver todos los chunks sin filtro
console.print("\n" + "="*80)
console.print("[bold yellow]TODOS LOS CHUNKS (sin filtro):[/bold yellow]\n")

all_chunks = search_hybrid(
    query="requisitos",
    analysis_id=analysis_id,
    top_k=30,
    keyword_query=None,
    category_filter=None,
)

for chunk in all_chunks:
    console.print(
        f"[dim]Page {chunk.get('page_number')}, Chunk {chunk.get('chunk_index')} - "
        f"Primary: {chunk.get('primary_category')} - "
        f"Title: {chunk.get('title', 'N/A')[:60]}...[/dim]"
    )
