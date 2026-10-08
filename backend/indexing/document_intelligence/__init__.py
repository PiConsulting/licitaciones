"""Document Intelligence: parsea el layout de Azure DI a bloques de chunking.

Reexporta `extract_text`, el unico simbolo que el resto del backend importa desde
aca (`from indexing.document_intelligence import extract_text`)."""
from indexing.document_intelligence.adapter import extract_text

__all__ = ["extract_text"]
