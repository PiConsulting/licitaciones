import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
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
from infra.config import get_settings
from infra.database import engine
from infra.logging import configure_logging
from timeline.routes import timeline_router
from tracking.routes import tracking_router
from users.routes import auth_router, protected_router

logger = logging.getLogger(__name__)


def _database_health() -> tuple[str, str]:
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


def _azure_config_health() -> tuple[str, str, list[str]]:
    settings = get_settings()
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
    timestamp = datetime.now(UTC).isoformat()

    db_status, db_message = _database_health()

    pymupdf_status, pymupdf_message = _pymupdf_health()

    checks: dict[str, dict[str, Any]] = {
        "database": {
            "status": db_status,
            "message": db_message,
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


async def _warm_up_reranker(model_name: str) -> None:
    """Carga el cross-encoder de reranking en el arranque del server, no en
    el primer request real. FIX (2026-09-08): sin esto, la primera llamada a
    `rerank_chunks` de cada proceso paga el costo de importar
    sentence_transformers/torch (perezoso, dentro de `_load_model`) más la
    carga de pesos -- >10s medidos en este entorno, muy por encima de
    `rag_reranking_timeout_seconds` (5.0s por defecto) -- y esa primera
    llamada siempre cae al fallback de orden RRF. `_load_model` está
    cacheado (`lru_cache`), así que esto solo paga el costo una vez por
    proceso. Corre en un thread aparte para no bloquear el event loop
    durante el arranque; si falla (sin red, modelo no disponible, etc.) solo
    logueamos -- el reranking sigue teniendo su propio fallback seguro y no
    debe tumbar el arranque del server por esto.
    """
    try:
        from analysis.extraction.engine.reranking import _load_model

        await asyncio.to_thread(_load_model, model_name)
        logger.info("Reranker model warmed up: %s", model_name)
    except Exception:  # noqa: BLE001
        logger.warning("Reranker model warm-up failed: %s", model_name, exc_info=True)


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    if settings.is_production:
        settings.validate_cloud_configuration()
    if settings.rag_reranking_enabled:
        await _warm_up_reranker(settings.rag_reranking_model)
    yield


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="licitaciones-pi API", version="0.1.0", lifespan=_lifespan)

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
    app.include_router(tracking_router, prefix="/api/v1")
    app.include_router(timeline_router, prefix="/api/v1")
    app.include_router(documents_router, prefix="/api/v1")

    # DEBUG - quitar antes de commitear a producción
    from debug.chunks_viewer import debug_router

    app.include_router(debug_router, prefix="/api/debug")

    return app


app = create_app()
