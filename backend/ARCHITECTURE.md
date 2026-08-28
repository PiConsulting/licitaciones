/# Arquitectura: puertos y adapters

Este backend usa PostgreSQL (con la extensión `pgvector` para búsqueda
vectorial/híbrida) como único backend de persistencia. Hasta la Épica 22
(migración completada 2026-08-28) usaba Cosmos DB (metadata/runtime) y Azure
AI Search (vectores) — ver `docs/docu/PLAN-migracion-cosmos-postgres-pgvector.md`
y `docs/docu/pgvector-retrieval-runbook.md` para el detalle de esa migración y
cómo funciona el retrieval actual. Las piezas que hablan con un proveedor
externo se siguen accediendo detrás de un **puerto**: una interfaz chica
(`typing.Protocol` o `ABC`) que describe el contrato, implementada por un
**adapter** concreto para ese proveedor — el patrón sobrevivió la migración
sin cambios, sólo cambiaron los adapters concretos detrás de cada puerto.

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
Exactamente este razonamiento es el que permitió que la Épica 22 reemplazara
Cosmos DB/Azure AI Search por Postgres/pgvector escribiendo adapters nuevos sin
tocar el código de negocio que los consume.

## Los puntos de corte

| Punto de corte | Puerto | Adapter actual | Se inyecta en |
|---|---|---|---|
| Document Intelligence (OCR/layout) | `indexing/ports/document_intelligence_port.py::DocumentIntelligencePort` | `indexing/document_intelligence/adapter.py::AzureDocumentIntelligenceAdapter` | `indexing/runner.py::_build_document_intelligence` |
| Embeddings | `indexing/ports/embeddings_port.py::EmbeddingsPort` | `indexing/embeddings.py::AzureEmbeddingsAdapter` | `indexing/runner.py::_build_embeddings` |
| Búsqueda vectorial/híbrida (escritura: subir/borrar chunks) | `indexing/ports/search_client_port.py::SearchClientPort` | `infra/adapters/pgvector_search.py::PgVectorSearchAdapter` | `indexing/runner.py::_build_search_client` |
| Búsqueda vectorial/híbrida (lectura: retrieval) | sin puerto formal — `infra/ports/pgvector_search.py::search_hybrid`/`fetch_all_analysis_chunks`, funciones de módulo | — (reemplaza `infra/ports/azure_search.py`, ver "Qué NO pasa por un puerto") | `analysis/extraction/engine/chunk_retrieval.py` |

Los tres primeros siguen exactamente el patrón de `BlobStoragePort`: cada
módulo de `indexing/` expone también una función pública (`extract_text`,
`generate_embeddings`, `upload_chunks`) con la lógica de reintentos/logging/
validación que ya existía, y acepta el adapter como parámetro opcional — si no
se pasa uno, lo construye internamente (`_build_adapter()`). Eso mantiene
compatibilidad con los callers que no necesitan inyectar nada (scripts,
tests unitarios de cada módulo) sin duplicar la lógica de orquestación.

Document Intelligence, embeddings y blob storage siguen sobre Azure — la
migración de la Épica 22 fue específicamente de metadata/runtime (Cosmos) y
búsqueda vectorial (Azure AI Search) a Postgres/pgvector, no de todo el
sistema. Ver la sección 1.2 del plan de migración para el detalle de qué
quedó explícitamente fuera de alcance.

No existe más una capa de persistencia de metadata de análisis separada del
resto (`AnalysisMetadataSink`/dual-write se eliminaron con la Épica 22): las
tablas `analyses`/`documents`/`analysis_versions`/`events`/`deadlines`/
`tracking*` son SQLAlchemy contra Postgres directo, sin puerto intermedio —
son el modelo de datos propio del backend, no un proveedor externo
intercambiable, así que no aplica el mismo patrón.

## Qué NO pasa por un puerto (a propósito)

`infra/ports/pgvector_search.py` (búsqueda de lectura: `search_hybrid`,
`fetch_all_analysis_chunks`, expansión parent/child) es un módulo de
funciones, no una clase detrás de un `Protocol`/`ABC` — no hay un segundo
proveedor de búsqueda al que migrar, así que no vale la pena la abstracción
extra. Es el reemplazo directo de `infra/ports/azure_search.py` (borrado en
la Épica 22): mismo contrato de salida (lista de dicts de chunk), para que
`chunk_retrieval.py` y el resto del pipeline de extracción no tuvieran que
cambiar.

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
