"""Inspeccionar contenido de todos los chunks de un análisis."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from shared.ports.azure_search import search_hybrid

console = Console()

if len(sys.argv) < 2:
    console.print("[red]Error: Falta analysis_id[/red]")
    console.print("\nUso: python debug_chunks_content.py <analysis_id>")
    sys.exit(1)

analysis_id = sys.argv[1]

# Obtener TODOS los chunks del análisis
all_chunks = search_hybrid(
    query="*",
    analysis_id=analysis_id,
    top_k=1000,
    keyword_query=None,
    category_filter=None,
)

console.print(f"\n[bold]Total chunks: {len(all_chunks)}[/bold]\n")

# Agrupar por categoría
by_category = {}
for chunk in all_chunks:
    primary = chunk.get("primary_category", "unknown")
    if primary not in by_category:
        by_category[primary] = []
    by_category[primary].append(chunk)

# Tabla resumen
table = Table(title="Distribución de Chunks por Categoría")
table.add_column("Categoría", style="cyan")
table.add_column("Cantidad", style="green")
table.add_column("Páginas", style="yellow")

for cat in sorted(by_category.keys()):
    chunks = by_category[cat]
    pages = sorted(set(c.get("page_number", 0) for c in chunks))
    table.add_row(cat, str(len(chunks)), str(pages))

console.print(table)

# Buscar causales de rechazo en el contenido
console.print("\n[bold magenta]BÚSQUEDA DE CAUSALES DE RECHAZO:[/bold magenta]\n")
keywords = ["rechaz", "desestim", "exclus", "descalif", "inadmisi", "no ser considerada", "quedará excluida"]

matches = []
for chunk in all_chunks:
    content = chunk.get("content", "").lower()
    for keyword in keywords:
        if keyword in content:
            matches.append((chunk, keyword))
            break

if matches:
    console.print(f"[green]Encontrados {len(matches)} chunks con palabras relacionadas a rechazo:[/green]\n")
    for i, (chunk, keyword) in enumerate(matches[:5], 1):
        primary = chunk.get("primary_category", "unknown")
        page = chunk.get("page_number", "?")
        content_preview = chunk.get("content", "")[:300]
        
        console.print(Panel(
            f"[bold]Primary Category:[/bold] {primary}\n"
            f"[bold]Keyword Match:[/bold] {keyword}\n"
            f"[dim]Page {page}[/dim]\n\n"
            f"{content_preview}...",
            title=f"Chunk {i}",
            border_style="yellow",
        ))
else:
    console.print("[red]NO se encontraron chunks con palabras relacionadas a rechazo[/red]")

# Buscar anexos en el contenido
console.print("\n[bold magenta]BÚSQUEDA DE ANEXOS OBLIGATORIOS:[/bold magenta]\n")
keywords_anexos = ["anexo", "formulario", "declaracion jurada", "planilla de cotizacion", "debe presentar"]

matches_anexos = []
for chunk in all_chunks:
    content = chunk.get("content", "").lower()
    for keyword in keywords_anexos:
        if keyword in content:
            matches_anexos.append((chunk, keyword))
            break

if matches_anexos:
    console.print(f"[green]Encontrados {len(matches_anexos)} chunks con palabras relacionadas a anexos:[/green]\n")
    for i, (chunk, keyword) in enumerate(matches_anexos[:10], 1):
        primary = chunk.get("primary_category", "unknown")
        page = chunk.get("page_number", "?")
        title = chunk.get("title", "N/A")
        content_preview = chunk.get("content", "")[:200]
        
        console.print(Panel(
            f"[bold]Primary Category:[/bold] {primary}\n"
            f"[bold]Keyword Match:[/bold] {keyword}\n"
            f"[bold]Title:[/bold] {title}\n"
            f"[dim]Page {page}[/dim]\n\n"
            f"{content_preview}...",
            title=f"Chunk {i}",
            border_style="cyan" if primary == "anexos_obligatorios" else "red",
        ))
else:
    console.print("[red]NO se encontraron chunks con palabras relacionadas a anexos[/red]")
