"""
Script de debugging para analizar el problema de retrieval RAG.

Muestra:
1. Qué chunks se recuperan para cada categoría
2. Cómo están clasificados (primary_category, secondary_categories)
3. Pureza del retrieval (% de chunks relevantes)
4. Contenido real de los chunks para verificar si hay overlaps

Uso:
    python debug_retrieval.py <analysis_id> [categoria]
    
Ejemplos:
    python debug_retrieval.py 162587f0-5c70-48de-ac11-ffbd584a2d69
    python debug_retrieval.py 162587f0-5c70-48de-ac11-ffbd584a2d69 requisitos_admisibilidad
"""

import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

import structlog
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax

from shared.ports.azure_search import search_hybrid
from analysis.extraction.glossary import build_keyword_query
from shared.config import get_settings
from analysis.extraction.extractors.base import _retrieve_with_category_priority

logger = structlog.get_logger(__name__)
console = Console()

CATEGORIES = [
    "objeto_alcance",
    "requisitos_admisibilidad",
    "garantias",
    "plazos_clave",
    "criterios_evaluacion",
    "causales_rechazo",
    "anexos_obligatorios",
]

CATEGORY_QUERIES = {
    "objeto_alcance": "Qué se licita, descripción del objeto, alcance de la contratación, lugar de entrega, modalidad de prestación",
    "requisitos_admisibilidad": "Documentación obligatoria para que la oferta no sea rechazada de entrada: inscripción en registros, certificados fiscales, habilitaciones, antecedentes",
    "garantias": "Garantías financieras: mantenimiento de oferta, cumplimiento de contrato, monto, forma de constitución, vigencia",
    "plazos_clave": "Fechas y plazos críticos: apertura de ofertas, mantenimiento de oferta, entrega, consultas, impugnaciones",
    "criterios_evaluacion": "Cómo se evalúan y ponderan las ofertas: precio, técnica, puntajes, factores de ponderación",
    "causales_rechazo": "Motivos de rechazo o descalificación de ofertas que no permiten evaluación",
    "anexos_obligatorios": "Formularios y anexos que deben completarse y presentarse con la oferta",
}


