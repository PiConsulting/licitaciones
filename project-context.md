# PROJECT_CONTEXT.md
> Contexto canónico para agentes de IA. Actualizar al cambiar arquitectura o convenciones.

## Git Workflow (OBLIGATORIO — leer antes de tocar cualquier archivo de código)

### Ramas protegidas
- `main` → producción. Solo merges desde `develop` vía PR.
- `develop` → integración. Solo merges desde ramas de feature/fix vía PR.

### Antes de modificar código — secuencia obligatoria
```bash
git branch --show-current          # verificar rama actual
git checkout develop
git pull origin develop
git checkout -b <tipo>/<descripcion-corta>   # crear rama de trabajo
```

### Nomenclatura de ramas
| Prefijo | Uso |
|---------|-----|
| `feat/` | nueva funcionalidad |
| `fix/` | corrección de bug |
| `refactor/` | refactorización sin cambio funcional |
| `test/` | solo tests |
| `chore/` | mantenimiento (deps, config, CI, docs) |

### Commits — Conventional Commits
```
<tipo>(<scope>): <descripcion imperativa en minúsculas>
```
Scopes válidos: `frontend`, `backend`, `auth`, `analysis`, `documents`, `storage`, `db`, `ci`, `agents`

Ejemplos:
- `feat(analysis): agregar endpoint para listar análisis paginados`
- `fix(auth): corregir expiración de token con timezone UTC-3`
- `chore(ci): agregar step de lint en GitHub Actions`

### Pull Requests
- Destino siempre: `develop` (nunca directamente a `main`)
- Título: mismo formato que el commit principal
- Usar el template `.github/pull_request_template.md` (se carga automáticamente)
- Instrucciones completas en `.github/copilot-instructions.md`

---

## Overview
Plataforma web para automatizar la extracción y análisis de documentos de licitaciones (pliegos PDF). El flujo actual cubre: registro/login con JWT, carga de PDFs a un análisis, validación básica de archivos y persistencia en base de datos; el pipeline de extracción con IA está definido en ports pero no implementado.

---

## Tech Stack

| Capa        | Tecnología                                             |
|-------------|--------------------------------------------------------|
| Frontend    | React 18 + TypeScript, Vite, Tailwind CSS, React Query, Zustand, Axios, Zod, react-hook-form |
| Backend     | Python 3.11, FastAPI, SQLAlchemy 2, Alembic, Pydantic Settings, passlib (bcrypt), PyJWT |
| Base de datos | SQLite (dev) / PostgreSQL-compatible (prod) vía `DATABASE_URL` env var |
| Storage     | Local filesystem (dev) / Azure Blob Storage (prod), seleccionado por `USE_LOCAL_ADAPTERS` |
| IA (ports)  | Ports definidos para Document Intelligence, LLM y Search; sin adaptadores concretos aún |
| Deploy      | Docker: backend en uvicorn:8000, frontend en nginx:80 |
| CI/CD       | GitHub Actions (push a `main`): ruff + pytest (backend), npm test + build (frontend) |

---

## Estructura de carpetas

```
backend/
  main.py                  # FastAPI app, CORS, exception handler global, montaje de routers
  shared/
    config.py              # Pydantic Settings — única fuente de config; lee .env
    database.py            # Engine SQLAlchemy + SessionLocal + get_db()
    ports/                 # Contratos abstractos: BlobStoragePort, LLMClientPort, etc.
    adapters/              # Implementaciones: LocalBlobStorageAdapter, AzureBlobStorageAdapter
  users/                   # Módulo bounded: models, schemas, routes, service
  analysis/                # Módulo bounded: models, schemas, routes, service
  documents/               # Solo models y schemas (sin routes propias)
  alembic/versions/        # Migraciones incrementales con timestamp_NNN_descripcion
frontend/
  src/
    api/                   # Funciones tipadas de llamada HTTP (auth.ts, analyses.ts, client.ts)
    types/                 # Contratos TS por dominio (auth.ts, analysis.ts, document.ts, upload.ts)
    store/                 # Zustand: useUIStore (estado UI global: sidebar)
    hooks/                 # Mutaciones reutilizables (useRegister, useFileUpload, useDocumentUpload)
    pages/                 # Vistas: Login, Register, Dashboard, NewAnalysis (wizard 3 pasos)
    components/            # UI atómicos y compuestos (Button, Input, Toast, DropZone, FileList…)
docs/                      # PRD y product brief — fuente de verdad funcional
```

---

## Modelo de datos central

```python
# backend — SQLAlchemy ORM (snake_case, UUIDs como str len=36)

class User(Base):
    id: str               # PK UUID
    email: str            # unique, normalizado a lowercase
    password_hash: str
    name: str
    created_at / updated_at: datetime (tz-aware)
    deleted_at: datetime | None  # soft-delete

class Analysis(Base):
    id: str               # PK UUID
    created_by: str       # FK → users.id
    status: str           # "queued" | (futuros estados del pipeline)
    current_stage: str | None
    correlation_id: str   # UUID para rastreo distribuido
    current_version_id: str | None
    created_at / updated_at / deleted_at: datetime

class Document(Base):
    id: str               # PK UUID
    analysis_id: str      # FK → analyses.id CASCADE DELETE
    filename: str
    blob_name: str        # clave en el storage (local path o Azure blob name)
    file_size_bytes: int
    page_count: int
    is_primary: bool      # un solo documento primario por análisis
    sha256_hash: str      # len=64, para deduplicación
    created_by: str       # FK → users.id
    uploaded_at / deleted_at: datetime
```

