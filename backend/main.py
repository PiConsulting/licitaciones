import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from analysis.routes import analysis_router
from documents.routes import router as documents_router
from extraction.ai_search import validate_index_contract
from shared.config import get_settings
from shared.database import engine
from shared.logging import configure_logging
from users.routes import auth_router, protected_router

logger = logging.getLogger(__name__)


def _database_health() -> tuple[str, str]:
    if engine is None:
        return "skipped", "Chequeo de base SQL omitido (cosmos_only)"
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return "ok", "Conectividad de base de datos operativa"
    except SQLAlchemyError as exc:
        logger.warning("Healthcheck: database unavailable", exc_info=exc)
        return "error", "No se pudo conectar a la base de datos"
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.warning("Healthcheck: unexpected database failure", exc_info=exc)
        return "error", "Error inesperado verificando base de datos"


def _cosmos_health() -> tuple[str, str]:
    """FIX (auditoría 2026-08-12, flujo Cosmos): en los modos que usan Cosmos
    (`cosmos`, `dual_write`, `cosmos_temporal`, `cosmos_only`) no existía
    NINGÚN chequeo real de conectividad -- `_azure_config_health()` solo
    valida que las variables de entorno estén seteadas
    (`missing_cloud_required_variables()`), nunca hace una llamada real
    contra Cosmos. Con eso, `/health` podía reportar "ok" durante un outage
    real de Cosmos DB, justo en los modos donde SQL se saltea y Cosmos es la
    única fuente de verdad. `.read()` sobre el container es una llamada
    liviana de metadata (no toca documentos), igual de barata que el
    `SELECT 1` que ya se usa para el chequeo de SQL."""
    from shared.cosmos_container import get_cosmos_container

    try:
        container = get_cosmos_container()
        container.read()
        return "ok", "Conectividad con Cosmos DB operativa"
    except Exception as exc:  # noqa: BLE001 - cualquier fallo de conectividad debe marcar error
        logger.warning("Healthcheck: cosmos unavailable", exc_info=exc)
        return "error", "No se pudo conectar a Cosmos DB"


def _azure_config_health() -> tuple[str, str, list[str]]:
    settings = get_settings()
    mode = settings.persistence_mode_normalized()
    if mode not in {"sql", "cosmos", "dual_write", "cosmos_temporal", "cosmos_only"}:
        return "error", "Modo de persistencia inválido", ["PERSISTENCE_MODE"]

    missing = settings.missing_cloud_required_variables()
    if missing:
        return "error", "Falta configuración para Azure", missing
    return "ok", "Configuración de Azure presente", []


def _pymupdf_health() -> tuple[str, str]:
    """FIX MEDIUM (#9): Validar que PyMuPDF esté disponible para highlights."""
    try:
        import fitz  # PyMuPDF
        version = fitz.VersionBind
        return "ok", f"PyMuPDF disponible (versión {version})"
    except ImportError:
        return "error", "PyMuPDF no está instalado - highlights no funcionarán"
    except Exception as exc:
        logger.warning("Healthcheck: PyMuPDF check failed unexpectedly", exc_info=exc)
        return "warning", f"PyMuPDF check falló: {str(exc)[:100]}"


def _run_health_checks() -> tuple[int, dict[str, Any]]:
    settings = get_settings()
    timestamp = datetime.now(UTC).isoformat()

    mode = settings.persistence_mode_normalized()
    if settings.is_production and mode in {"cosmos_temporal", "cosmos_only", "cosmos"}:
        db_status, db_message = "skipped", f"Chequeo de base SQL omitido en modo {mode}"
    else:
        db_status, db_message = _database_health()

    # FIX (auditoría 2026-08-12, flujo Cosmos): antes no había ningún chequeo
    # real de Cosmos -- justo en los modos donde el chequeo de SQL de arriba
    # se saltea. Se corre siempre que el modo de persistencia use Cosmos
    # (todos menos "sql" puro), igual que el chequeo de SQL corre siempre que
    # el modo lo use.
    if mode in {"cosmos", "dual_write", "cosmos_temporal", "cosmos_only"}:
        cosmos_status, cosmos_message = _cosmos_health()
    else:
        cosmos_status, cosmos_message = "skipped", "Cosmos no se usa en este modo de persistencia"

    # FIX MEDIUM (#9): Validar PyMuPDF disponible
    pymupdf_status, pymupdf_message = _pymupdf_health()

    checks: dict[str, dict[str, Any]] = {
        "database": {
            "status": db_status,
            "message": db_message,
        },
        "cosmos": {
            "status": cosmos_status,
            "message": cosmos_message,
        },
        "pymupdf": {
            "status": pymupdf_status,
            "message": pymupdf_message,
        },
    }

    # Verificar solo configuración de Azure (eliminados adaptadores locales)
    azure_status, azure_message, missing = _azure_config_health()
    checks["adapters"] = {
        "status": azure_status,
        "mode": "cloud",
        "message": azure_message,
        "missing": missing,
    }

    has_errors = any(item["status"] == "error" for item in checks.values())
    status_code = 503 if has_errors else 200
    payload = {
        "status": "degraded" if has_errors else "ok",
        "timestamp": timestamp,
        "checks": checks,
    }
    return status_code, payload


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="licitaciones-pi API", version="0.1.0")

    @app.on_event("startup")
    def validate_cloud_startup_configuration() -> None:
        settings = get_settings()
        if settings.is_production:
            settings.validate_cloud_configuration()
            # FIX (auditoría 2026-08-12, hallazgo US-4.2): antes este chequeo
            # de schema recién se disparaba en el primer upload_chunks() real
            # (guardado con `if settings.is_production`), es decir en medio
            # de un análisis en curso -- muy tarde para evitar el incidente
            # de campos faltantes en el índice. Validarlo acá lo mueve al
            # arranque real de la app, antes de aceptar tráfico.
            validate_index_contract()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_, exc: HTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": "HTTP_ERROR", "message": str(exc.detail)}},
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_exception_handler(_, exc: Exception) -> JSONResponse:
        logger.exception("Database connectivity error", exc_info=exc)
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "code": "DATABASE_UNAVAILABLE",
                    "message": "No se pudo conectar a la base de datos",
                }
            },
        )

    @app.exception_handler(UnicodeDecodeError)
    async def unicode_decode_exception_handler(_, exc: UnicodeDecodeError) -> JSONResponse:
        logger.exception("Unicode decoding error", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "UNICODE_DECODE_ERROR",
                    "message": "Error de codificacion de caracteres",
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled server error", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "Ocurrió un error interno",
                }
            },
        )

    @app.get("/health")
    def healthcheck() -> JSONResponse:
        status_code, payload = _run_health_checks()
        return JSONResponse(status_code=status_code, content=payload)

    @app.get("/health/liveness")
    def liveness() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(protected_router, prefix="/api/v1")
    app.include_router(analysis_router, prefix="/api/v1")
    app.include_router(documents_router, prefix="/api/v1")
    
    # 🔧 DEBUG - quitar antes de commitear
    from debug.chunks_viewer import debug_router
    app.include_router(debug_router, prefix="/api/debug")
    
    return app


app = create_app()