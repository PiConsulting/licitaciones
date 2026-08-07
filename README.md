# licitaciones-pi

Monorepo base para CedIA - Sistema de Analisis Automatico de Pliegos.

## Requisitos

- Python 3.11+
- Node.js 20+
- Recursos de Azure provisionados (ver [Servicios de Azure requeridos](#servicios-de-azure-requeridos)):
  - Azure Database for PostgreSQL (o Azure Cosmos DB, segun `PERSISTENCE_MODE`)
  - Azure Blob Storage
  - Azure AI Document Intelligence
  - Azure AI Search
  - Azure OpenAI (chat + embeddings)

Este proyecto corre contra el ecosistema de Azure (`APP_ENV=production`). El perfil local (ChromaDB, Cohere, Sentence Transformers) es solo un modo de desarrollo offline opcional — ver [Perfiles de ejecucion](#perfiles-de-ejecucion).

## Servicios de Azure requeridos

Antes de instalar, tene a mano las credenciales de:

- **Azure Database for PostgreSQL** (o Cosmos DB si vas a usar `PERSISTENCE_MODE=cosmos_only`): cadena de conexion.
- **Azure Blob Storage**: connection string y nombre de contenedor.
- **Azure AI Document Intelligence**: endpoint y key.
- **Azure AI Search**: endpoint, key y nombre de indice.
- **Azure OpenAI**: endpoint, key, deployment de chat, deployment de embeddings y version de API.
- **Azure Cosmos DB** (solo si `PERSISTENCE_MODE` es `cosmos`, `dual_write`, `cosmos_temporal` o `cosmos_only`): endpoint, key, database y container.

## Backend

1. Crear y activar entorno virtual (Windows):
   - `python -m venv .venv`
   - `.venv\Scripts\activate`
2. Instalar dependencias desde `backend/requirements.txt` (pinneadas, generadas con `pip-compile` desde `backend/pyproject.toml`):
   - `.venv\Scripts\python.exe -m pip install -r backend/requirements.txt`
   - Para desarrollo (incluye `pytest` y `ruff`): `.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt`
3. Configurar variables de entorno:
   - Copiar `.env.example` a `.env` en la raiz del repo.
   - Setear `APP_ENV=production` y `USE_LOCAL_ADAPTERS=false`.
   - Completar todas las credenciales de Azure listadas en [Variables de entorno relevantes](#variables-de-entorno-relevantes-story-25).
   - `DATABASE_URL` debe apuntar a la instancia de Azure Database for PostgreSQL (no `localhost`; el arranque en `production` rechaza hosts locales salvo en modo `cosmos_temporal`/`cosmos_only`).
4. Aplicar migraciones (desde `backend`, contra la base de Azure):
   - `cd backend && ..\.venv\Scripts\python.exe -m alembic upgrade head`
5. (Opcional) Crear usuario de prueba:
   - `.venv\Scripts\python.exe backend/seed.py`
6. Ejecutar backend:
   - `.venv\Scripts\python.exe -m uvicorn main:app --reload --app-dir backend`


## Frontend

1. Instalar dependencias:
   - `npm install` (en carpeta `frontend`)
2. Configurar variables de entorno:
   - `VITE_API_BASE_URL` se toma del `.env` en la raiz (ver `.env.example`).
3. Ejecutar frontend:
   - `npm run dev`

## Testing

- Backend: `.venv\Scripts\python.exe -m pytest backend/tests`
- Frontend: `npm run test` (en `frontend`)

## Variables de entorno relevantes (Story 2.5)

- `APP_ENV=production`
- `USE_LOCAL_ADAPTERS=false`
- `DATABASE_URL=` cadena de conexion a Azure Database for PostgreSQL
- `PERSISTENCE_MODE=` uno de `sql`, `cosmos`, `dual_write`, `cosmos_temporal`, `cosmos_only`

Azure Blob Storage:

- `AZURE_BLOB_CONNECTION_STRING=`
- `AZURE_BLOB_CONTAINER_NAME=documents`

Azure AI Document Intelligence:

- `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=`
- `AZURE_DOCUMENT_INTELLIGENCE_KEY=`
- `DOCUMENT_INTELLIGENCE_TIMEOUT_SECONDS=60`
- `DOCUMENT_INTELLIGENCE_RETRY_ATTEMPTS=3`

Azure AI Search:

- `AZURE_SEARCH_ENDPOINT=`
- `AZURE_SEARCH_KEY=`
- `AZURE_SEARCH_INDEX_NAME=documents-index`
- `AZURE_SEARCH_UPLOAD_BATCH_SIZE=1000`
- `AZURE_SEARCH_RETRY_ATTEMPTS=3`

Azure OpenAI:

- `AZURE_OPENAI_ENDPOINT=`
- `AZURE_OPENAI_API_KEY=`
- `AZURE_OPENAI_API_VERSION=2024-10-21`
- `AZURE_OPENAI_DEPLOYMENT=` (deployment de chat)
- `AZURE_OPENAI_EMBEDDING_DEPLOYMENT=` (deployment de embeddings)
- `AZURE_OPENAI_EMBEDDINGS_BATCH_SIZE=16`
- `AZURE_OPENAI_RETRY_ATTEMPTS=3`

Azure Cosmos DB (solo si `PERSISTENCE_MODE` es `cosmos`, `dual_write`, `cosmos_temporal` o `cosmos_only`):

- `COSMOS_ENDPOINT=`
- `COSMOS_KEY=`
- `COSMOS_DATABASE=`
- `COSMOS_CONTAINER=`

Otras:

- `EXTRACTION_MAX_CONCURRENCY=4`
- `LOG_LEVEL=INFO`
- `AZURE_SDK_LOG_LEVEL=WARNING`

## Perfiles de ejecucion

- **Production (Azure, recomendado)**: `APP_ENV=production`. Azure Document Intelligence + chunking estructural + Azure OpenAI Embeddings + Azure AI Search + Azure OpenAI. Requiere todas las credenciales de Azure listadas arriba; se valida al arrancar (`validate_cloud_configuration`).
- **Development (local, opcional)**: `APP_ENV=development` / `USE_LOCAL_ADAPTERS=true`. Usa MarkItDown + Sentence Transformers (BAAI/bge-m3) + ChromaDB + Cohere en lugar de los servicios de Azure. Util solo para desarrollo offline sin credenciales de Azure a mano.

## Pipeline de extraccion de 8 categorias

- El backend ejecuta un pipeline LangGraph sincrono al finalizar la indexacion.
- Orden del flujo: `setup` -> 8 extractores en paralelo -> `merge`.
- Categorias: plazos, garantias, causales, documentos requeridos, criterios de evaluacion, restricciones de participacion, cronograma del proceso, estimacion de presupuesto.
- Cada categoria aplica retries (2 intentos con backoff), anti-injection y citas verificables.
- Resultado consolidado:
   - Guarda version en `analysis_versions`.
   - Actualiza `analyses.current_version_id`.
   - Persiste conflictos y metadata de costo/tokens.