def analyze_retrieval(analysis_id: str, category: str | None = None):
    """Analiza el retrieval para una o todas las categorías."""
    settings = get_settings()
    
    categories_to_check = [category] if category else CATEGORIES
    
    for cat in categories_to_check:
        console.print(f"\n[bold cyan]{'='*80}[/bold cyan]")
        console.print(f"[bold yellow]CATEGORÍA: {cat.upper()}[/bold yellow]")
        console.print(f"[bold cyan]{'='*80}[/bold cyan]\n")
        
        query = CATEGORY_QUERIES.get(cat, "")
        keyword_query = build_keyword_query(cat)
        top_k = settings.extraction_top_k
        
        console.print(f"[dim]Query: {query}[/dim]")
        console.print(f"[dim]Keywords: {keyword_query}[/dim]")
        console.print(f"[dim]Top-K: {top_k}[/dim]\n")
        
        # Retrieval CON ajuste dinámico (función real del extractor)
        with_priority = _retrieve_with_category_priority(
            query=query,
            analysis_id=analysis_id,
            top_k=top_k,
            keyword_query=keyword_query,
            category=cat,
            correlation_id="debug",
        )
        
        # Retrieval CON filtro de categoría (sin backfill)
        with_filter = search_hybrid(
            query=query,
            analysis_id=analysis_id,
            top_k=top_k,
            keyword_query=keyword_query,
            category_filter=cat,
        )
        
        # Retrieval SIN filtro (backfill sin límite)
        without_filter = search_hybrid(
            query=query,
            analysis_id=analysis_id,
            top_k=top_k,
            keyword_query=keyword_query,
            category_filter=None,
        )
        
        # Análisis de pureza
        cat_distribution_priority = {}
        cat_distribution_with = {}
        cat_distribution_without = {}
        
        for chunk in with_priority:
            primary = chunk.get("primary_category", "unknown")
            cat_distribution_priority[primary] = cat_distribution_priority.get(primary, 0) + 1
        
        for chunk in with_filter:
            primary = chunk.get("primary_category", "unknown")
            cat_distribution_with[primary] = cat_distribution_with.get(primary, 0) + 1
        
        for chunk in without_filter:
            primary = chunk.get("primary_category", "unknown")
            cat_distribution_without[primary] = cat_distribution_without.get(primary, 0) + 1
        
        # Tabla de distribución
        table = Table(title=f"Distribución de categorías recuperadas")
        table.add_column("Primary Category", style="cyan")
        table.add_column("Con prioridad (NEW)", style="magenta")
        table.add_column("Con filtro", style="green")
        table.add_column("Sin filtro", style="yellow")
        
        all_cats = set(cat_distribution_priority.keys()) | set(cat_distribution_with.keys()) | set(cat_distribution_without.keys())
        for c in sorted(all_cats):
            table.add_row(
                c,
                str(cat_distribution_priority.get(c, 0)),
                str(cat_distribution_with.get(c, 0)),
                str(cat_distribution_without.get(c, 0)),
            )
        
        console.print(table)
        
        # Pureza
        target_priority = sum(
            1 for chunk in with_priority
            if chunk.get("primary_category") == cat or cat in chunk.get("secondary_categories", [])
        )
        purity_priority = (target_priority / len(with_priority) * 100) if with_priority else 0
        
        target_with = sum(
            1 for chunk in with_filter
            if chunk.get("primary_category") == cat or cat in chunk.get("secondary_categories", [])
        )
        purity_with = (target_with / len(with_filter) * 100) if with_filter else 0
        
        target_without = sum(
            1 for chunk in without_filter
            if chunk.get("primary_category") == cat or cat in chunk.get("secondary_categories", [])
        )
        purity_without = (target_without / len(without_filter) * 100) if without_filter else 0
        
        console.print(f"\n[bold magenta]Pureza con prioridad (NEW):[/bold magenta] {purity_priority:.1f}% ({target_priority}/{len(with_priority)} chunks)")
        console.print(f"[bold]Pureza con filtro:[/bold] {purity_with:.1f}% ({target_with}/{len(with_filter)} chunks)")
        console.print(f"[bold]Pureza sin filtro:[/bold] {purity_without:.1f}% ({target_without}/{len(without_filter)} chunks)")
        
        # Mostrar contenido de chunks problemáticos
        console.print(f"\n[bold magenta]CHUNKS RECUPERADOS (CON PRIORIDAD - NEW):[/bold magenta]")
        for i, chunk in enumerate(with_priority[:5], 1):  # Primeros 5
            primary = chunk.get("primary_category", "unknown")
            secondary = chunk.get("secondary_categories", [])
            content_preview = chunk.get("content", "")[:200]
            page = chunk.get("page_number", "?")
            chunk_index = chunk.get("chunk_index", "?")
            
            is_target = primary == cat or cat in secondary
            color = "green" if is_target else "red"
            
            console.print(Panel(
                f"[{color}]Primary: {primary}[/{color}]\n"
                f"[dim]Secondary: {secondary}[/dim]\n"
                f"[dim]Page {page}, Chunk {chunk_index}[/dim]\n\n"
                f"{content_preview}...",
                title=f"Chunk {i}",
                border_style=color,
            ))
        
        if not with_priority:
            console.print("[red]⚠ NO SE RECUPERARON CHUNKS CON PRIORIDAD[/red]")
        
        console.print(f"\n[dim]Total chunks con prioridad (NEW): {len(with_priority)}[/dim]")
        console.print(f"[dim]Total chunks con filtro: {len(with_filter)}[/dim]")
        console.print(f"[dim]Total chunks sin filtro: {len(without_filter)}[/dim]")


def main():
    if len(sys.argv) < 2:
        console.print("[red]Error: Falta analysis_id[/red]")
        console.print("\nUso: python debug_retrieval.py <analysis_id> [categoria]")
        console.print("\nCategorías disponibles:")
        for cat in CATEGORIES:
            console.print(f"  - {cat}")
        sys.exit(1)
    
    analysis_id = sys.argv[1]
    category = sys.argv[2] if len(sys.argv) > 2 else None
    
    if category and category not in CATEGORIES:
        console.print(f"[red]Error: Categoría inválida: {category}[/red]")
        console.print("\nCategorías válidas:")
        for cat in CATEGORIES:
            console.print(f"  - {cat}")
        sys.exit(1)
    
    console.print(Panel(
        f"[bold]Analysis ID:[/bold] {analysis_id}\n"
        f"[bold]Categoría:[/bold] {category or 'Todas'}",
        title="DEBUG RETRIEVAL RAG",
        border_style="cyan",
    ))
    
    analyze_retrieval(analysis_id, category)


if __name__ == "__main__":
    main()
