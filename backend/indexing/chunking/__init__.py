"""Chunking: arma bloques intermedios, clasifica por categoria y produce chunks finales.

Reexporta `create_chunks`, el unico simbolo que el resto del backend importa desde
aca (`from indexing.chunking import create_chunks`)."""
from indexing.chunking.chunking import create_chunks

__all__ = ["create_chunks"]
