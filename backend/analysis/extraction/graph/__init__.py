"""Grafo de extraccion (LangGraph): setup -> extractores -> merge -> synthesize.

Reexporta `graph`, el unico simbolo que el resto del backend importa desde
aca (`from analysis.extraction.graph import graph`)."""
from analysis.extraction.graph.nodes import graph

__all__ = ["graph"]
