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
| Backend        | FastAPI + Python 3.11+, SQLAlchemy 2.0, Alembic, Pydantic Settings, PyJWT |
| Base de datos  | PostgreSQL (prod) / SQLite (dev/test)                                      |
| Blob storage   | Azure Blob Storage (prod) / filesystem local (dev) — Port/Adapter          |
| IA (puertos)   | Puertos definidos para LLM, Document Intelligence, Search — **sin impl.**  |
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
    database.py         # Engine SQLAlchemy + get_db()
    logging.py          # structlog JSON
    ports/              # Interfaces abstractas (BlobStorage, LLM, DocIntelligence, Search)
    adapters/           # Implementaciones concretas (Local, Azure)
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

```python
# backend — SQLAlchemy (todos usan soft delete vía deleted_at)

class User(Base):
    id: str           # UUID string(36)
    email: str        # único
    password_hash: str
    name: str
    deleted_at: datetime | None

class Analysis(Base):
    id: str
    created_by: str   # FK → users.id
    status: str       # "draft" | "queued" | "analyzing" | "completed" | "error"
    current_stage: str | None
    current_version_id: str | None
    correlation_id: str   # UUID para trazabilidad de background tasks
    deleted_at: datetime | None

class Document(Base):
    id: str
    analysis_id: str  # FK → analyses.id (CASCADE delete)
    filename: str
    blob_name: str    # referencia en BlobStorage
    sha256_hash: str  # deduplicación binaria (hash del archivo)
    content_hash: str | None  # deduplicación semántica (hash del texto extraído)
    is_primary: bool
    page_count: int
    file_size_bytes: int
    deleted_at: datetime | None
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

1. **Port/Adapter para servicios externos**: `BlobStoragePort`, `LLMClientPort`, `DocumentIntelligencePort`, `SearchClientPort` son ABCs en `shared/ports/`. El switch `USE_LOCAL_ADAPTERS=true` en `.env` activa el adaptador local sin tocar el servicio.

2. **Soft delete obligatorio**: Todos los modelos tienen `deleted_at`. Nunca borrar físicamente registros. Siempre filtrar `.where(Model.deleted_at.is_(None))` en queries.

3. **Doble hash en documentos**: `sha256_hash` = hash binario del archivo (dedup exacta). `content_hash` = hash del texto normalizado extraído (dedup semántica). Ambos se verifican en `find_duplicates_for_analysis`.

4. **Formato de error uniforme**: Todo error HTTP usa `{"error": {"code": "SNAKE_CODE", "message": "..."}}`. El handler global en `main.py` normaliza excepciones que no usen este formato. El frontend **no** debe manejar formatos de error alternativos.

5. **Auth JWT en localStorage**: El token se guarda en `localStorage.access_token`. El interceptor de Axios lo inyecta en cada request. Un 401 limpia el token y redirige a `/login`. No usar cookies.

6. **Background tasks para análisis**: El procesamiento IA usa `FastAPI.BackgroundTasks`. El endpoint `/start` retorna inmediatamente; el cliente hace polling a `/status`.

7. **Flujo de duplicados**: `POST /analyses/{id}/start` puede retornar `requires_resolution: true` con lista de duplicados. El cliente debe re-llamar con `decisions[]` antes de continuar.

8. **Validaciones PDF en el servicio**: Solo se aceptan PDFs no encriptados de máximo 300 páginas y hasta 10 archivos por análisis. Límites definidos como constantes en `analysis/service.py`.

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

1. Modificar `backend/{módulo}/models.py`.
2. Actualizar el schema Pydantic en `schemas.py`.
3. Generar migración Alembic y ejecutar `alembic upgrade head`.
4. Sincronizar la interfaz TS correspondiente en `frontend/src/types/`.

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