```typescript
// frontend — tipos espejo en src/types/

interface AnalysisCreateResponse {
  id: string; status: string;
  documents: DocumentSummary[];
  warnings: DocumentWarning[];
}
interface DocumentSummary { id: string; filename: string; page_count: number; file_size_bytes: number; is_primary: boolean; }
interface DocumentWarning  { filename: string; message: string; }
```

---

## Decisiones de arquitectura

- **Ports & Adapters (Hexagonal):** toda integración externa (storage, IA, search) pasa por un puerto abstracto en `shared/ports/`. Nunca instanciar un adaptador concreto fuera de `shared/adapters/`. La selección de adaptador ocurre en el servicio leyendo `settings.use_local_adapters`.
- **Handler de errores global:** `main.py` normaliza todas las `HTTPException` a `{ error: { code, message } }`. Los servicios lanzan `HTTPException` con `detail={"error": {"code": "...", "message": "..."}}` — nunca texto plano en `detail`.
- **Cleanup-on-failure:** si el proceso falla tras subir blobs, el servicio hace rollback de DB y borra los blobs ya subidos. Mantener este patrón en todo flujo de escritura multi-paso.
- **Soft-delete:** los modelos tienen `deleted_at`. Las queries deben filtrar `deleted_at IS NULL`. No usar `DELETE` físico.
- **Auth sin refresh tokens:** JWT de 24h almacenado en `localStorage`. El interceptor Axios detecta 401 y redirige a `/login`. No hay refresh token por ahora.
- **Sesión DB por request:** `get_db()` es un `Depends` que abre/cierra `SessionLocal`; nunca compartir sesiones entre requests.
- **CORS restringido:** actualmente solo `http://localhost:5173`. En prod, ajustar vía env var (no hardcodear orígenes).

---

## Patrones clave (recetas)

### Agregar un nuevo módulo/entidad backend
1. Crear carpeta `backend/<dominio>/` con `__init__.py`, `models.py`, `schemas.py`, `routes.py`, `service.py`.
2. `models.py`: heredar de `Base` (de `shared/database.py`), usar str UUID como PK, incluir `created_at`, `updated_at`, `deleted_at`.
3. Generar migración: `alembic revision --autogenerate -m "<descripcion>"`, revisar el archivo generado en `alembic/versions/`.
4. `service.py`: recibir `Session` y schemas como parámetros; lanzar errores como `HTTPException(status_code=..., detail={"error": {"code": "...", "message": "..."}})`.
5. `routes.py`: registrar el router con `prefix="/api/v1/<dominio>"` y añadirlo en `main.py`.

### Agregar un nuevo componente UI
1. Crear `frontend/src/components/<ComponentName>.tsx` en PascalCase.
2. Definir props con interfaz TypeScript inline o en `src/types/`.
3. Usar clases Tailwind; respetar el design system en `design-artifacts/D-Design-System/`.
4. Si necesita estado servidor, crear hook en `src/hooks/use<Nombre>.ts` con `useMutation`/`useQuery` de React Query.
5. Estado UI puro → Zustand (`useUIStore`) solo si es global; de lo contrario `useState` local.

### Extender el modelo de datos
1. Modificar el modelo SQLAlchemy en `models.py`.
2. Actualizar schemas Pydantic en `schemas.py`.
3. Generar y revisar migración Alembic.
4. Actualizar tipos TS espejo en `frontend/src/types/`.
5. Actualizar la función API correspondiente en `frontend/src/api/`.

---

## Convenciones de nombres

| Contexto                        | Convención                            |
|---------------------------------|---------------------------------------|
| Python: funciones, variables    | `snake_case`                          |
| Python: clases (ORM, schemas)   | `PascalCase`                          |
| Python: tablas y columnas DB    | `snake_case`                          |
| Rutas API                       | kebab-case sustantivos plurales: `/analyses`, `/auth/login` |
| Códigos de error backend        | `SCREAMING_SNAKE_CASE`: `EMAIL_ALREADY_EXISTS` |
| TypeScript: componentes, tipos  | `PascalCase`                          |
| TypeScript: funciones, vars     | `camelCase`                           |
| TypeScript: hooks               | `useNombreDescriptivo`                |
| Archivos de migración           | `YYYYMMDD_NNNN_descripcion_breve.py`  |
| Ramas Git                       | No definido formalmente aún           |
| Commits                         | No definido formalmente aún           |

---

## Manejo de errores

| Capa              | Patrón                                                                                  |
|-------------------|-----------------------------------------------------------------------------------------|
| Backend – servicio | `raise HTTPException(status_code=4xx, detail={"error": {"code": "...", "message": "..."}})` |
| Backend – handler global | `main.py` intercepta toda `HTTPException`; si `detail` ya es `{"error": ...}` lo pasa tal cual; si no, lo envuelve con `code: HTTP_ERROR` |
| Backend – cleanup | Patrón try/except/finally: si falla tras operaciones externas (blobs), rollback DB + cleanup blobs |
| Frontend – formularios | Zod + react-hook-form para validación cliente; errores mostrados inline por campo |
| Frontend – upload | Hook `useFileUpload` valida conteo (máx 10), tamaño por archivo (50 MB), total (150 MB) y formato PDF antes de llamar a la API |
| Frontend – API global | Interceptor Axios: 401 → limpiar token y redirigir a `/login`; otros errores propagados al llamador |
| Frontend – feedback | `Toast`/`ToastContainer` para notificaciones de éxito/error post-mutación |
