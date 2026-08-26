/# Arquitectura: puertos y adapters

Este backend usa Cosmos DB (metadata/runtime) y Azure AI Search (vectores) hoy,
con la migración a Postgres/pgvector planeada como trabajo futuro. Para que esa
migración sea acotada (cambiar adapters, no perseguir imports de Azure por todo
el pipeline), las piezas que hablan con un proveedor externo se acceden detrás
de un **puerto**: una interfaz chica (`typing.Protocol` o `ABC`) que describe
el contrato, implementada por un **adapter** concreto para ese proveedor.

## El patrón, con el ejemplo ya resuelto

`infra/ports/blob_storage.py` define el puerto:

```python
class BlobStoragePort(ABC):
    def upload(self, blob_name: str, content: bytes) -> str: ...
    def delete(self, blob_name: str) -> None: ...
    def generate_download_url(self, blob_name: str) -> str: ...
```

`infra/adapters/azure_blob_storage.py` lo implementa para Azure Blob Storage:

```python
class AzureBlobStorageAdapter(BlobStoragePort):
    ...
```

Y el punto de composición (`indexing/runner.py::extract_and_index`) construye
el adapter una sola vez y lo pasa por parámetro, en vez de que el código de
negocio importe Azure directamente:

```python
def _build_blob_storage() -> BlobStoragePort:
    ...
    return AzureBlobStorageAdapter(...)

def extract_and_index(analysis_id: str) -> None:
    blob_storage = _build_blob_storage()
    ...
    blob_url = blob_storage.generate_download_url(document.blob_name)
```

El día que se migre el storage de blobs a otro proveedor, alcanza con escribir
un `OtroProveedorAdapter(BlobStoragePort)` nuevo y cambiar `_build_blob_storage`
— nada del resto del pipeline sabe qué adapter está corriendo detrás del puerto.

## Los 4 puntos de corte para la migración a Postgres/pgvector

| Punto de corte | Puerto | Adapter actual | Se inyecta en |
|---|---|---|---|
| Document Intelligence (OCR/layout) | `indexing/ports/document_intelligence_port.py::DocumentIntelligencePort` | `indexing/document_intelligence/adapter.py::AzureDocumentIntelligenceAdapter` | `indexing/runner.py::_build_document_intelligence` |
| Embeddings | `indexing/ports/embeddings_port.py::EmbeddingsPort` | `indexing/embeddings.py::AzureEmbeddingsAdapter` | `indexing/runner.py::_build_embeddings` |
| Búsqueda vectorial/híbrida | `indexing/ports/search_client_port.py::SearchClientPort` | `indexing/ai_search.py::AzureSearchAdapter` | `indexing/runner.py::_build_search_client` |
| Persistencia de metadata de análisis | `analysis/metadata_persistence.py::AnalysisMetadataSink` | `SqlMetadataSink` / `CosmosMetadataSink` / `DualWriteMetadataSink` | `analysis/metadata_persistence.py::build_metadata_sink` |

Los tres primeros siguen exactamente el patrón de `BlobStoragePort`: cada
módulo de `indexing/` expone también una función pública (`extract_text`,
`generate_embeddings`, `upload_chunks`) con la lógica de reintentos/logging/
validación que ya existía, y acepta el adapter como parámetro opcional — si no
se pasa uno, lo construye internamente (`_build_adapter()`). Eso mantiene
compatibilidad con los callers que no necesitan inyectar nada (scripts,
tests unitarios de cada módulo) sin duplicar la lógica de orquestación.

`AnalysisMetadataSink` sigue el mismo espíritu con una variante: como el
proyecto ya soporta *dual write* (escribir a SQL y Cosmos a la vez durante la
transición), el "adapter" que se inyecta puede ser un compuesto
(`DualWriteMetadataSink`) que delega en dos sinks reales. `build_metadata_sink`
decide cuál construir según `PERSISTENCE_MODE`.

## Qué NO pasa por un puerto (a propósito)

`infra/ports/azure_search.py` (búsqueda legacy, camino de lectura) y
`analysis/cosmos_runtime.py` (runtime de Cosmos) se reemplazan enteros el día
de la migración — no vale la pena introducir una abstracción para código que
se va a borrar. Quedan, eso sí, tratados como código detrás de los puertos de
arriba desde el punto de vista de sus *callers*.

## Convención para archivos grandes: carpeta por responsabilidad

Cuando un módulo crece a un archivo plano con muchas funciones sin relación
directa, se convierte en una carpeta con un módulo por responsabilidad real
(no genéricos tipo `utils.py`). El archivo que queda con el mismo nombre que
la carpeta (p. ej. `chunking/chunking.py` dentro de `indexing/chunking/`) es
el único que expone símbolos fuera de la carpeta — vía el `__init__.py`, que
reexporta lo que el resto del backend importa. Los demás módulos de la carpeta
son de uso interno: se importan entre sí (con imports diferidos puntuales
donde hace falta romper un ciclo), pero nada externo debería importarlos
directo salvo tests de caja blanca sobre una función interna puntual.

Ejemplos ya aplicados: `analysis/extraction/extractors/`,
`analysis/extraction/engine/`, `indexing/chunking/`,
`indexing/document_intelligence/`, `analysis/extraction/graph/`,
`analysis/extraction/synthesis/`, `analysis/extraction/highlight/`,
`tracking/service/`, `analysis/service/`.
