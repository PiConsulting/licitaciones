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
| Backend        | FastAPI + Python 3.11+, Pydantic Settings, PyJWT, SQLAlchemy/Alembic solo compatibilidad |
| Base de datos  | Azure Cosmos DB en `PERSISTENCE_MODE=cosmos_only`                          |
| Blob storage   | Azure Blob Storage                                                         |
| IA / RAG        | Azure Document Intelligence, Azure OpenAI, Azure AI Search                 |
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
  shared/
    config.py           # Settings via pydantic-settings (lee .env)
    database.py         # SQLAlchemy solo fuera de cosmos_only; en cosmos_only engine/SessionLocal son None
    cosmos_container.py # Cliente Cosmos DB compartido
    logging.py          # structlog JSON
    ports/              # Contratos para servicios externos cuando aplican
    adapters/           # Implementaciones cloud vigentes
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

El modelo operativo actual vive en Cosmos DB. Los items relacionados con un análisis comparten `partition_key=<analysis_id>` y usan `type` como discriminador.

```python
# Cosmos item: analysis
{
  "id": "analysis::<analysis_id>",
  "type": "analysis",
  "partition_key": "<analysis_id>",
  "analysis_id": "<analysis_id>",
  "created_by": "<user_id>",
  "status": "draft|queued|processing|analyzed|error|cancelled",
  "current_stage": "queued|...|completed",
  "current_version_id": "<version_id|null>",
  "correlation_id": "<uuid>",
  "deleted": False,
}

# Cosmos item: document
{
  "id": "document::<document_id>",
  "type": "document",
  "partition_key": "<analysis_id>",
  "analysis_id": "<analysis_id>",
  "document_id": "<document_id>",
  "filename": "pliego.pdf",
  "blob_name": "<analysis_id>/<uuid>-pliego.pdf",
  "sha256_hash": "...",
  "content_hash": "...",
  "deleted": False,
}

# Cosmos item: analysis_version
{
  "id": "version::<version_id>",
  "type": "analysis_version",
  "partition_key": "<analysis_id>",
  "analysis_id": "<analysis_id>",
  "version_number": 1,
  "extracted_data": {},
  "conflicts": [],
}
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

1. **Cloud-first con Azure**: El runtime vigente usa Cosmos DB, Azure Blob Storage, Azure Document Intelligence, Azure OpenAI y Azure AI Search. No hay runtime local soportado para reemplazar el pipeline IA/RAG.

2. **Cosmos DB como fuente de verdad actual**: En `PERSISTENCE_MODE=cosmos_only`, `shared.database.engine` y `SessionLocal` son `None`; rutas y servicios deben usar los caminos Cosmos nativos.

3. **Soft delete obligatorio**: En Cosmos usar `deleted: true`/`deleted_at`; en modelos SQL legacy usar `deleted_at`. Nunca borrar físicamente registros salvo hard-delete deliberado de análisis en error o cleanup operativo definido.

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
2. El modelo extiende `Base` de `shared.database`; incluir `deleted_at`, `created_at`, `updated_at`, id UUID string(36).
3. Crear migración: `alembic revision --autogenerate -m "add {módulo}"`.
4. Registrar en `main.py`: `app.include_router({módulo}_router, prefix="/api/v1")`.
5. Agregar tipos en `frontend/src/types/{módulo}.ts` y funciones en `frontend/src/api/{módulo}.ts`.

### Agregar un nuevo componente UI

1. Crear `frontend/src/components/MiComponente.tsx` (PascalCase).
2. Usar `clsx` + `tailwind-merge` para clases condicionales.
3. Formularios: `react-hook-form` + `zod` para validación.
4. Estado global mínimo: preferir React Query para server state; Zustand solo para UI state (ej: sidebar).

### Extender el modelo de datos

1. Actualizar el contrato Cosmos correspondiente en el servicio/runtime dueño.
2. Actualizar el schema Pydantic en `schemas.py`.
3. Agregar o ajustar tests Cosmos del flujo afectado.
4. Sincronizar la interfaz TS correspondiente en `frontend/src/types/`.
5. Solo crear migración Alembic si la historia declara explícitamente trabajo sobre el camino SQL legacy o una migración futura.

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
