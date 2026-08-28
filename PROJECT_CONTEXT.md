# PROJECT_CONTEXT.md

> **Leer antes de cualquier cambio.** Contexto canónico para agentes de IA.

---

## Overview

**CedIA** es un sistema de análisis automático de pliegos (documentos de licitaciones públicas). Los usuarios suben PDFs, el sistema los valida, detecta duplicados y ejecuta un pipeline de análisis. El backend expone una API REST; el frontend es una SPA React.

---

## Tech Stack

| Capa           | Tecnología                                                                 |
|----------------|----------------------------------------------------------------------------|
| Frontend       | React 18 + TypeScript, Vite, TailwindCSS, React Query, Zustand, Axios     |
| Backend        | FastAPI + Python 3.11+, Pydantic Settings, PyJWT, SQLAlchemy/Alembic       |
| Base de datos  | PostgreSQL local (nativo, con `pgvector`) — Azure Database for PostgreSQL es el destino final cuando existan credenciales, sin cambio de código (solo `DATABASE_URL`) |
| Blob storage   | Azure Blob Storage                                                         |
| IA / RAG        | Azure Document Intelligence, Azure OpenAI, PostgreSQL + `pgvector` (búsqueda híbrida RRF + reranking cross-encoder local) |
| Deploy         | Docker (Dockerfile en cada servicio), `docker-compose.cloud.yml`           |
| Dev local      | `scripts/dev-start.ps1` arranca backend + frontend + migraciones           |

---

## Estructura de carpetas

```
backend/
  main.py               # App factory; registra todos los routers
  users/                # Auth JWT, registro, login
  analysis/             # Ciclo de vida de análisis (create → start → status)
  documents/            # Modelo Document, hashing de contenido
  infra/
    config.py           # Settings via pydantic-settings (lee .env)
    database.py         # SQLAlchemy — engine/SessionLocal siempre activos (Postgres)
    logging.py          # structlog JSON
    ports/               # Contratos para servicios externos (puertos, ver ARCHITECTURE.md)
    adapters/            # Implementaciones concretas (Azure Blob/OpenAI/Document Intelligence, PgVectorSearchAdapter)
  alembic/              # Migraciones de BD
frontend/
  src/
    api/                # Wrappers Axios: client.ts (interceptors), analyses.ts, auth.ts
    pages/              # Componentes de ruta (Dashboard, NewAnalysis, AnalysisDetail)
    components/         # UI reutilizable (Button, Input, Toast, Sidebar…)
    store/              # Zustand stores (useUIStore)
    types/              # Interfaces TS que replican los schemas Pydantic
    hooks/              # Custom hooks React
```

---

## Modelo de datos central

El modelo operativo vive en PostgreSQL como modelos SQLAlchemy (`Base` de
`infra.database`), con Alembic para migraciones. Tablas principales:
`analyses`, `documents`, `analysis_versions`, `chunks` (pgvector — ver
`docs/docu/pgvector-retrieval-runbook.md`), `events`/`deadlines` (timeline),
`tracking`/`tracking_categories`/`tracking_items`/`tracking_comments`, `users`.

```python
# analysis/models.py::Analysis
class Analysis(Base):
    __tablename__ = "analyses"
    id: str                          # UUID string(36)
    created_by: str                  # FK -> users.id
    current_version_id: str | None   # FK -> analysis_versions.id
    analysis_name: str | None
    status: str                      # draft|queued|processing|analyzed|error|cancelled
    current_stage: str               # queued|extracting_text|indexing|analyzing|consolidating|completed
    progress_percentage: int
    extraction_metadata: dict | None
    correlation_id: str
    created_at, updated_at, deleted_at: datetime | None   # soft delete

    documents: list[Document]        # relationship, cascade delete-orphan
    versions: list[AnalysisVersion]  # relationship, cascade delete-orphan

# documents/models.py::Document
class Document(Base):
    __tablename__ = "documents"
    id: str
    analysis_id: str                 # FK -> analyses.id, ondelete CASCADE
    filename: str
    blob_name: str
    sha256_hash: str                 # dedup exacta (binario)
    content_hash: str | None         # dedup semántica (texto normalizado)
    extraction_status: str           # pending|...
    extraction_error: str | None
    deleted_at: datetime | None

# analysis/models.py::AnalysisVersion
class AnalysisVersion(Base):
    __tablename__ = "analysis_versions"
    id: str
    analysis_id: str                 # FK -> analyses.id, ondelete CASCADE
    version_number: int
    extracted_data: dict
    conflicts: list[dict] | None
```

```typescript
// frontend — tipos TS (src/types/)

interface AnalysisStatusResponse {
  id: string;
  status: "draft" | "queued" | "analyzing" | "completed" | "error";
  current_stage: string | null;
}

interface DocumentSummary {
  id: string; filename: string;
  page_count: number; file_size_bytes: number; is_primary: boolean;
}
```

---

## Decisiones de arquitectura

