# licitaciones-pi

Monorepo base para CedIA - Sistema de Analisis Automatico de Pliegos.

## Requisitos

- Python 3.11+
- Node.js 20+
- PostgreSQL local

## Backend

1. Crear y activar entorno virtual.
2. Instalar dependencias:
   - `c:/Users/AgostinaTorres/Desktop/Proyectos/licitaciones/licitaciones-pi/.venv/Scripts/python.exe -m pip install fastapi uvicorn sqlalchemy alembic pydantic-settings pyjwt passlib[bcrypt] structlog psycopg2-binary pytest httpx ruff email-validator`
3. Crear base local en PostgreSQL:
   - `CREATE DATABASE licitaciones;`
4. Ejecutar backend:
   - `c:/Users/AgostinaTorres/Desktop/Proyectos/licitaciones/licitaciones-pi/.venv/Scripts/python.exe -m uvicorn main:app --reload --app-dir backend`

## Frontend

1. Instalar dependencias:
   - `npm install` (en carpeta `frontend`)
2. Ejecutar frontend:
   - `npm run dev`

## Testing

- Backend: `c:/Users/AgostinaTorres/Desktop/Proyectos/licitaciones/licitaciones-pi/.venv/Scripts/python.exe -m pytest backend/tests`
- Frontend: `npm run test` (en `frontend`)

## Variables de entorno relevantes (Story 2.5)

- `APP_ENV=development|production` (default: development si `USE_LOCAL_ADAPTERS=true`)
- `USE_LOCAL_ADAPTERS=true` para modo local (default)
- `LOCAL_BLOB_STORAGE_PATH=./local_blob_storage` (si no se define, usa `local_blob_storage` en la raiz del repo)
- `MARKITDOWN_ENABLED=true` (development)
- `SENTENCE_TRANSFORMERS_MODEL=BAAI/bge-m3` (development)
- `CHROMA_PERSIST_DIRECTORY=./local_blob_storage/chroma` (development)
- `COHERE_API_KEY=` (development)
- `COHERE_MODEL=command-r-plus` (development)
- `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT=`
- `AZURE_DOCUMENT_INTELLIGENCE_KEY=`
- `AZURE_SEARCH_ENDPOINT=`
- `AZURE_SEARCH_KEY=`
- `AZURE_SEARCH_INDEX_NAME=documents-index`
- `AZURE_OPENAI_ENDPOINT=`
- `AZURE_OPENAI_API_KEY=`
- `AZURE_OPENAI_DEPLOYMENT=gpt-4o-mini`
- `AZURE_OPENAI_EMBEDDING_DEPLOYMENT=text-embedding-ada-002`
- `AZURE_OPENAI_API_VERSION=2023-05-15`
- `EXTRACTION_MAX_CONCURRENCY=4`

## Perfiles de ejecucion

- Development (pruebas desde tu maquina): MarkItDown + chunking estructural + Sentence Transformers (BAAI/bge-m3) + ChromaDB + Cohere.
- Production: Azure Document Intelligence + chunking estructural + Azure OpenAI Embeddings + Azure AI Search + Azure OpenAI.

## Pipeline de extraccion de 8 categorias

- El backend ejecuta un pipeline LangGraph sincrono al finalizar la indexacion.
- Orden del flujo: `setup` -> 8 extractores en paralelo -> `merge`.
- Categorias: plazos, garantias, causales, documentos requeridos, criterios de evaluacion, restricciones de participacion, cronograma del proceso, estimacion de presupuesto.
- Cada categoria aplica retries (2 intentos con backoff), anti-injection y citas verificables.
- Resultado consolidado:
   - Guarda version en `analysis_versions`.
   - Actualiza `analyses.current_version_id`.
   - Persiste conflictos y metadata de costo/tokens.

## Arranque rapido (Windows)

- Script recomendado: `./scripts/dev-start.ps1`
- Que hace:
   - Ejecuta `alembic upgrade head` en backend
   - Ejecuta `seed.py` para crear usuario de prueba si no existe
   - Abre dos terminales nuevas con backend (`uvicorn`) y frontend (`npm run dev`)

Uso:

- `powershell -ExecutionPolicy Bypass -File .\scripts\dev-start.ps1`
- Opcional (instalar dependencias antes de arrancar):
   - `powershell -ExecutionPolicy Bypass -File .\scripts\dev-start.ps1 -InstallDeps`
- Opcional (limpiar storage local antes de arrancar):
   - `powershell -ExecutionPolicy Bypass -File .\scripts\dev-start.ps1 -CleanLocalStorage`
- Modo diagnostico (no arranca procesos):
   - `powershell -ExecutionPolicy Bypass -File .\scripts\dev-start.ps1 -DryRun`

Limpieza manual de storage local:

- `powershell -ExecutionPolicy Bypass -File .\scripts\clean-local-storage.ps1`