1. **PostgreSQL + pgvector como única persistencia**: el runtime usa PostgreSQL (local nativo hoy, Azure Database for PostgreSQL como destino final), Azure Blob Storage, Azure Document Intelligence y Azure OpenAI. La búsqueda vectorial/híbrida corre sobre la extensión `pgvector` de Postgres (RRF + reranking cross-encoder local), no sobre Azure AI Search. Migración completada en la Épica 22 (2026-08-28) — ver `docs/docu/PLAN-migracion-cosmos-postgres-pgvector.md` y `docs/docu/pgvector-retrieval-runbook.md`.

2. **`infra.database.engine`/`SessionLocal` siempre activos**: no existe más un modo condicional (`PERSISTENCE_MODE` se eliminó junto con Cosmos); toda ruta y servicio usa SQLAlchemy contra Postgres.

3. **Soft delete obligatorio**: todos los modelos SQL usan `deleted_at: datetime | None`. Nunca borrar físicamente registros salvo hard-delete deliberado de análisis en error o cleanup operativo definido.

4. **Doble hash en documentos**: `sha256_hash` = hash binario del archivo (dedup exacta). `content_hash` = hash del texto normalizado extraído (dedup semántica). Ambos se verifican en duplicados.

5. **Formato de error uniforme**: Todo error HTTP usa `{"error": {"code": "SNAKE_CODE", "message": "..."}}`. El handler global en `main.py` normaliza excepciones que no usen este formato. El frontend **no** debe manejar formatos de error alternativos.

6. **Auth JWT en localStorage**: El token se guarda en `localStorage.access_token`. El interceptor de Axios lo inyecta en cada request. Un 401 limpia el token y redirige a `/login`. No usar cookies.

7. **Background tasks para análisis**: El procesamiento IA usa `FastAPI.BackgroundTasks`. El endpoint `/start` retorna inmediatamente; el cliente hace polling a `/status`.

8. **Flujo de duplicados**: `POST /analyses/{id}/start` puede retornar `requires_resolution: true` con lista de duplicados. El cliente debe re-llamar con `decisions[]` antes de continuar.

9. **Validaciones PDF en el servicio**: Solo se aceptan PDFs no encriptados de máximo 300 páginas y hasta 10 archivos por análisis. Límites definidos como constantes en `analysis/service.py`.

---

## Patrones clave (recetas)

### Agregar un nuevo módulo backend

1. Crear `backend/{módulo}/` con `__init__.py`, `models.py`, `schemas.py`, `service.py`, `routes.py`.
2. El modelo extiende `Base` de `infra.database`; incluir `deleted_at`, `created_at`, `updated_at`, id UUID string(36).
3. Crear migración: `alembic revision --autogenerate -m "add {módulo}"`.
4. Registrar en `main.py`: `app.include_router({módulo}_router, prefix="/api/v1")`.
5. Agregar tipos en `frontend/src/types/{módulo}.ts` y funciones en `frontend/src/api/{módulo}.ts`.

### Agregar un nuevo componente UI

1. Crear `frontend/src/components/MiComponente.tsx` (PascalCase).
2. Usar `clsx` + `tailwind-merge` para clases condicionales.
3. Formularios: `react-hook-form` + `zod` para validación.
4. Estado global mínimo: preferir React Query para server state; Zustand solo para UI state (ej: sidebar).

### Extender el modelo de datos

1. Actualizar el modelo SQLAlchemy correspondiente en `{módulo}/models.py`.
2. Actualizar el schema Pydantic en `schemas.py`.
3. Crear migración: `alembic revision --autogenerate -m "add {campo}"` (desde `backend/`, con la base local corriendo) y revisarla a mano antes de aplicarla.
4. Agregar o ajustar tests del flujo afectado (preferir Postgres real vía la fixture `pg_session_factory` sobre mocks cuando el cambio toca `chunks`/búsqueda híbrida).
5. Sincronizar la interfaz TS correspondiente en `frontend/src/types/`.

---

## Convenciones de nombres

| Contexto                   | Convención              |
|----------------------------|-------------------------|
| Funciones y variables Python | `snake_case`          |
| Clases Python              | `PascalCase`            |
| Tablas SQL                 | `plural_snake_case`     |
| Columnas SQL               | `snake_case`            |
| Componentes React          | `PascalCase`            |
| Variables/funciones TS     | `camelCase`             |
| Interfaces/tipos TS        | `PascalCase`            |
| Archivos de componentes    | `PascalCase.tsx`        |
| Archivos de utilidades TS  | `camelCase.ts`          |
| Rutas API                  | `/api/v1/{recurso_plural}` |
| Códigos de error           | `UPPER_SNAKE_CASE`      |

---

## Manejo de errores

| Capa          | Mecanismo                                                                                     |
|---------------|-----------------------------------------------------------------------------------------------|
| Backend API   | `raise HTTPException(status_code=..., detail={"error": {"code": "...", "message": "..."}})` |
| Backend global| Handler en `main.py` normaliza cualquier `HTTPException` al formato estándar                 |
| Servicios     | Elevan `HTTPException` directamente (no retornan errores como valores)                        |
| Frontend API  | Interceptor Axios maneja 401 globalmente; errores específicos se capturan en el componente    |
| Frontend UI   | Componente `Toast` para notificaciones de error al usuario                                    |
